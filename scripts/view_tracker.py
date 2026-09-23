"""RAISE's own data-room view tracker -- replaces the Drive Activity API
as the source of data_room_views, since Drive Activity does not
reliably report views for personal (non-Workspace) Gmail viewers
(confirmed live, twice; see workflows/DATA_ROOM_PROCEDURE.md).

Mechanism: a tiny Google Apps Script Web App (pasted in manually once --
see workflows/VIEW_TRACKER_SETUP.md) serves each investor a unique
tracking link. On a hit, the script logs (token, timestamp) to a Google
Sheet and redirects the browser to the real Drive file. This module
writes the token->file mapping to that Sheet at grant time, and reads
back new view events at report time.

Known limitation: Apps Script's doGet(e) event object exposes no HTTP
headers -- no user-agent, no IP. This tracks "opened, when, how many
times," never who/what device/browser, and cannot detect a forwarded
link. If that ever matters, the tracker's backend can be swapped for
Cloudflare Workers (which does see headers/IP) without changing anything
on RAISE's Postgres side -- this module's only contract is
(token, viewed_at) events in, nothing about where they came from.

Usage:
    python scripts/view_tracker.py setup
"""

import argparse
import datetime
import os
import pathlib
import sys

from googleapiclient.discovery import build

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from google_auth import get_credentials  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent

TOKENS_HEADER = ["token", "investor_id", "file_id", "drive_url", "created_at"]
EVENTS_HEADER = ["token", "viewed_at"]
TOKENS_RANGE = "tokens!A:E"
EVENTS_RANGE = "events!A:B"


def _sheets():
    return build("sheets", "v4", credentials=get_credentials())


def create_sheet():
    """One-time setup: creates the tracker spreadsheet with both tabs and
    headers. Prints the spreadsheet id -- put it in .env as
    VIEW_TRACKER_SHEET_ID."""
    sheets = _sheets()
    body = {
        "properties": {"title": "RAISE View Tracker"},
        "sheets": [
            {"properties": {"title": "tokens"}},
            {"properties": {"title": "events"}},
        ],
    }
    spreadsheet = sheets.spreadsheets().create(body=body, fields="spreadsheetId").execute()
    spreadsheet_id = spreadsheet["spreadsheetId"]

    sheets.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range="tokens!A1",
        valueInputOption="RAW", body={"values": [TOKENS_HEADER]},
    ).execute()
    sheets.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range="events!A1",
        valueInputOption="RAW", body={"values": [EVENTS_HEADER]},
    ).execute()
    return spreadsheet_id


def register_link(spreadsheet_id, token, investor_id, file_id, drive_url):
    """Writes the token->file mapping the Apps Script needs to know where
    to redirect. Called once per grant, from data_room.grant_access()."""
    row = [token, str(investor_id), str(file_id), drive_url, datetime.datetime.now(datetime.timezone.utc).isoformat()]
    _sheets().spreadsheets().values().append(
        spreadsheetId=spreadsheet_id, range=TOKENS_RANGE,
        valueInputOption="RAW", insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()


def fetch_events(spreadsheet_id):
    """Reads every logged view event. Full re-fetch each call -- dedup
    happens at the Postgres insert (unique index on
    data_room_views(file_id, viewed_at)), not a watermark here, so a
    missed report() run can never lose an event."""
    resp = _sheets().spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=EVENTS_RANGE
    ).execute()
    rows = resp.get("values", [])
    events = []
    for row in rows[1:]:  # skip header
        if len(row) < 2:
            continue
        events.append({"token": row[0], "viewed_at": row[1]})
    return events


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup")
    args = parser.parse_args()

    if args.command == "setup":
        spreadsheet_id = create_sheet()
        print("Created tracker spreadsheet:", spreadsheet_id)
        print("Add to .env: VIEW_TRACKER_SHEET_ID={}".format(spreadsheet_id))
        print("Next: follow workflows/VIEW_TRACKER_SETUP.md to deploy the Apps Script.")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    main()
