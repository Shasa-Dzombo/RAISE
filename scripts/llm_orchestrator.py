"""Standalone Stage 2 orchestrator, driven by an open-weights model instead
of a Claude Code session.

Runs the same procedure as workflows/STAGE2_PROCEDURE.md Procedure A, but the
loop deciding which tool to call next is an OpenAI-compatible tool-calling
model (OPEN_WEIGHT_BASE_URL) instead of Claude. Gmail access goes through
gmail_mcp_server.py (a self-hosted MCP server) via mcp_gmail_client.py --
the same server Claude Code can also be pointed at, so there is one Gmail
implementation instead of two.

Safety boundary: the tool list handed to the model is a closed set (defined
below). gmail_mcp_server.py exposes no send/reply tool at all, so there is
no tool the model could call, correctly or by mistake, that would send mail.
classify_thread's actual classification/rendering logic is unchanged --
still deterministic Python, not delegated to the model. The model's only
job is sequencing: which tool to call next, with what arguments, based on
the same handling-ladder rules given to it as a system prompt.

Usage:
    python scripts/llm_orchestrator.py --scope-label RAISE/stage2-test
"""

import argparse
import asyncio
import json
import os
import pathlib
import sys

import psycopg
from dotenv import load_dotenv
from openai import OpenAI

# Windows consoles default stdout to cp1252, which cannot encode characters
# some models emit (e.g. U+202F narrow no-break space). Force UTF-8 with
# replacement so a model's word choice can never crash the run.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from mcp_gmail_client import MCPGmailClient  # noqa: E402
from classify_thread import classify  # noqa: E402
from render_lib import check_question, load_facts  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent

BOOKKEEPING_LABELS = ["RAISE/drafted", "RAISE/escalated", "RAISE/locked", "RAISE/measured"]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_scope_threads",
            "description": "List thread IDs under the scope label that have not yet been processed (no bookkeeping label applied).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_thread",
            "description": "Fetch a thread's full messages (sender, date, plaintext body).",
            "parameters": {
                "type": "object",
                "properties": {"thread_id": {"type": "string"}},
                "required": ["thread_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "classify_and_maybe_draft",
            "description": (
                "Classify the newest message in a thread per the INBOX handling ladder. "
                "If safe, this ALSO creates the Gmail draft and records it -- it is the only "
                "path that can produce a draft. Returns the classification and what happened."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string"},
                    "target_message_id": {"type": "string"},
                },
                "required": ["thread_id", "target_message_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "label_thread",
            "description": "Apply a bookkeeping label to a thread (RAISE/drafted, RAISE/escalated, or RAISE/locked). Never removes the scope label.",
            "parameters": {
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string"},
                    "label": {"type": "string", "enum": BOOKKEEPING_LABELS},
                },
                "required": ["thread_id", "label"],
            },
        },
    },
]

SYSTEM_PROMPT = """You are the RAISE Inbox agent, running Stage 2: draft-only inbound handling.

Your only job each turn is to decide which tool to call next. You never see
or write raw email text yourself -- classify_and_maybe_draft does all
classification and drafting deterministically from the fact sheet; you only
sequence calls.

Procedure, for every thread returned by list_scope_threads:
  1. get_thread(thread_id) to see its messages.
  2. Pick the newest message as target_message_id.
  3. classify_and_maybe_draft(thread_id, target_message_id).
  4. Based on the returned classification, call label_thread once:
     - "known_question_draft" -> label "RAISE/drafted"
     - "thread_locked_skip" -> label "RAISE/locked"
     - anything else -> label "RAISE/escalated"

Rules with no exceptions:
- Only ever call the four tools you were given. There is no tool to send or
  reply to anything -- do not attempt to describe, draft, or output raw
  email text yourself under any circumstance.
- Never call label_thread with any label other than the three bookkeeping
  labels. Never attempt to remove the scope label.
- Process every thread list_scope_threads returns, then stop and summarize
  what happened -- how many drafted, escalated, locked. Do not invent
  threads or message IDs that were not returned by a tool call.
"""


def make_tool_impls(db_cur, founder_email, scope_label, label_ids, gmail):
    async def list_scope_threads():
        query = "label:{} -label:RAISE/drafted -label:RAISE/escalated -label:RAISE/locked".format(scope_label)
        threads = await gmail.search_threads(query)
        return {"thread_ids": [t["id"] for t in threads]}

    async def get_thread(thread_id):
        return await gmail.get_thread(thread_id)

    async def classify_and_maybe_draft(thread_id, target_message_id):
        thread = await gmail.get_thread(thread_id)
        target = next((m for m in thread["messages"] if m["id"] == target_message_id), None)
        if target is None:
            return {"error": "target_message_id not found in thread"}

        sender_email = None
        import re
        m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", target.get("sender", ""))
        if m:
            sender_email = m.group(0).lower()

        facts = load_facts(db_cur)
        db_cur.execute("SELECT id, question, answer_template FROM question_bank ORDER BY id")
        questions = [{"id": r[0], "question": r[1], "answer_template": r[2]} for r in db_cur.fetchall()]

        investor_row = None
        if sender_email:
            db_cur.execute(
                "SELECT id, firm_name, do_not_contact, partner_seniority FROM investor_file WHERE lower(partner_email) = %s",
                (sender_email,),
            )
            row = db_cur.fetchone()
            if row:
                investor_row = {"id": row[0], "firm_name": row[1], "do_not_contact": row[2], "partner_seniority": row[3]}

        decision = classify(thread, target_message_id, founder_email, investor_row, facts, questions)

        db_cur.execute(
            """
            INSERT INTO drafts (gmail_thread_id, gmail_message_id, investor_id, sender_email,
                sender_seniority, classification, question_id, match_score, draft_text, status, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
            """,
            (thread_id, target_message_id, investor_row["id"] if investor_row else None, sender_email,
             investor_row["partner_seniority"] if investor_row else "unknown", decision["classification"],
             decision.get("question_id"), decision.get("match_score"), decision.get("draft_text"),
             "not_drafted", decision.get("notes")),
        )
        draft_row_id = db_cur.fetchone()[0]

        if decision["classification"] == "known_question_draft":
            gmail_draft = await gmail.create_draft(
                to=sender_email or target.get("sender", ""),
                subject="Re: " + (thread.get("subject") or ""),
                body=decision["draft_text"],
                reply_to_message_id=target_message_id,
                thread_id=thread_id,
            )
            db_cur.execute(
                "UPDATE drafts SET gmail_draft_id=%s, draft_created_at=now(), status='drafted', updated_at=now() WHERE id=%s",
                (gmail_draft["id"], draft_row_id),
            )
            db_cur.execute(
                "INSERT INTO activity_log (actor, action_type, entity_type, entity_id, thread_ref, details) VALUES (%s,%s,%s,%s,%s,%s)",
                ("Inbox (open-weights)", "outbound_drafted", "drafts", str(draft_row_id), thread_id,
                 json.dumps({"gmail_draft_id": gmail_draft["id"], "model": os.environ.get("OPEN_WEIGHT_MODEL")})),
            )

        db_cur.execute(
            "INSERT INTO activity_log (actor, action_type, entity_type, entity_id, thread_ref, details) VALUES (%s,%s,%s,%s,%s,%s)",
            ("Inbox (open-weights)", "inbound_classified", "drafts", str(draft_row_id), thread_id,
             json.dumps({"classification": decision["classification"], "notes": decision.get("notes")})),
        )

        return {"classification": decision["classification"], "notes": decision.get("notes"), "draft_row_id": draft_row_id}

    async def label_thread(thread_id, label):
        if label not in label_ids:
            return {"error": "unknown bookkeeping label: {}".format(label)}
        await gmail.label_thread(thread_id, [label_ids[label]])
        return {"labeled": label}

    return {
        "list_scope_threads": list_scope_threads,
        "get_thread": get_thread,
        "classify_and_maybe_draft": classify_and_maybe_draft,
        "label_thread": label_thread,
    }


async def run(scope_label, max_turns=30):
    load_dotenv(ROOT / ".env")
    database_url = os.environ.get("DATABASE_URL")
    founder_email = os.environ.get("FOUNDER_EMAIL")
    open_weight_key = os.environ.get("OPEN_WEIGHT_API_KEY")
    open_weight_url = os.environ.get("OPEN_WEIGHT_BASE_URL")
    model = os.environ.get("OPEN_WEIGHT_MODEL", "gpt-oss:120b")

    missing = [n for n, v in [
        ("DATABASE_URL", database_url), ("FOUNDER_EMAIL", founder_email),
        ("OPEN_WEIGHT_API_KEY", open_weight_key), ("OPEN_WEIGHT_BASE_URL", open_weight_url),
    ] if not v]
    if missing:
        print("Missing env vars: " + ", ".join(missing), file=sys.stderr)
        sys.exit(1)

    client = OpenAI(api_key=open_weight_key, base_url=open_weight_url)

    async with MCPGmailClient() as gmail:
        scope_label_id = await gmail.get_or_create_label_id(scope_label)
        label_ids = {}
        for name in BOOKKEEPING_LABELS:
            label_ids[name] = await gmail.get_or_create_label_id(name)
        print("Scope label '{}' resolved to id {}".format(scope_label, scope_label_id))

        with psycopg.connect(database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                tool_impls = make_tool_impls(cur, founder_email, scope_label, label_ids, gmail)

                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": "Process every unhandled thread under the scope label now."},
                ]

                for turn in range(max_turns):
                    response = client.chat.completions.create(
                        model=model, messages=messages, tools=TOOLS, tool_choice="auto",
                    )
                    choice = response.choices[0]
                    messages.append(choice.message.model_dump(exclude_none=True))

                    if not choice.message.tool_calls:
                        print("\n[model] " + (choice.message.content or ""))
                        break

                    for tool_call in choice.message.tool_calls:
                        name = tool_call.function.name
                        try:
                            args = json.loads(tool_call.function.arguments or "{}")
                        except json.JSONDecodeError:
                            args = {}
                        print("[tool call] {}({})".format(name, args))

                        impl = tool_impls.get(name)
                        if impl is None:
                            result = {"error": "no such tool: {}".format(name)}
                        else:
                            try:
                                result = await impl(**args)
                            except Exception as exc:  # noqa: BLE001
                                result = {"error": str(exc)}

                        print("[tool result] {}".format(json.dumps(result)[:300]))
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result, default=str),
                        })
                else:
                    print("Hit max_turns ({}) without the model finishing on its own.".format(max_turns), file=sys.stderr)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope-label", default="RAISE/stage2-test")
    parser.add_argument("--max-turns", type=int, default=30)
    args = parser.parse_args()
    asyncio.run(run(args.scope_label, args.max_turns))


if __name__ == "__main__":
    main()
