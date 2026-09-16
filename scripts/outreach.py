"""First-note drafting (agents/SPECIALISTS.md #2 OUTREACH).

Draft only -- this never sends, at any build stage. "Send stays manual" is
not a Stage 4 caveat, it is the whole design: the draft is always the last
automated step, a person always hits send.

Usage:
    python scripts/outreach.py draft --investor-id N --to email@fund.com --deck path/to/deck.pdf
    python scripts/outreach.py mark-sent --touch-id N
"""

import argparse
import os
import pathlib
import sys

import psycopg
from dotenv import load_dotenv

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import gmail_client  # noqa: E402
from outreach_templates import draft_first_note  # noqa: E402
from render_lib import load_facts  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


def draft_touch(conn, investor_id, to_email, deck_path, touch_number=1):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT firm_name, partner_name, capital_type, why_them, warm_path, do_not_contact, approved
            FROM investor_file WHERE id = %s
            """,
            (investor_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError("no investor_file row with id {}".format(investor_id))
        firm_name, partner_name, capital_type, why_them, warm_path, do_not_contact, approved = row

        if do_not_contact:
            raise ValueError("{} is on the do-not-contact list -- refusing to draft".format(firm_name))
        if capital_type == "local_angel_syndicate" and not warm_path:
            raise ValueError(
                "{} is a local/regional angel syndicate with no warm_path set -- ".format(firm_name)
                + "per IDENTITY.md, cold outreach converts poorly here. Find a warm intro first, "
                + "or set investor_file.warm_path explicitly if one exists."
            )
        if not approved:
            raise ValueError("{} is not approved yet -- founder must approve before Outreach drafts anything".format(firm_name))

        cur.execute("SELECT 1 FROM outreach_touches WHERE investor_id = %s AND touch_number = %s", (investor_id, touch_number))
        if cur.fetchone():
            raise ValueError("touch {} already exists for investor_id {} -- not re-drafting".format(touch_number, investor_id))

        fund = {"firm_name": firm_name, "partner_name": partner_name, "capital_type": capital_type, "why_them": why_them, "warm_path": warm_path}
        facts = load_facts(cur)
        subject, body = draft_first_note(fund, facts)

        gmail_draft = gmail_client.create_draft(to=to_email, subject=subject, body=body, attachment_path=deck_path)

        cur.execute(
            """
            INSERT INTO outreach_touches (investor_id, touch_number, template_capital_type, gmail_draft_id, draft_text, status)
            VALUES (%s, %s, %s, %s, %s, 'drafted') RETURNING id
            """,
            (investor_id, touch_number, capital_type, gmail_draft["id"], body),
        )
        touch_id = cur.fetchone()[0]

        cur.execute(
            "INSERT INTO activity_log (actor, action_type, entity_type, entity_id, details) VALUES (%s,%s,%s,%s,%s)",
            ("Outreach", "outbound_drafted", "outreach_touches", str(touch_id),
             '{{"firm": "{}", "capital_type": "{}", "touch_number": {}}}'.format(firm_name, capital_type, touch_number)),
        )

    return {"touch_id": touch_id, "gmail_draft_id": gmail_draft["id"], "subject": subject, "body": body}


def mark_sent(conn, touch_id):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE outreach_touches SET status = 'sent', sent_at = now() WHERE id = %s AND status = 'drafted' RETURNING investor_id",
            (touch_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError("no drafted outreach_touches row with id {}".format(touch_id))
        investor_id = row[0]
        cur.execute("UPDATE investor_file SET process_stage = 'contacted', last_touch_at = now() WHERE id = %s", (investor_id,))
        cur.execute(
            "INSERT INTO activity_log (actor, action_type, entity_type, entity_id, details) VALUES (%s,%s,%s,%s,%s)",
            ("Outreach", "outbound_sent", "outreach_touches", str(touch_id), '{"note": "founder sent the draft"}'),
        )
    return investor_id


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    d = sub.add_parser("draft")
    d.add_argument("--investor-id", type=int, required=True)
    d.add_argument("--to", required=True)
    d.add_argument("--deck", required=True)
    d.add_argument("--touch-number", type=int, default=1)

    m = sub.add_parser("mark-sent")
    m.add_argument("--touch-id", type=int, required=True)

    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        sys.exit(1)

    with psycopg.connect(database_url, autocommit=True) as conn:
        if args.command == "draft":
            result = draft_touch(conn, args.investor_id, args.to, args.deck, args.touch_number)
            print(result)
        elif args.command == "mark-sent":
            investor_id = mark_sent(conn, args.touch_id)
            print("investor_file.id={} moved to process_stage=contacted".format(investor_id))


if __name__ == "__main__":
    main()
