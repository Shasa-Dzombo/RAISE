"""Small Google Calendar edge client used by Scheduler."""

import datetime

from googleapiclient.discovery import build

from google_auth import get_credentials


def _service():
    return build("calendar", "v3", credentials=get_credentials())


def list_events(time_min, time_max, calendar_id="primary"):
    response = _service().events().list(
        calendarId=calendar_id,
        timeMin=time_min.isoformat(),
        timeMax=time_max.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return response.get("items", [])


def create_hold(start, end, summary, description, calendar_id="primary"):
    event = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
        "transparency": "opaque",
        "status": "tentative",
    }
    return _service().events().insert(calendarId=calendar_id, body=event).execute()


def release_hold(event_id, calendar_id="primary"):
    return _service().events().delete(calendarId=calendar_id, eventId=event_id).execute()
