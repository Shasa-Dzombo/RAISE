# STAGE 2 PROCEDURE

Step-by-step for "Inbox drafts only. A person hits send. Measure how much of
each draft survives." Read `identity/VOICE.md` first (the founder voice
study must be done and confirmed before any of this runs) and the safety
scoping rules below before running any step.

---

## Two consumers, one Gmail implementation

`scripts/gmail_mcp_server.py` is the single source of truth for Gmail
access, exposed over MCP (stdio). It has no send/reply tool -- that
function does not exist anywhere in this codebase.

- **Claude Code** (this file's Procedure A/B, run manually or on request):
  connects via `.mcp.json` (server name `raise-gmail`).
- **The standalone open-weights orchestrator** (`scripts/llm_orchestrator.py`):
  connects via `scripts/mcp_gmail_client.py`, an async MCP client.

Both talk to the exact same server process definition, so there is one
Gmail integration to maintain, not two. Before this unification, Claude
used Anthropic's separately-hosted "Claude for Gmail" connector and the
open-weights orchestrator used a direct-API client (`scripts/gmail_client.py`,
which `gmail_mcp_server.py` now wraps) -- two paths that could drift apart.

---

## Safety scoping -- read this before anything else

**Label:** `RAISE/stage2-test` -- applied manually by the founder to any
thread opted into testing. Nothing else defines scope.

**Bookkeeping labels:** `RAISE/drafted`, `RAISE/escalated`, `RAISE/locked`,
`RAISE/measured`.

**Hard constraints, no exceptions:**
- Every `search_threads` query must begin with `label:RAISE/stage2-test`,
  only ever narrowed further, never broadened or replaced.
- `get_thread` / `get_message` / `get_draft` only ever called with an ID that
  came from a `label:RAISE/stage2-test`-filtered search earlier in the same
  run.
- `create_draft` only ever called with `replyToMessageId` set to a message ID
  obtained the same way, and only for a `known_question_draft` classification.
- `label_thread` only ever adds the bookkeeping labels above; never removes
  `RAISE/stage2-test` itself.
- **Never call:** `reply`, `send_message`, `forward`, `trash_message`,
  `trash_thread`, `mark_message_spam`, `mark_thread_spam`,
  `unlabel_thread`/`unlabel_message` (except a human-approved bookkeeping
  correction), `update_message_labels`, `delete_label`.

---

## Procedure A: process one new inbound thread

1. `list_labels()` -- confirm `RAISE/stage2-test` exists (and the four
   bookkeeping labels). Create any missing ones via `create_label`. Stop and
   ask the founder if `RAISE/stage2-test` itself doesn't exist.
2. `search_threads(query="label:RAISE/stage2-test -label:RAISE/drafted -label:RAISE/escalated -label:RAISE/locked")`.
3. For each thread returned: `get_thread(threadId, messageFormat=PLAIN_TEXT)`.
4. Identify the target message (the newest message needing a decision) and
   pipe the thread JSON into:
   `python scripts/classify_thread.py --target-message-id <id>`
5. Read the JSON decision printed to stdout:
   - `known_question_draft` -> `create_draft(replyToMessageId=<id>, subject="Re: ...", body=<decision.draft_text>)`,
     then `python scripts/record_draft.py --draft-row-id <decision.draft_row_id> --gmail-draft-id <id>`,
     then `label_thread(threadId, ["RAISE/drafted"])`.
   - `thread_locked_skip` -> `label_thread(threadId, ["RAISE/locked"])`, no
     Gmail mutation beyond that.
   - anything else (`unknown_question_escalate`, `legal_price_personal_escalate`,
     `meeting_request_flag`, `data_room_request_flag`, `do_not_contact_skip`)
     -> `label_thread(threadId, ["RAISE/escalated"])`, surface the reason to
     the founder directly (no Slack digest yet -- not authorized).

## Procedure B: measure survival for drafted items

1. `python scripts/measure_survival.py --list-open`
2. For each open draft: `get_thread(threadId, messageFormat=PLAIN_TEXT)` to
   check for a founder-authored message after `draft_created_at`, then:
   `python scripts/measure_survival.py --draft-row-id <id> --thread-json -`
   (thread JSON piped on stdin), then `label_thread(threadId, ["RAISE/measured"])`.
3. `python scripts/measure_survival.py --report` for the aggregate survival
   number -- this is the literal Stage 2 exit gate.

---

## Known limitations (first pass -- tune once more real data exists)

- Question matching is a simple token-overlap-coefficient heuristic
  (`scripts/question_match.py`), not semantic. It requires a minimum of 2
  overlapping non-stopword tokens plus a 0.5 overlap-coefficient score, to
  avoid one generic shared word (e.g. "current") falsely matching an
  unrelated short question. Confirmed against one real test message during
  build: initially under-matched with a pure Jaccard score, then over-matched
  once switched to overlap coefficient alone, until the minimum-overlap-count
  guard was added. Expect to keep tuning this against real inbound mail.
- A message asking several questions at once gets ALL of them answered in one
  combined draft (each independently rendered and safe), not split into
  separate replies.
- The legal/price/personal, meeting-request, and data-room keyword lists in
  `classify_thread.py` are a first-pass draft, not founder-reviewed.
- Meeting and data-room requests are only flagged, never acted on (Scheduler
  and Data Room are Stage 3+).
