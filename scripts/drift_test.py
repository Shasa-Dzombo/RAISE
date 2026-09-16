"""Render every question_bank answer from canon_facts alone and report drift risk.

This is the Stage 1 gate: "numbers stop drifting across repeated tests." Answers
are templates ({{field_key}} placeholders) resolved at read time from
canon_facts, so a correctly-authored template cannot drift on its own -- it can
only be MISSING (fact not loaded yet) or STALE (fact past its refresh_by date).

Two classes of problem are reported:

  Template-hygiene errors (fail the run, exit code 1):
    - a raw number appears in a template outside a {{...}} placeholder
    - a template references a field_key that question_bank_facts links to but
      that does not exist in canon_facts at all

  Expected-at-this-stage findings (reported, do not fail the run):
    - MISSING: the field_key exists but canon_facts.value is still NULL
    - STALE: the field has a value but refresh_by has passed
    - NOT QUOTABLE: the field is marked agent_quotable = false and must never
      be cited in agent output

Usage:
    python scripts/drift_test.py
"""

import datetime
import os
import pathlib
import sys

import psycopg
from dotenv import load_dotenv

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from render_lib import check_question, load_facts  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> None:
    load_dotenv(ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set. Copy .env.example to .env first.", file=sys.stderr)
        sys.exit(1)

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            facts = load_facts(cur)

            cur.execute(
                "SELECT id, question, answer_template FROM question_bank ORDER BY id"
            )
            questions = cur.fetchall()

    print(f"RAISE drift test -- {datetime.datetime.now().isoformat(timespec='seconds')}")
    print("=" * 72)

    hygiene_error_count = 0
    missing_or_stale_count = 0
    pass_count = 0

    for qid, question, template in questions:
        result = check_question(template, facts)

        if result["hygiene_errors"]:
            hygiene_error_count += 1
            print(f"\n[TEMPLATE ERROR] Q{qid}: {question}")
            for err in result["hygiene_errors"]:
                print(f"    {err}")
            for finding in result["findings"]:
                print(f"    {finding}")
            continue

        if result["findings"]:
            missing_or_stale_count += 1
            print(f"\n[NOT SENDABLE] Q{qid}: {question}")
            for finding in result["findings"]:
                print(f"    {finding}")
            continue

        pass_count += 1
        print(f"\n[PASS] Q{qid}: {question}")
        print(f"    -> {result['rendered']}")

    print("\n" + "-" * 72)
    print(f"{len(questions)} questions checked")
    print(f"{pass_count} pass (fully sourced, fresh, sendable)")
    print(f"{missing_or_stale_count} not sendable (missing/stale/restricted fact -- expected before the fact sheet is loaded)")
    print(f"{hygiene_error_count} template-hygiene errors (raw numbers or dangling field references)")

    if hygiene_error_count > 0:
        print("\nFAIL: fix template-hygiene errors above before this counts as a clean Stage 1 run.")
        sys.exit(1)

    print("\nTemplate hygiene: OK. Re-run after loading facts -- rendered answers above must stay identical for the same inputs.")
    sys.exit(0)


if __name__ == "__main__":
    main()
