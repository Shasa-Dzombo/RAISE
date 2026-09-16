"""Direct Gmail API client for the standalone orchestrator.

Used only when RAISE runs outside a Claude Code session (the Claude Gmail
MCP connector is not reachable from a plain Python process). Mirrors the
subset of the MCP connector's surface that Stage 2 actually needs.

Deliberately does NOT implement send/reply/forward/trash/spam -- those
functions simply do not exist in this module, so no tool-calling loop built
on top of it can call them, no matter what the model decides. This is a
structural safety boundary, not a documented rule the model could ignore.

First-time setup:
  1. In Google Cloud Console, create an OAuth 2.0 Client ID of type
     "Desktop app" for the Gmail account this should act on.
  2. Download the client secret JSON, save it at GMAIL_CREDENTIALS_PATH
     (see .env.example).
  3. Run `python scripts/gmail_client.py --auth` once. It opens a browser for
     consent and caches a refresh token at GMAIL_TOKEN_PATH. Only Gmail
     read/compose/label scopes are requested -- never gmail.send.
"""

import argparse
import base64
import pathlib
import sys
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from googleapiclient.discovery import build

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from google_auth import get_credentials  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Note: gmail.send is deliberately never requested (see google_auth.py's
# SCOPES) -- this client can read, label, and create drafts, but the OAuth
# scope itself makes sending impossible even if a bug called the wrong
# method.


def _service():
    return build("gmail", "v1", credentials=get_credentials())


def list_labels():
    service = _service()
    resp = service.users().labels().list(userId="me").execute()
    return resp.get("labels", [])


def create_label(name):
    service = _service()
    body = {"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"}
    return service.users().labels().create(userId="me", body=body).execute()


def get_or_create_label_id(name):
    for label in list_labels():
        if label["name"] == name:
            return label["id"]
    return create_label(name)["id"]


def search_threads(query, max_results=20):
    service = _service()
    resp = service.users().threads().list(userId="me", q=query, maxResults=max_results).execute()
    return resp.get("threads", [])


def get_thread(thread_id):
    service = _service()
    raw = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
    messages = []
    for msg in raw.get("messages", []):
        # Unlike the Claude MCP Gmail connector, the raw API includes a
        # thread's own draft messages in threads.get(). A draft is not a
        # sent/received message -- including it let the orchestrator once
        # mistake its own earlier draft for a new inbound message and
        # reply to itself. Match the MCP connector's (correct) behavior.
        if "DRAFT" in msg.get("labelIds", []):
            continue
        headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
        messages.append({
            "id": msg["id"],
            "threadId": msg["threadId"],
            "sender": headers.get("from", ""),
            "to": headers.get("to", ""),
            "date": _internal_date_iso(msg),
            "plaintextBody": _extract_plaintext(msg["payload"]),
            "labelIds": msg.get("labelIds", []),
        })
    return {"id": thread_id, "messages": messages}


def _internal_date_iso(msg):
    import datetime
    ms = int(msg["internalDate"])
    return datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc).isoformat()


def _extract_plaintext(payload):
    if payload.get("mimeType") == "text/plain" and "data" in payload.get("body", {}):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    for part in payload.get("parts", []) or []:
        text = _extract_plaintext(part)
        if text:
            return text
    return ""


def create_draft(to, subject, body, reply_to_message_id=None, thread_id=None, attachment_path=None):
    service = _service()
    if attachment_path:
        mime = MIMEMultipart()
        mime.attach(MIMEText(body))
        with open(attachment_path, "rb") as f:
            part = MIMEApplication(f.read(), _subtype="pdf")
        part.add_header("Content-Disposition", "attachment", filename=pathlib.Path(attachment_path).name)
        mime.attach(part)
    else:
        mime = MIMEText(body)
    mime["to"] = to
    mime["subject"] = subject
    if reply_to_message_id:
        mime["In-Reply-To"] = reply_to_message_id
        mime["References"] = reply_to_message_id
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    message = {"raw": raw}
    if thread_id:
        message["threadId"] = thread_id
    draft_body = {"message": message}
    return service.users().drafts().create(userId="me", body=draft_body).execute()


def label_thread(thread_id, label_ids):
    service = _service()
    return service.users().threads().modify(
        userId="me", id=thread_id, body={"addLabelIds": label_ids}
    ).execute()


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth", action="store_true", help="run the one-time OAuth consent flow")
    args = parser.parse_args()
    if args.auth:
        get_credentials()
        print("Authenticated. Token cached at", os.environ["GMAIL_TOKEN_PATH"])
