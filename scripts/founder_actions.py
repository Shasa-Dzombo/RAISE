"""Founder-only write actions exposed to scripts/dashboard.py.

Deliberately narrow: only actions investor_file already treats as
founder-gated (approval / pass). Never touches Gmail or Drive, never
drafts or sends anything -- those stay script/CLI only, preserving "a
person hits send." Marking an outreach touch as sent reuses
outreach.mark_sent() directly rather than being duplicated here.
"""

import json

from scheduler import create_hold_for_slot, dispatch_pending_requests


def approve_investor(conn, investor_id):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE investor_file SET approved = TRUE, updated_at = now() WHERE id = %s RETURNING firm_name",
            (investor_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError("no investor_file row with id {}".format(investor_id))
        firm_name = row[0]
        cur.execute(
            "INSERT INTO activity_log (actor, action_type, entity_type, entity_id, details) VALUES (%s,%s,%s,%s,%s)",
            ("founder", "approval", "investor_file", str(investor_id),
             json.dumps({"firm": firm_name, "decision": "approved", "via": "dashboard"})),
        )
    return firm_name


def pass_investor(conn, investor_id, note=None):
    note_line = note or "Passed via dashboard."
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE investor_file
            SET process_stage = 'passed',
                updated_at = now(),
                notes = COALESCE(notes || E'\n', '') || %s
            WHERE id = %s RETURNING firm_name
            """,
            (note_line, investor_id),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError("no investor_file row with id {}".format(investor_id))
        firm_name = row[0]
        cur.execute(
            "INSERT INTO activity_log (actor, action_type, entity_type, entity_id, details) VALUES (%s,%s,%s,%s,%s)",
            ("founder", "approval", "investor_file", str(investor_id),
             json.dumps({"firm": firm_name, "decision": "passed", "via": "dashboard", "note": note_line})),
        )
    return firm_name


def approve_scheduling_request(conn, request_id):
    """Allow Scheduler to propose slots after an explicit founder decision."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE scheduling_requests
            SET founder_approval_required = FALSE,
                status = CASE WHEN status = 'awaiting_founder' THEN 'pending' ELSE status END,
                updated_at = now()
            WHERE id = %s
            RETURNING investor_id, thread_ref
            """,
            (request_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError("no scheduling request with id {}".format(request_id))
        cur.execute(
            """
            INSERT INTO activity_log
                (actor, action_type, entity_type, entity_id, details)
            VALUES ('founder', 'scheduling_approval', 'scheduling_requests', %s, %s)
            """,
            (str(request_id), json.dumps({"investor_id": row[0], "thread_ref": row[1]})),
        )
    dispatch_pending_requests(conn, [request_id])
    return request_id


def approve_scheduling_slot(conn, slot_id):
    """Create one tentative Calendar hold for a founder-selected proposal."""
    return create_hold_for_slot(conn, slot_id)


def release_scheduling_slot(conn, slot_id, note=None):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT request_id, calendar_event_id, status
            FROM scheduling_slots
            WHERE id = %s AND status IN ('proposed', 'held')
            FOR UPDATE
            """,
            (slot_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError("no active scheduling slot with id {}".format(slot_id))
        request_id, event_id, status = row
        if event_id:
            from scheduler import calendar_client
            calendar_client.release_hold(event_id)
        cur.execute(
            "UPDATE scheduling_slots SET status = 'released' WHERE id = %s",
            (slot_id,),
        )
        cur.execute(
            """
            INSERT INTO activity_log
                (actor, action_type, entity_type, entity_id, details)
            VALUES ('founder', 'scheduling_slot_released', 'scheduling_slots', %s, %s)
            """,
            (str(slot_id), json.dumps({"request_id": row[0], "note": note or ""})),
        )
    return slot_id
