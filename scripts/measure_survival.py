"""Measure how much of each drafted reply survives to what was actually sent.

This is the literal Stage 2 exit gate: "Measure how much of each draft
survives. Stable at high survival."

Usage:
    python scripts/measure_survival.py --list-open
    python scripts/measure_survival.py --draft-row-id N --thread-json -   (reads thread JSON from stdin)
    python scripts/measure_survival.py --report
"""

import argparse
import difflib
import json
import os
import pathlib
import sys

import psycopg
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent


def list_open(cur):
    cur.execute(
        "SELECT id, gmail_thread_id, gmail_draft_id, draft_created_at FROM drafts "
        "WHERE status = 'drafted' ORDER BY draft_created_at"
    )
    rows = cur.fetchall()
    if not rows:
        print("No open drafts awaiting measurement.")
        return
    for row_id, thread_id, draft_id, created_at in rows:
        print(f"drafts.id={row_id}  thread={thread_id}  gmail_draft_id={draft_id}  drafted_at={created_at}")


def measure(cur, draft_row_id, thread, founder_email):
    cur.execute(
        "SELECT draft_text, draft_created_at, gmail_thread_id FROM drafts WHERE id = %s",
        (draft_row_id,),
    )
    row = cur.fetchone()
    if row is None:
        print(f"No drafts row with id {draft_row_id}", file=sys.stderr)
        sys.exit(1)
    draft_text, draft_created_at, thread_id = row

    sent_candidates = [
        m for m in thread["messages"]
        if m.get("sender", "").lower().find(founder_email.lower()) != -1
        and draft_created_at is not None
        and m["date"] > draft_created_at.isoformat()
    ]
    if not sent_candidates:
        print("No founder-authored message found after the draft was created yet. Nothing to measure.")
        return

    sent_message = sorted(sent_candidates, key=lambda m: m["date"])[0]
    sent_text = sent_message.get("plaintextBody") or ""

    score = difflib.SequenceMatcher(None, draft_text or "", sent_text).ratio()
    status = "sent_matched" if score >= 0.9 else "sent_diverged"

    cur.execute(
        """
        UPDATE drafts
        SET sent_message_id = %s, sent_text = %s, sent_at = %s,
            survival_score = %s, survival_method = 'difflib_ratio',
            measured_at = now(), status = %s, updated_at = now()
        WHERE id = %s
        """,
        (sent_message["id"], sent_text, sent_message["date"], round(score, 4), status, draft_row_id),
    )
    cur.execute(
        """
        INSERT INTO activity_log (actor, action_type, entity_type, entity_id, thread_ref, details)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        ("Inbox", "draft_survival_measured", "drafts", str(draft_row_id), thread_id,
         json.dumps({"survival_score": round(score, 4), "status": status})),
    )
    print(f"drafts.id={draft_row_id}  survival_score={score:.4f}  status={status}")


def report(cur):
    cur.execute(
        "SELECT status, count(*), avg(survival_score), min(survival_score), max(survival_score) "
        "FROM drafts WHERE status IN ('sent_matched', 'sent_diverged') GROUP BY status"
    )
    rows = cur.fetchall()
    cur.execute("SELECT avg(survival_score) FROM drafts WHERE survival_score IS NOT NULL")
    overall = cur.fetchone()[0]

    print("Draft survival report")
    print("=" * 40)
    if not rows:
        print("No measured drafts yet.")
        return
    for status, count, avg, mn, mx in rows:
        print(f"{status}: {count} drafts, avg={avg:.4f}, min={mn:.4f}, max={mx:.4f}")
    print()
    print(f"Overall average survival: {overall:.4f}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list-open", action="store_true")
    parser.add_argument("--draft-row-id", type=int)
    parser.add_argument("--thread-json", help="path to thread JSON, or '-' for stdin")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL")
    founder_email = os.environ.get("FOUNDER_EMAIL")
    if not database_url or not founder_email:
        print("DATABASE_URL and FOUNDER_EMAIL must be set.", file=sys.stderr)
        sys.exit(1)

    with psycopg.connect(database_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            if args.list_open:
                list_open(cur)
            elif args.report:
                report(cur)
            elif args.draft_row_id and args.thread_json:
                thread_raw = sys.stdin.read() if args.thread_json == "-" else pathlib.Path(args.thread_json).read_text()
                thread = json.loads(thread_raw)
                measure(cur, args.draft_row_id, thread, founder_email)
            else:
                parser.print_help()


if __name__ == "__main__":
    main()
