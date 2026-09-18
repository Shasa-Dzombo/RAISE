"""Founder-only write actions exposed to scripts/dashboard.py.

Deliberately narrow: only actions investor_file already treats as
founder-gated (approval / pass). Never touches Gmail or Drive, never
drafts or sends anything -- those stay script/CLI only, preserving "a
person hits send." Marking an outreach touch as sent reuses
outreach.mark_sent() directly rather than being duplicated here.
"""

import json


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
