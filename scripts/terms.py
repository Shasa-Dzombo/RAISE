"""Terms safety lane: preserve offers and compare only explicit fields.

The parser is deliberately conservative. It does not infer valuation,
dilution, or economic meaning; it only presents captured text side by side.
"""

import argparse
import json
import os
import pathlib

import psycopg
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent


def compare_offers(conn, investor_ids):
    placeholders = ",".join(["%s"] * len(investor_ids))
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, investor_id, thread_ref, raw_text, detected_at, status
            FROM term_offers
            WHERE investor_id IN ({})
            ORDER BY detected_at
            """.format(placeholders),
            tuple(investor_ids),
        )
        rows = cur.fetchall()
    return [
        {
            "offer_id": row[0],
            "investor_id": row[1],
            "thread_ref": row[2],
            "raw_text": row[3],
            "detected_at": row[4],
            "status": row[5],
        }
        for row in rows
    ]


def render_neutral_comparison(offers):
    lines = [
        "RAISE — neutral offer record",
        "",
        "This is a source-text comparison for founder and counsel.",
        "It is not a valuation, dilution, legal, or negotiation recommendation.",
        "",
    ]
    for offer in offers:
        lines.extend([
            "Offer #{} (investor_file.id={}) — {}".format(
                offer["offer_id"], offer["investor_id"], offer["status"]
            ),
            "Detected: {}".format(offer["detected_at"]),
            "Thread: {}".format(offer["thread_ref"]),
            "Captured text:",
            offer["raw_text"],
            "",
        ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--investor-id", action="append", type=int, required=True)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        print(render_neutral_comparison(compare_offers(conn, args.investor_id)))
