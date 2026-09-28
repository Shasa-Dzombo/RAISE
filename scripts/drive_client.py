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
    """Upload one file into a folder and share it as "anyone with the
    link, reader". Returns {file_id, share_url}.

    Deliberately NOT restricted to `email` at the Drive layer anymore --
    that restriction existed only so Drive's own Activity API could
    attribute a view to an identity. It never worked for personal Gmail
    viewers anyway (see workflows/DATA_ROOM_PROCEDURE.md) and caused a
    real "you need access" / sign-in friction point once the tracker
    took over attribution. Real access control now lives entirely in the
    tracker token (96 bits of randomness) that's actually handed out --
    the same model DocSend/Papermark links use. `email` is kept only for
    bookkeeping (recorded in data_room_files.shared_with_email and the
    tracker's tokens sheet), not for restricting who can open the file.

    expiry_date is a datetime.date; Drive's expirationTime field is only
    honored for user/group-type permissions, not "anyone" -- so this
    call is expected to always retry without it, relying entirely on
    RAISE's own data_room_links.expiry_date for enforcement."""
    service = _drive()
    file_metadata = {"name": filename, "parents": [parent_folder_id]}
    media = MediaFileUpload(local_path, mimetype=mime_type)
    file = service.files().create(body=file_metadata, media_body=media, fields="id, webViewLink").execute()
    file_id = file["id"]

    permission = {"type": "anyone", "role": "reader"}
    if expiry_date is not None:
        permission["expirationTime"] = expiry_date.isoformat() + "T00:00:00Z"
    try:
        service.permissions().create(fileId=file_id, body=permission, sendNotificationEmail=False).execute()
    except Exception as exc:  # noqa: BLE001
        # expirationTime is not supported on "anyone" permissions -- retry
        # once without it rather than failing the whole grant.
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
