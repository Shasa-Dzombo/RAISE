"""Calendar-truth Scheduler.

The Manager dispatch path automatically proposes slots for founder-approved
requests. Creating a Google Calendar hold remains an explicit founder action.
This module never accepts, refuses, or moves an already accepted meeting.
"""

import argparse
import datetime
import json
import os
import pathlib
import sys
from zoneinfo import ZoneInfo

import psycopg
from dotenv import load_dotenv

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import calendar_client  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_DURATION_MINUTES = 30
DEFAULT_HOLD_HOURS = 48


def _event_window(event):
    start = event.get("start", {}).get("dateTime")
    end = event.get("end", {}).get("dateTime")
    if not start and event.get("start", {}).get("date"):
        start = event["start"]["date"] + "T00:00:00+00:00"
        end = event["end"]["date"] + "T00:00:00+00:00"
    if not start or not end:
        return None
    return datetime.datetime.fromisoformat(start.replace("Z", "+00:00")), datetime.datetime.fromisoformat(end.replace("Z", "+00:00"))


def propose_slots(request_start, request_end, busy_events, blocks, duration_minutes=30):
    """Return slots in the founder's configured blocks, excluding busy events."""
    duration = datetime.timedelta(minutes=duration_minutes)
    busy = [window for event in busy_events if (window := _event_window(event))]
    slots = []
    cursor_date = request_start.date()
    while cursor_date <= request_end.date():
        weekday = cursor_date.weekday()
        for block in blocks:
            if block["weekday"] != weekday:
                continue
            tz = ZoneInfo(block["timezone"])
            block_start = datetime.datetime.combine(cursor_date, block["start_local"], tzinfo=tz).astimezone(datetime.timezone.utc)
            block_end = datetime.datetime.combine(cursor_date, block["end_local"], tzinfo=tz).astimezone(datetime.timezone.utc)
            candidate = max(block_start, request_start)
            while candidate + duration <= min(block_end, request_end):
                candidate_end = candidate + duration
                if not any(candidate < busy_end and candidate_end > busy_start for busy_start, busy_end in busy):
                    slots.append((candidate, candidate_end))
                candidate += duration
        cursor_date += datetime.timedelta(days=1)
    return slots


def create_request(conn, investor_id, thread_ref, email, timezone, request_text, founder_approval_required=True):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO scheduling_requests
                (investor_id, thread_ref, requested_by_email, requested_timezone,
                 request_text, founder_approval_required, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (thread_ref) DO UPDATE
            SET requested_by_email = COALESCE(scheduling_requests.requested_by_email, EXCLUDED.requested_by_email),
                request_text = COALESCE(scheduling_requests.request_text, EXCLUDED.request_text),
                updated_at = now()
            RETURNING id
            """,
            (
                 investor_id, thread_ref, email, timezone, request_text,
                 founder_approval_required,
                 "awaiting_founder" if founder_approval_required else "pending",
            ),
        )
        return cur.fetchone()[0]


def load_blocks(cur):
    cur.execute(
        """
        SELECT weekday, start_local, end_local, timezone
        FROM fundraising_calendar_blocks WHERE active = TRUE
        ORDER BY weekday, start_local
        """
    )
    return [
        {"weekday": row[0], "start_local": row[1], "end_local": row[2], "timezone": row[3]}
        for row in cur.fetchall()
    ]


def _record_escalation(cur, request_id, investor_id, thread_ref, reason):
    cur.execute(
        """
        INSERT INTO escalations
            (thread_ref, investor_id, escalation_type, reason, created_by)
        VALUES (%s, %s, 'scheduler_failure', %s, 'Scheduler')
        """,
        (thread_ref, investor_id, reason),
    )
    cur.execute(
        """
        INSERT INTO activity_log
            (actor, action_type, entity_type, entity_id, thread_ref, details)
        VALUES ('Scheduler', 'escalation', 'scheduling_requests', %s, %s, %s)
        """,
        (str(request_id), thread_ref, json.dumps({"reason": reason})),
    )


def propose_for_request(conn, request_id, days=7, duration_minutes=30, create_holds=False):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT investor_id, thread_ref, requested_by_email, requested_timezone,
                   founder_approval_required, status
            FROM scheduling_requests WHERE id = %s
            """,
            (request_id,),
        )
        request = cur.fetchone()
        if request is None:
            raise ValueError("no scheduling request with id {}".format(request_id))
        investor_id, thread_ref, recipient_email, recipient_timezone, approval_required, status = request
        if status not in ("awaiting_founder", "pending", "proposed"):
            raise ValueError("request {} is not schedulable in status {}".format(request_id, status))
        if recipient_timezone:
            ZoneInfo(recipient_timezone)
        if create_holds:
            raise ValueError("Calendar holds require founder selection through create_hold_for_slot")
        now = datetime.datetime.now(datetime.timezone.utc).replace(second=0, microsecond=0)
        end = now + datetime.timedelta(days=days)
        blocks = load_blocks(cur)
        if not blocks:
            _record_escalation(cur, request_id, investor_id, thread_ref, "No active fundraising calendar blocks are configured.")
            cur.execute(
                "UPDATE scheduling_requests SET status = 'escalated', updated_at = now() WHERE id = %s",
                (request_id,),
            )
            return []
        busy_events = calendar_client.list_events(now, end)
        slots = propose_slots(now, end, busy_events, blocks, duration_minutes)
        if not slots:
            _record_escalation(cur, request_id, investor_id, thread_ref, "No free slots were found inside the configured fundraising blocks.")
            cur.execute(
                "UPDATE scheduling_requests SET status = 'escalated', updated_at = now() WHERE id = %s",
                (request_id,),
            )
            return []
        for start, finish in slots[:5]:
            cur.execute(
                """
                SELECT 1 FROM scheduling_slots
                WHERE request_id = %s AND slot_start = %s AND slot_end = %s
                """,
                (request_id, start, finish),
            )
            if cur.fetchone():
                continue
            calendar_event = None
            slot_status = "proposed"
            if create_holds:
                calendar_event = calendar_client.create_hold(
                    start,
                    finish,
                    "RAISE fundraising hold",
                    "Tentative hold. Request {}. Release or confirm only through the founder workflow.".format(request_id),
                )
                slot_status = "held"
            cur.execute(
                """
                INSERT INTO scheduling_slots
                    (request_id, slot_start, slot_end, recipient_timezone,
                     calendar_event_id, status, hold_expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (request_id, slot_start, slot_end) DO NOTHING
                """,
                (
                    request_id, start, finish, recipient_timezone or "UTC",
                    calendar_event.get("id") if calendar_event else None,
                    slot_status,
                    start + datetime.timedelta(hours=DEFAULT_HOLD_HOURS),
                ),
            )
        cur.execute(
            "UPDATE scheduling_requests SET status = %s, updated_at = now() WHERE id = %s",
            ("held" if create_holds else "proposed", request_id),
        )
        return slots[:5]


def dispatch_pending_requests(conn, request_ids=None, days=7, duration_minutes=30):
    """Process founder-approved requests once; proposal generation is idempotent."""
    with conn.cursor() as cur:
        if request_ids:
            cur.execute(
                """
                SELECT id FROM scheduling_requests
                WHERE id = ANY(%s) AND status = 'pending'
                ORDER BY id
                """,
                (request_ids,),
            )
        else:
            cur.execute(
                """
                SELECT id FROM scheduling_requests
                WHERE status = 'pending'
                ORDER BY id
                """
            )
        request_ids_to_process = [row[0] for row in cur.fetchall()]

    results = []
    for request_id in request_ids_to_process:
        try:
            slots = propose_for_request(
                conn,
                request_id,
                days=days,
                duration_minutes=duration_minutes,
                create_holds=False,
            )
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO activity_log
                        (actor, action_type, entity_type, entity_id, thread_ref, details)
                    SELECT 'Scheduler', 'slots_proposed', 'scheduling_requests',
                           %s, thread_ref, %s
                    FROM scheduling_requests WHERE id = %s
                    """,
                    (str(request_id), json.dumps({"slot_count": len(slots)}), request_id),
                )
            results.append({"request_id": request_id, "status": "proposed", "slot_count": len(slots)})
        except Exception as exc:  # external Calendar/auth failures need an audit row
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT investor_id, thread_ref FROM scheduling_requests WHERE id = %s
                    """,
                    (request_id,),
                )
                row = cur.fetchone()
                if row:
                    _record_escalation(
                        cur,
                        request_id,
                        row[0],
                        row[1],
                        "Calendar/provider failure: {}".format(exc),
                    )
                    cur.execute(
                        """
                        UPDATE scheduling_requests
                        SET status = 'escalated', updated_at = now()
                        WHERE id = %s
                        """,
                        (request_id,),
                    )
            results.append({"request_id": request_id, "status": "escalated", "error": str(exc)})
    return results


def create_hold_for_slot(conn, slot_id):
    """Create exactly one tentative hold after a founder selects a proposal."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.request_id, s.slot_start, s.slot_end, s.status,
                   r.investor_id, r.thread_ref, r.founder_approval_required
            FROM scheduling_slots s
            JOIN scheduling_requests r ON r.id = s.request_id
            WHERE s.id = %s
            FOR UPDATE
            """,
            (slot_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError("no scheduling slot with id {}".format(slot_id))
        request_id, start, end, status, investor_id, thread_ref, approval_required = row
        if status != "proposed":
            raise ValueError("slot {} is not awaiting founder selection".format(slot_id))
        if approval_required:
            raise ValueError("founder approval is required before creating Calendar holds")
        try:
            event = calendar_client.create_hold(
                start,
                end,
                "RAISE fundraising hold",
                "Tentative hold. Request {}. Release or confirm only through the founder workflow.".format(request_id),
            )
        except Exception as exc:  # surface provider failures as an escalation
            _record_escalation(cur, request_id, investor_id, thread_ref, "Calendar hold failure: {}".format(exc))
            raise
        cur.execute(
            """
            UPDATE scheduling_slots
            SET status = 'held', calendar_event_id = %s,
                hold_expires_at = %s
            WHERE id = %s
            """,
            (event.get("id"), start + datetime.timedelta(hours=DEFAULT_HOLD_HOURS), slot_id),
        )
        cur.execute(
            """
            INSERT INTO activity_log
                (actor, action_type, entity_type, entity_id, thread_ref, details)
            VALUES ('founder', 'scheduling_hold_created', 'scheduling_slots', %s, %s, %s)
            """,
            (str(slot_id), thread_ref, json.dumps({"request_id": request_id, "calendar_event_id": event.get("id")})),
        )
    return slot_id


def expire_holds(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE scheduling_slots
            SET status = 'expired'
            WHERE status IN ('proposed', 'held')
              AND hold_expires_at IS NOT NULL
              AND hold_expires_at < now()
            RETURNING id, request_id
            """
        )
        expired = cur.fetchall()
        for slot_id, request_id in expired:
            cur.execute(
                "SELECT calendar_event_id FROM scheduling_slots WHERE id = %s",
                (slot_id,),
            )
            event_id = cur.fetchone()[0]
            if event_id:
                try:
                    calendar_client.release_hold(event_id)
                except Exception as exc:
                    _record_escalation(
                        cur,
                        request_id,
                        None,
                        None,
                        "Calendar hold release failure: {}".format(exc),
                    )
        cur.execute(
            """
            UPDATE scheduling_requests r
            SET status = 'expired', updated_at = now()
            WHERE r.id IN (SELECT request_id FROM scheduling_slots WHERE status = 'expired')
              AND NOT EXISTS (
                  SELECT 1 FROM scheduling_slots s
                  WHERE s.request_id = r.id AND s.status IN ('proposed', 'held', 'booked')
              )
            """
        )
        return expired


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("propose")
    p.add_argument("--request-id", type=int, required=True)
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--duration-minutes", type=int, default=DEFAULT_DURATION_MINUTES)
    d = sub.add_parser("dispatch")
    d.add_argument("--days", type=int, default=7)
    d.add_argument("--duration-minutes", type=int, default=DEFAULT_DURATION_MINUTES)
    sub.add_parser("expire")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is not set")
    with psycopg.connect(database_url, autocommit=True) as conn:
        if args.command == "propose":
            slots = propose_for_request(conn, args.request_id, args.days, args.duration_minutes)
            for start, end in slots:
                print("{} -> {}".format(start.isoformat(), end.isoformat()))
        elif args.command == "dispatch":
            print(json.dumps(dispatch_pending_requests(conn, days=args.days, duration_minutes=args.duration_minutes), default=str))
        else:
            print("Expired {} scheduling slot(s).".format(len(expire_holds(conn))))


if __name__ == "__main__":
    main()
