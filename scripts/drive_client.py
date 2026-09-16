"""Direct Google Drive API client for RAISE's data room.

Every file lives inside RAISE's own drive.file scope (files this app
creates, never the founder's wider Drive). Sharing is always a restricted
grant to one specific email -- never "anyone with the link" -- both because
that is what "unique link, never shared across firms" requires, and because
Drive can only attribute a view to a named identity when the file was
shared with that person directly.

First-time setup: see scripts/google_auth.py (same shared OAuth token as
gmail_client.py -- Drive and Drive Activity APIs must also be enabled on
the Cloud project, same as Gmail was).
"""

import pathlib
import sys

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from google_auth import get_credentials  # noqa: E402


def _drive():
    return build("drive", "v3", credentials=get_credentials())


def _activity():
    return build("driveactivity", "v2", credentials=get_credentials())


def create_folder(name, parent_id=None):
    service = _drive()
    body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        body["parents"] = [parent_id]
    folder = service.files().create(body=body, fields="id").execute()
    return folder["id"]


def upload_and_share(local_path, filename, parent_folder_id, email, expiry_date=None, mime_type="application/pdf"):
    """Upload one file into a folder and grant read access to exactly one
    email. Returns {file_id, share_url}. expiry_date is a datetime.date;
    Drive's own permission-expiration only applies to Workspace-domain
    users, so this is also enforced by RAISE (data_room_links.expiry_date)
    regardless of whether Drive honors it for this recipient."""
    service = _drive()
    file_metadata = {"name": filename, "parents": [parent_folder_id]}
    media = MediaFileUpload(local_path, mimetype=mime_type)
    file = service.files().create(body=file_metadata, media_body=media, fields="id, webViewLink").execute()
    file_id = file["id"]

    permission = {"type": "user", "role": "reader", "emailAddress": email}
    if expiry_date is not None:
        permission["expirationTime"] = expiry_date.isoformat() + "T00:00:00Z"
    try:
        service.permissions().create(fileId=file_id, body=permission, sendNotificationEmail=False).execute()
    except Exception as exc:  # noqa: BLE001
        # expirationTime is rejected for non-Workspace recipients on some
        # tiers -- retry once without it rather than failing the whole grant.
        if "expirationTime" in permission:
            del permission["expirationTime"]
            service.permissions().create(fileId=file_id, body=permission, sendNotificationEmail=False).execute()
        else:
            raise exc

    file = service.files().get(fileId=file_id, fields="webViewLink").execute()
    return {"file_id": file_id, "share_url": file["webViewLink"]}


def list_view_activity(file_id):
    """Best-effort view log for one file via the Drive Activity API.
    Returns [{timestamp, actor_identifier, is_known_user}]. actor_identifier
    is a Drive person resource name (e.g. 'people/123...'), not necessarily
    a resolved email -- resolving that further needs the People API, not
    wired up here. Anonymous/unattributable views come back with
    actor_identifier=None, is_known_user=False."""
    service = _activity()
    body = {"itemName": "items/" + file_id, "filter": "detail.action_detail_case:VIEW"}
    response = service.activity().query(body=body).execute()

    events = []
    for activity in response.get("activities", []):
        timestamp = activity.get("timestamp") or (activity.get("timeRange") or {}).get("endTime")
        for actor in activity.get("actors", []):
            user = actor.get("user", {})
            known = user.get("knownUser")
            events.append({
                "timestamp": timestamp,
                "actor_identifier": known.get("personName") if known else None,
                "is_known_user": known is not None,
            })
    return events
