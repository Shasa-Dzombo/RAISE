"""Classify one inbound Gmail message per the INBOX handling ladder
(agents/SPECIALISTS.md section 3) and, for the one safe case, produce a
fact-sheet-only draft reply. Never calls Gmail itself -- the calling Claude
Code session already fetched the thread via MCP and pipes it in as JSON;
if this script says to draft, the caller then calls create_draft.

Priority order (first match wins; see the plan for why):
  1. founder-lock       -- founder already replied after this message
  2. do-not-contact     -- sender/firm is on investor_file.do_not_contact
  3. legal/price/personal keyword hit
  4. question-bank match (renders via render_lib; if matched but unrenderable
     -- missing/stale fact -- falls through to unknown_question_escalate
     with the reason noted, never a partial/guessed draft)
  5. meeting-request keywords (only if no question matched)
  6. data-room-request keywords (only if no question matched, no meeting match)
  7. otherwise: unknown_question_escalate

Usage:
    python scripts/classify_thread.py --target-message-id <id> < thread.json
"""

import argparse
import json
import os
import pathlib
import re
import sys

import psycopg
from dotenv import load_dotenv

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from render_lib import check_question, load_facts  # noqa: E402
from question_match import all_matches  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent

LEGAL_PRICE_PERSONAL_KEYWORDS = [
    "valuation", "term sheet", "cap table", "dilution", "exclusiv",
    "no-shop", "no shop", "board seat", "signature", "counsel", "lawyer",
    "nda", "discount rate", "pre-money", "post-money", "sign the", "signing",
]

MEETING_KEYWORDS = [
    "set up a call", "schedule a call", "meet up", "meeting", "calendar",
    "what time works", "find time", "book a time", "hop on a call",
]

DATA_ROOM_KEYWORDS = [
    "data room", "due diligence materials", "diligence folder",
    "access to the data room", "share the data room", "cap table access",
]

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
NL2 = chr(10) + chr(10)


def extract_email(sender_field):
    match = EMAIL_RE.search(sender_field or "")
    return match.group(0).lower() if match else None


def contains_any(text, keywords):
    lowered = text.lower()
    return next((kw for kw in keywords if kw in lowered), None)


def classify(thread, target_message_id, founder_email, investor_row, facts, questions):
    messages = thread["messages"]
    target = next((m for m in messages if m["id"] == target_message_id), None)
    if target is None:
        raise SystemExit(f"target message {target_message_id} not found in thread")

    body = target.get("plaintextBody") or ""
    target_date = target["date"]

    # 1. founder-lock: did the founder send something in this thread AFTER
    # the message we're classifying?
    founder_replied_after = any(
        m.get("sender", "").lower().find(founder_email.lower()) != -1
        and m["date"] > target_date
        for m in messages
        if m["id"] != target_message_id
    )
    if founder_replied_after:
        return {"classification": "thread_locked_skip", "notes": "Founder already replied in this thread after this message."}

    # 2. do-not-contact
    if investor_row and investor_row.get("do_not_contact"):
        return {"classification": "do_not_contact_skip", "notes": f"Firm '{investor_row['firm_name']}' is on the do-not-contact list."}

    # 3. legal/price/personal
    hit = contains_any(body, LEGAL_PRICE_PERSONAL_KEYWORDS)
    if hit:
        return {"classification": "legal_price_personal_escalate", "notes": f"Message contains restricted keyword: '{hit}'."}

    # 4. question-bank match -- a real message can ask more than one thing
    matches = all_matches(body, [(q["id"], q["question"]) for q in questions])
    if matches:
        rendered_parts = []
        unrenderable_parts = []
        matched_ids = []
        for qid, qtext, score in matches:
            template = next(q["answer_template"] for q in questions if q["id"] == qid)
            result = check_question(template, facts)
            matched_ids.append(qid)
            if result["renderable"]:
                rendered_parts.append(result["rendered"])
            else:
                unrenderable_parts.append(
                    "question_bank #{} ({!r}): {}".format(
                        qid, qtext, "; ".join(result["findings"] + result["hygiene_errors"])
                    )
                )

        if rendered_parts:
            notes = "Matched question_bank {} (top score {:.3f}).".format(matched_ids, matches[0][2])
            if unrenderable_parts:
                notes += " Could not answer: " + "; ".join(unrenderable_parts)
            return {
                "classification": "known_question_draft",
                "question_id": matches[0][0],
                "match_score": round(matches[0][2], 3),
                "draft_text": NL2.join(rendered_parts),
                "notes": notes,
            }

        return {
            "classification": "unknown_question_escalate",
            "question_id": matches[0][0],
            "match_score": round(matches[0][2], 3),
            "notes": "Matched but cannot render safely: " + "; ".join(unrenderable_parts),
        }

    # 5. meeting request
    hit = contains_any(body, MEETING_KEYWORDS)
    if hit:
        return {"classification": "meeting_request_flag", "notes": f"Meeting-request keyword: '{hit}'. Scheduler isn't built yet (Stage 3+) -- founder should follow up."}

    # 6. data room request
    hit = contains_any(body, DATA_ROOM_KEYWORDS)
    if hit:
        return {"classification": "data_room_request_flag", "notes": f"Data-room-request keyword: '{hit}'. Data room isn't built yet (Stage 3+) -- founder should follow up."}

    # 7. fallback
    return {"classification": "unknown_question_escalate", "notes": "No question_bank match found above threshold."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-message-id", required=True)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL")
    founder_email = os.environ.get("FOUNDER_EMAIL")
    if not database_url or not founder_email:
        print("DATABASE_URL and FOUNDER_EMAIL must be set. Copy .env.example to .env first.", file=sys.stderr)
        sys.exit(1)

    thread = json.load(sys.stdin)
    target = next((m for m in thread["messages"] if m["id"] == args.target_message_id), None)
    if target is None:
        print(f"target message {args.target_message_id} not found in thread JSON", file=sys.stderr)
        sys.exit(1)
    sender_email = extract_email(target.get("sender", ""))

    with psycopg.connect(database_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            facts = load_facts(cur)

            cur.execute("SELECT id, question, answer_template FROM question_bank ORDER BY id")
            questions = [{"id": r[0], "question": r[1], "answer_template": r[2]} for r in cur.fetchall()]

            investor_row = None
            if sender_email:
                cur.execute(
                    "SELECT id, firm_name, do_not_contact, partner_seniority FROM investor_file WHERE lower(partner_email) = %s",
                    (sender_email,),
                )
                row = cur.fetchone()
                if row:
                    investor_row = {"id": row[0], "firm_name": row[1], "do_not_contact": row[2], "partner_seniority": row[3]}

            decision = classify(thread, args.target_message_id, founder_email, investor_row, facts, questions)

            cur.execute(
                """
                INSERT INTO drafts (
                    gmail_thread_id, gmail_message_id, investor_id, sender_email,
                    sender_seniority, classification, question_id, match_score,
                    draft_text, status, notes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    thread["id"], args.target_message_id,
                    investor_row["id"] if investor_row else None,
                    sender_email,
                    investor_row["partner_seniority"] if investor_row else "unknown",
                    decision["classification"],
                    decision.get("question_id"),
                    decision.get("match_score"),
                    decision.get("draft_text"),
                    "drafted" if decision["classification"] == "known_question_draft" else "not_drafted",
                    decision.get("notes"),
                ),
            )
            draft_row_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO activity_log (actor, action_type, entity_type, entity_id, thread_ref, details)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    "Inbox", "inbound_classified", "drafts", str(draft_row_id), thread["id"],
                    json.dumps({"classification": decision["classification"], "sender": sender_email, "notes": decision.get("notes")}),
                ),
            )

            if decision.get("question_id") and decision["classification"] == "known_question_draft":
                template = next(q["answer_template"] for q in questions if q["id"] == decision["question_id"])
                for field_key in check_question(template, facts)["placeholders"]:
                    cur.execute(
                        """
                        INSERT INTO activity_log (actor, action_type, entity_type, entity_id, thread_ref, details)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        ("Inbox", "number_quoted", "canon_facts", field_key, thread["id"],
                         json.dumps({"draft_row_id": draft_row_id, "value": facts[field_key]["value"]})),
                    )

    decision["draft_row_id"] = draft_row_id
    print(json.dumps(decision, indent=2))


if __name__ == "__main__":
    main()
