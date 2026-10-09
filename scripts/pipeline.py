"""Behavioral Pipeline station.

Pipeline derives board views from investor_file plus immutable pipeline_events.
It never contacts firms and never makes the founder's pass/drop decision.
"""

import argparse
import datetime
import json
import os
import pathlib
import sys

import psycopg
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
STAGES = (
    "target", "contacted", "replied", "diligence", "term_sheet",
    "closed_won", "closed_lost", "passed", "do_not_contact",
)


def record_event(conn, investor_id, event_type, to_stage=None, heat_after=None,
                 source_entity_type=None, source_entity_id=None, evidence=None,
                 recorded_by="Pipeline"):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT process_stage, heat FROM investor_file WHERE id = %s FOR UPDATE",
            (investor_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError("no investor_file row with id {}".format(investor_id))
        from_stage, heat_before = row
        if to_stage is not None and to_stage not in STAGES:
            raise ValueError("invalid pipeline stage {}".format(to_stage))
        cur.execute(
            """
            INSERT INTO pipeline_events
                (investor_id, event_type, from_stage, to_stage, heat_before,
                 heat_after, source_entity_type, source_entity_id, evidence, recorded_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                investor_id, event_type, from_stage, to_stage, heat_before,
                heat_after, source_entity_type, source_entity_id,
                json.dumps(evidence or {}), recorded_by,
            ),
        )
        event_id = cur.fetchone()[0]
        if to_stage is not None or heat_after is not None:
            cur.execute(
                """
                UPDATE investor_file
                SET process_stage = COALESCE(%s, process_stage),
                    heat = COALESCE(%s, heat),
                    updated_at = now()
                WHERE id = %s
                """,
                (to_stage, heat_after, investor_id),
            )
        return event_id


def board(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, firm_name, capital_type, process_stage, heat,
                   last_touch_at, next_action, next_action_due
            FROM investor_file ORDER BY process_stage, next_action_due NULLS LAST, firm_name
            """
        )
        return cur.fetchall()


def behavioral_review(conn, as_of=None, stale_days=14):
    as_of = as_of or datetime.datetime.now(datetime.timezone.utc)
    cutoff = as_of - datetime.timedelta(days=stale_days)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.id, i.firm_name, i.process_stage, i.heat,
                   i.last_touch_at, i.next_action, i.next_action_due,
                   count(DISTINCT q.id) AS questions,
                   count(DISTINCT v.id) FILTER (WHERE v.confirmed) AS confirmed_views,
                   count(DISTINCT s.id) FILTER (WHERE s.status IN ('booked', 'held')) AS meetings,
                   count(DISTINCT pe.id) FILTER (WHERE pe.event_type = 'partner_involvement') AS partner_events
            FROM investor_file i
            LEFT JOIN question_bank_asked_by q ON q.investor_id = i.id
            LEFT JOIN data_room_links l ON l.investor_id = i.id AND l.revoked_at IS NULL
            LEFT JOIN data_room_files f ON f.link_id = l.id
            LEFT JOIN data_room_views v ON v.file_id = f.id
            LEFT JOIN scheduling_requests r ON r.investor_id = i.id
            LEFT JOIN scheduling_slots s ON s.request_id = r.id
            LEFT JOIN pipeline_events pe ON pe.investor_id = i.id
            WHERE i.process_stage NOT IN ('closed_won', 'closed_lost', 'passed', 'do_not_contact')
            GROUP BY i.id, i.firm_name, i.process_stage, i.heat,
                     i.last_touch_at, i.next_action, i.next_action_due
            ORDER BY i.last_touch_at NULLS FIRST
            """
        )
        rows = cur.fetchall()
    review = []
    for row in rows:
        investor_id, firm, stage, heat, last_touch, next_action, due, questions, views, meetings, partner_events = row
        reasons = []
        if last_touch is None or last_touch < cutoff:
            reasons.append("stalled: no recent touch")
        if due and due < as_of.date():
            reasons.append("overdue next action")
        if questions:
            reasons.append("{} diligence question(s)".format(questions))
        if views:
            reasons.append("{} confirmed data-room view(s)".format(views))
        if meetings:
            reasons.append("{} meeting hold/booked event(s)".format(meetings))
        if partner_events:
            reasons.append("{} partner involvement event(s)".format(partner_events))
        review.append({
            "investor_id": investor_id,
            "firm_name": firm,
            "stage": stage,
            "heat": heat,
            "next_action": next_action,
            "evidence": reasons,
            "stalled": any(reason.startswith(("stalled", "overdue")) for reason in reasons),
        })
    return review


def render_weekly_review(conn, as_of=None):
    review = behavioral_review(conn, as_of=as_of)
    lines = ["RAISE — weekly pipeline review", "", "FIRMS BY BEHAVIOUR"]
    for item in review:
        evidence = "; ".join(item["evidence"]) or "no recorded engagement signal"
        recommendation = "FOUNDER REVIEW: consider drop" if item["stalled"] else "retain for review"
        lines.append("- {} [{} / {}] — {}; {}".format(
            item["firm_name"], item["stage"], item["heat"] or "unheated",
            evidence, recommendation,
        ))
    lines.extend([
        "",
        "No recommendation changes a stage or contacts a firm automatically.",
        "Founder decides every pass/drop action.",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("board")
    sub.add_parser("weekly-review")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        if args.command == "board":
            for row in board(conn):
                print(row)
        else:
            print(render_weekly_review(conn))


if __name__ == "__main__":
    main()
