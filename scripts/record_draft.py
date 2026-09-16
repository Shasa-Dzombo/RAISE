"""Record the Gmail draft_id returned by create_draft against a drafts row.

Usage:
    python scripts/record_draft.py --draft-row-id N --gmail-draft-id <id>
"""

import argparse
import os
import pathlib
import sys

import psycopg
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft-row-id", required=True, type=int)
    parser.add_argument("--gmail-draft-id", required=True)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set. Copy .env.example to .env first.", file=sys.stderr)
        sys.exit(1)

    with psycopg.connect(database_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE drafts
                SET gmail_draft_id = %s, draft_created_at = now(), status = 'drafted', updated_at = now()
                WHERE id = %s
                RETURNING id
                """,
                (args.gmail_draft_id, args.draft_row_id),
            )
            row = cur.fetchone()
            if row is None:
                print(f"No drafts row with id {args.draft_row_id}", file=sys.stderr)
                sys.exit(1)

            cur.execute(
                """
                INSERT INTO activity_log (actor, action_type, entity_type, entity_id, details)
                VALUES (%s, %s, %s, %s, %s)
                """,
                ("Inbox", "outbound_drafted", "drafts", str(args.draft_row_id),
                 '{"gmail_draft_id": "%s"}' % args.gmail_draft_id),
            )

    print(f"Recorded gmail_draft_id={args.gmail_draft_id} on drafts.id={args.draft_row_id}")


if __name__ == "__main__":
    main()
