"""Data room orchestration (agents/SPECIALISTS.md #5 DATA ROOM).

Per firm: unique Drive folder, watermarked copy of each file, a restricted
share (one specific email, never a public link), an expiry date, and a
view log built from the Drive Activity API. Full-tier access requires
explicit founder approval, per firm -- enforced by the caller checking
investor_file.approved before calling grant_access with tier='full'.

Usage:
    python scripts/data_room.py grant --investor-id 3 --tier teaser --email partner@fund.com --deck path/to/deck.pdf
    python scripts/data_room.py report
"""

import argparse
import os
import pathlib
import secrets
import sys
from datetime import date, timedelta

import psycopg
from dotenv import load_dotenv

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import drive_client  # noqa: E402
import view_tracker  # noqa: E402
from watermark_pdf import watermark_pdf  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
ROOT_FOLDER_NAME = "RAISE Data Room"
DEFAULT_EXPIRY_DAYS = 30


def _get_root_folder_id(cur, conn):
    cur.execute("SELECT location FROM assets WHERE asset_key = 'data_room_root_folder'")
    row = cur.fetchone()
    if row:
        return row[0]
    folder_id = drive_client.create_folder(ROOT_FOLDER_NAME)
    cur.execute(
        "INSERT INTO assets (asset_key, asset_type, location, description) VALUES (%s,%s,%s,%s)",
        ("data_room_root_folder", "data_room_folder", folder_id, "Root Drive folder for all per-firm data rooms"),
    )
    return folder_id


def grant_access(conn, investor_id, tier, email, deck_path, expiry_days=DEFAULT_EXPIRY_DAYS):
    # Atomic on purpose: conn is autocommit, so without an explicit
    # transaction a failure partway through (bad deck path, Drive hiccup,
    # missing tracker env vars) would leave an orphaned data_room_links
    # row committed with no matching data_room_files row -- which then
    # blocks every future grant for that investor via
    # idx_data_room_links_active (one active link per firm). Hit this for
    # real once already; wrapping the whole thing in one transaction means
    # any failure rolls back cleanly and a retry just works.
    with conn.transaction(), conn.cursor() as cur:
        cur.execute("SELECT firm_name, approved FROM investor_file WHERE id = %s", (investor_id,))
        row = cur.fetchone()
        if row is None:
            raise ValueError("no investor_file row with id {}".format(investor_id))
        firm_name, approved = row
        if tier == "full" and not approved:
            raise ValueError("firm is not approved -- full-tier access requires founder approval first")

        root_folder_id = _get_root_folder_id(cur, conn)
        firm_folder_id = drive_client.create_folder("{} -- {}".format(firm_name, tier), root_folder_id)

        expiry_date = date.today() + timedelta(days=expiry_days)
        cur.execute(
            """
            INSERT INTO data_room_links (investor_id, tier, drive_folder_id, expiry_date)
            VALUES (%s, %s, %s, %s) RETURNING id
            """,
            (investor_id, tier, firm_folder_id, expiry_date),
        )
        link_id = cur.fetchone()[0]

        watermarked_path = ROOT / "scratch" / "{}_{}.pdf".format(firm_name.replace(" ", "_"), pathlib.Path(deck_path).stem)
        watermark_pdf(deck_path, watermarked_path, firm_name)

        upload = drive_client.upload_and_share(str(watermarked_path), pathlib.Path(deck_path).name, firm_folder_id, email, expiry_date)

        # Own tracking link instead of the raw Drive URL -- Drive Activity
        # does not reliably report views for personal Gmail viewers (see
        # workflows/DATA_ROOM_PROCEDURE.md). What the investor actually
        # receives is the tracker link; the real Drive URL only lives in
        # the tracker's own Sheet, for the Apps Script to redirect to.
        sheet_id = os.environ.get("VIEW_TRACKER_SHEET_ID")
        base_url = os.environ.get("VIEW_TRACKER_BASE_URL")
        if not sheet_id or not base_url:
            raise ValueError(
                "VIEW_TRACKER_SHEET_ID and VIEW_TRACKER_BASE_URL must be set -- "
                "run `python scripts/view_tracker.py setup` and follow "
                "workflows/VIEW_TRACKER_SETUP.md first"
            )
        token = secrets.token_urlsafe(12)
        tracker_url = "{}?t={}".format(base_url, token)

        cur.execute(
            """
            INSERT INTO data_room_files (link_id, drive_file_id, filename, share_url, shared_with_email, tracking_token)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (link_id, upload["file_id"], pathlib.Path(deck_path).name, tracker_url, email, token),
        )
        file_row_id = cur.fetchone()[0]

        view_tracker.register_link(sheet_id, token, investor_id, file_row_id, upload["share_url"])

        cur.execute(
            "INSERT INTO activity_log (actor, action_type, entity_type, entity_id, details) VALUES (%s,%s,%s,%s,%s)",
            ("Data room", "link_granted", "data_room_links", str(link_id),
             '{{"firm": "{}", "tier": "{}", "email": "{}", "expiry": "{}"}}'.format(firm_name, tier, email, expiry_date)),
        )

    return {"link_id": link_id, "file_id": file_row_id, "share_url": tracker_url, "expiry_date": str(expiry_date)}


def morning_report(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT f.id, i.firm_name, f.filename, f.drive_file_id, f.shared_with_email, f.tracking_token
            FROM data_room_files f
            JOIN data_room_links l ON l.id = f.link_id
            JOIN investor_file i ON i.id = l.investor_id
            WHERE l.revoked_at IS NULL
            """
        )
        files = cur.fetchall()

        print("Data room morning report -- {}".format(date.today()))
        print("=" * 50)
        if not files:
            print("No active data room links.")
            return

        # One fetch covers every file's tracker events -- group by token
        # rather than re-fetching the whole sheet per file.
        sheet_id = os.environ.get("VIEW_TRACKER_SHEET_ID")
        events_by_token = {}
        if sheet_id:
            for event in view_tracker.fetch_events(sheet_id):
                events_by_token.setdefault(event["token"], []).append(event["viewed_at"])

        for file_row_id, firm_name, filename, drive_file_id, shared_with_email, tracking_token in files:
            print("\n{} -- {}".format(firm_name, filename))

            if tracking_token:
                # Own tracker is the source of truth for anything granted
                # after this feature landed. viewer_email is the email the
                # link was issued to -- the token guarantees that identity
                # by construction (modulo forwarding, which this cannot
                # detect: Apps Script exposes no IP/headers to check
                # against). flagged_unexpected is always FALSE here for the
                # same reason -- never claim a check that isn't happening.
                viewed_ats = events_by_token.get(tracking_token, [])
                if not viewed_ats:
                    print("  No views recorded.")
                    continue
                for viewed_at in viewed_ats:
                    print("  {}  opened by {}".format(viewed_at, shared_with_email))
                    cur.execute(
                        """
                        INSERT INTO data_room_views (file_id, viewer_email, viewed_at, flagged_unexpected)
                        VALUES (%s, %s, %s, FALSE)
                        ON CONFLICT (file_id, viewed_at) DO NOTHING
                        """,
                        (file_row_id, shared_with_email, viewed_at),
                    )
                continue

            # Legacy fallback for any file granted before the tracker
            # existed (tracking_token IS NULL) -- Drive Activity, known
            # unreliable for personal Gmail viewers (see
            # workflows/DATA_ROOM_PROCEDURE.md), kept only so an old grant
            # isn't silently unreported.
            events = drive_client.list_view_activity(drive_file_id)
            if not events:
                print("  No views recorded.")
                continue
            for event in events:
                flagged = " ** UNEXPECTED VIEWER **" if not event["is_known_user"] else ""
                print("  {}  actor={}{}".format(event["timestamp"], event["actor_identifier"] or "unattributed", flagged))
                cur.execute(
                    """
                    INSERT INTO data_room_views (file_id, viewer_email, viewed_at, flagged_unexpected)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (file_id, viewed_at) DO NOTHING
                    """,
                    (file_row_id, event["actor_identifier"], event["timestamp"], not event["is_known_user"]),
                )


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    grant = sub.add_parser("grant")
    grant.add_argument("--investor-id", type=int, required=True)
    grant.add_argument("--tier", choices=["teaser", "standard", "full"], required=True)
    grant.add_argument("--email", required=True)
    grant.add_argument("--deck", required=True)
    grant.add_argument("--expiry-days", type=int, default=DEFAULT_EXPIRY_DAYS)

    sub.add_parser("report")

    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        sys.exit(1)

    with psycopg.connect(database_url, autocommit=True) as conn:
        if args.command == "grant":
            result = grant_access(conn, args.investor_id, args.tier, args.email, args.deck, args.expiry_days)
            print(result)
        elif args.command == "report":
            morning_report(conn)


if __name__ == "__main__":
    main()
