"""Apply db/schema.sql and db/seed.sql to DATABASE_URL.

Usage:
    python scripts/init_db.py
"""

import os
import pathlib
import sys

import psycopg
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> None:
    load_dotenv(ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set. Copy .env.example to .env first.", file=sys.stderr)
        sys.exit(1)

    schema_sql = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    seed_sql = (ROOT / "db" / "seed.sql").read_text(encoding="utf-8")

    with psycopg.connect(database_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            print("Applying db/schema.sql ...")
            cur.execute(schema_sql)
            print("Applying db/seed.sql ...")
            cur.execute(seed_sql)

    print("Done.")


if __name__ == "__main__":
    main()
