"""Shared Google OAuth credential loading for gmail_client.py and
drive_client.py -- one consent grant, one cached token, covering every
scope any direct-API client in this project needs.

SCOPES is the single combined list. Adding a new Google API surface means
adding its scope here and re-running `python scripts/google_auth.py --auth`
once (existing cached tokens do not automatically pick up new scopes).
"""

import argparse
import os
import pathlib
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

ROOT = pathlib.Path(__file__).resolve().parent.parent

SCOPES = [
    # Gmail -- deliberately excludes gmail.send; see gmail_client.py.
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/gmail.modify",
    # Drive -- drive.file only: this app can see/manage only files it
    # creates itself, never the founder's wider Drive.
    "https://www.googleapis.com/auth/drive.file",
    # Drive Activity -- read-only, needed for the data-room view log
    # (who opened what, when).
    "https://www.googleapis.com/auth/drive.activity.readonly",
]


def _paths():
    creds_path = pathlib.Path(os.environ["GMAIL_CREDENTIALS_PATH"]).expanduser()
    token_path = pathlib.Path(os.environ["GMAIL_TOKEN_PATH"]).expanduser()
    return creds_path, token_path


def get_credentials():
    creds_path, token_path = _paths()
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_path.exists():
                print(
                    "No OAuth client credentials at {}. Create a Desktop OAuth "
                    "client in Google Cloud Console and save it there first.".format(creds_path),
                    file=sys.stderr,
                )
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())
    return creds


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth", action="store_true")
    args = parser.parse_args()
    if args.auth:
        get_credentials()
        print("Authenticated. Token cached at", os.environ["GMAIL_TOKEN_PATH"])
