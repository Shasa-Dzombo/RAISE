"""Insert or update one investor_file row from a researched Scout note.

Every field that came from research must carry `source` + `source_date` --
this script does not enforce that at the DB level (source/source_date are
nullable, since some fields like process_stage are internal, not researched)
but Scout's own rule (agents/SPECIALISTS.md #1: "Every claim about a fund
carries a source and date") means the caller must have one before calling
this for any researched fact.

Usage: import and call add_investor(**fields), or run as a CLI with a JSON
file: python scripts/add_investor.py fund.json
"""

import json
import os
import pathlib
import sys

import psycopg
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent

FIELDS = [
    "firm_name", "partner_name", "partner_email", "capital_type", "thesis",
    "check_size_min", "check_size_max", "check_size_currency", "domicile",
    "deployment_markets", "domicile_blocker", "warm_path", "working_language",
    "heat", "source", "source_date", "notes", "stage_fit",
    "portfolio_examples", "conflicts", "why_them", "partner_seniority",
]


def add_investor(conn, **fields):
    unknown = set(fields) - set(FIELDS)
    if unknown:
        raise ValueError("unknown investor_file fields: {}".format(unknown))
    if "firm_name" not in fields or "capital_type" not in fields:
        raise ValueError("firm_name and capital_type are required")
    if not fields.get("source") or not fields.get("source_date"):
        raise ValueError(
            "source and source_date are required -- Scout's rule: "
            "every claim about a fund carries a source and date"
        )

    cols = list(fields.keys())
    placeholders = ", ".join(["%s"] * len(cols))
    col_list = ", ".join(cols)
    update_clause = ", ".join("{0} = EXCLUDED.{0}".format(c) for c in cols if c not in ("firm_name",))

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO investor_file ({cols}, updated_at)
            VALUES ({placeholders}, now())
            ON CONFLICT (firm_name, COALESCE(partner_email, '')) DO UPDATE SET
                {update_clause}, updated_at = now()
            RETURNING id
            """.format(cols=col_list, placeholders=placeholders, update_clause=update_clause),
            [fields[c] for c in cols],
        )
        row_id = cur.fetchone()[0]

        cur.execute(
            "INSERT INTO activity_log (actor, action_type, entity_type, entity_id, details) VALUES (%s,%s,%s,%s,%s)",
            ("Scout", "investor_added", "investor_file", str(row_id),
             json.dumps({"firm_name": fields["firm_name"], "source": fields.get("source"), "source_date": str(fields.get("source_date"))})),
        )
    return row_id


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/add_investor.py <fund.json>", file=sys.stderr)
        sys.exit(1)

    load_dotenv(ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        sys.exit(1)

    fields = json.loads(pathlib.Path(sys.argv[1]).read_text())
    with psycopg.connect(database_url, autocommit=True) as conn:
        row_id = add_investor(conn, **fields)
    print("investor_file.id={}: {}".format(row_id, fields["firm_name"]))


if __name__ == "__main__":
    main()
