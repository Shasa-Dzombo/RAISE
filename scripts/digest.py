"""Idempotent report generation for the founder's daily and weekly reviews."""

import argparse
import datetime
import os
import pathlib

import psycopg
from dotenv import load_dotenv

from pipeline import render_weekly_review

ROOT = pathlib.Path(__file__).resolve().parent.parent


def generate_weekly_review(conn, period_end=None):
    period_end = period_end or datetime.date.today()
    period_start = period_end - datetime.timedelta(days=6)
    text = render_weekly_review(conn, datetime.datetime.combine(
        period_end, datetime.time.max, tzinfo=datetime.timezone.utc
    ))
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, report_text FROM pipeline_reviews
            WHERE review_period_start = %s AND review_period_end = %s
            ORDER BY created_at DESC LIMIT 1
            """,
            (period_start, period_end),
        )
        existing = cur.fetchone()
        if existing:
            return existing[0], existing[1]
        cur.execute(
            """
            INSERT INTO pipeline_reviews (review_period_start, review_period_end, report_text)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (period_start, period_end, text),
        )
        return cur.fetchone()[0], text


def generate_daily_digest(conn, as_of=None):
    as_of = as_of or datetime.datetime.now(datetime.timezone.utc)
    review = render_weekly_review(conn, as_of)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM activity_log
            WHERE actor = 'Manager' AND action_type = 'daily_digest_generated'
              AND entity_type = 'digest' AND entity_id = %s
            ORDER BY occurred_at DESC LIMIT 1
            """,
            (as_of.date().isoformat(),),
        )
        existing = cur.fetchone()
        if existing:
            return existing[0], review
        cur.execute(
            """
            INSERT INTO activity_log
                (actor, action_type, entity_type, entity_id, details)
            VALUES ('Manager', 'daily_digest_generated', 'digest', %s, %s)
            RETURNING id
            """,
            (as_of.date().isoformat(), '{"delivery": "founder_review_queue"}'),
        )
        return cur.fetchone()[0], review


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", choices=("daily", "weekly"))
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        report_id, text = (
            generate_daily_digest(conn)
            if args.report == "daily"
            else generate_weekly_review(conn)
        )
        print("report_id={}\n{}".format(report_id, text))


if __name__ == "__main__":
    main()
