# RAISE — Fundraising Agent System

A manager-plus-specialists agent system for running a venture fundraise
across African and Africa-active capital markets: one shared Postgres
record everything reads from, eight specialist lanes (Scout, Outreach,
Inbox, Diligence, Data Room, Scheduler, Pipeline, Terms), and a hard rule
that no code path in this repo can send or reply to an email — a person
always hits send.

**Fastest way to see what's actually built and working right now:**

```bash
python scripts/dashboard.py
```

then open the local URL it prints. It's a read-only live view — pipeline
status per specialist, the real Postgres tables, and two interactive demos
(render a question_bank answer, classify a pasted message) — see
[Running the dashboard](#running-the-dashboard) below.

---

## What's built

| # | Specialist | Status | Notes |
|---|---|---|---|
| 1 | Scout | Built & verified | Researches funds, writes one-page notes to `investor_file`, needs founder approval |
| 2 | Outreach | Built & verified | Drafts first notes by capital type, never sends |
| 3 | Inbox | Built & verified | Classifies replies, drafts known-question answers, escalates everything else |
| 4 | Diligence | Partially built | `question_bank` + drift test exist; no standalone escalation-review script yet |
| 5 | Data Room | Built & verified, with a known gap | Drive folders/watermarking/restricted sharing work; per-viewer view-tracking does not (see [Known limitations](#known-limitations)) |
| 6 | Scheduler | Not built | — |
| 7 | Pipeline | Not built | `investor_file.process_stage` tracks stage, but no board/report script |
| 8 | Terms | Not built | — |

Inbox can run two ways: driven interactively (Claude reads Gmail via MCP
and calls `classify_thread.py`), or fully standalone via
`scripts/llm_orchestrator.py`, an open-weights model that sequences the
same four safe tools with zero drafting discretion of its own — see
[Running Inbox](#running-each-specialist).

---

## Architecture at a glance

- **Postgres is the single source of truth.** Every number any agent may
  ever write lives in `canon_facts`; every answer template in
  `question_bank` references it by `{{field_key}}`, never a raw number.
  `db/schema.sql` is one running file, applied whole by `init_db.py` — no
  migration framework.
- **Gmail access is unified behind one self-hosted MCP server**
  (`scripts/gmail_mcp_server.py`), so both an interactive Claude Code
  session and the standalone orchestrator drive the exact same
  implementation. It has no send/reply tool — not disallowed by
  instruction, the function does not exist in the codebase at all.
- **Drive access** (`scripts/drive_client.py`) shares one OAuth token with
  Gmail (`scripts/google_auth.py`), used only for the Data Room.
- **No framework.** Plain Python + `psycopg` + stdlib where possible. The
  one exception is `scripts/dashboard.py`, which uses Gradio because it's
  a UI.

---

## Prerequisites

- **Docker Desktop** (for Postgres — `pgvector/pgvector:pg16`, mapped to
  host port **5344**, not the Postgres default 5432)
- **Python 3.11+**
- A **Google account** to act as the founder's Gmail/Drive identity, and a
  **Google Cloud project** with OAuth credentials (see
  [Google OAuth setup](#google-oauth-setup) — needed for anything that
  touches Gmail or Drive, not for the database/dashboard alone)
- (Optional) an **open-weights API key** if you want to run the standalone
  Inbox orchestrator instead of driving it interactively

### Windows-specific notes

- Docker Desktop's engine can stop between reboots/sessions — if
  `docker compose up -d` or any script hangs on a DB connection, run
  `docker info` to check, and relaunch Docker Desktop if it errors.
- If you're using Git Bash, native Windows Python can't read Git Bash's
  POSIX-style paths (`/c/Users/...`). Use Windows-style paths
  (`C:\Users\...`) or `cd` into the directory first and use relative paths.
- Console output defaults to `cp1252` on Windows, which can throw
  `UnicodeEncodeError` on some model output. `llm_orchestrator.py` already
  reconfigures stdout to UTF-8 for this reason.

---

## Quickstart (local)

```bash
# 1. Install Python dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# edit .env: FOUNDER_EMAIL, and OPEN_WEIGHT_* only if you'll run the
# standalone orchestrator. DATABASE_URL already points at localhost:5344,
# matching docker-compose.yml -- change both together if you change either.

# 3. Start Postgres
docker compose up -d

# 4. Apply schema + seed data
python scripts/init_db.py

# 5. (Optional but recommended for a working demo) load pseudo test data
#    so canon_facts/question_bank actually render something
psql "$DATABASE_URL" -f db/seed_pseudo_fixture.sql
# or, without psql installed:
python -c "
import os, pathlib, psycopg
from dotenv import load_dotenv
load_dotenv('.env')
psycopg.connect(os.environ['DATABASE_URL'], autocommit=True).execute(
    pathlib.Path('db/seed_pseudo_fixture.sql').read_text()
)
"

# 6. Verify: every question_bank answer should render, nothing MISSING/STALE
python scripts/drift_test.py
```

At this point the database is fully set up and `scripts/dashboard.py`,
`scripts/add_investor.py`, `scripts/outreach.py draft` (against a fake
`--to`), and every other Postgres-only piece will work. Anything that
touches real Gmail or Drive needs the OAuth setup below first.

### Resetting the database

The DB is disposable and cheap to recreate from scratch:

```bash
docker compose down -v && docker compose up -d && python scripts/init_db.py
```

---

## Google OAuth setup

Needed once, before anything that calls Gmail or Drive
(`gmail_client.py`, `gmail_mcp_server.py`, `drive_client.py`,
`data_room.py`, `outreach.py`, `classify_thread.py` when run through the
real inbox).

1. In [Google Cloud Console](https://console.cloud.google.com/), create or
   pick a project, then **APIs & Services → Enable APIs**: enable the
   **Gmail API**, **Google Drive API**, and **Drive Activity API**
   individually — each is gated separately and gives a 403
   `accessNotConfigured` error with a direct enable-link until you do.
2. **APIs & Services → OAuth consent screen**: add the Gmail account
   you'll use as a **Test user** (unverified apps only allow listed test
   users to authenticate).
3. **APIs & Services → Credentials → Create Credentials → OAuth client
   ID**, type **Desktop app**. Download the client secret JSON, save it at
   the path in `GMAIL_CREDENTIALS_PATH` (default:
   `./gmail_oauth_client.json`, gitignored — never commit it).
4. Run the one-time consent flow:

   ```bash
   python scripts/gmail_client.py --auth
   ```

   This opens a browser, asks for consent, and caches a refresh token at
   `GMAIL_TOKEN_PATH` (default `./.gmail_token.json`, gitignored). Scopes
   requested: `gmail.readonly`, `gmail.compose`, `gmail.labels`,
   `gmail.modify`, `drive.file`, `drive.activity.readonly` —
   **`gmail.send` is never requested**, so sending mail is impossible at
   the OAuth layer, not just undocumented.

If you add a scope later (this happened once, adding `gmail.modify` after
`gmail.labels` alone turned out not to cover applying labels to messages),
delete `.gmail_token.json` and rerun `--auth` to redo consent with the
full scope list.

---

## Running the dashboard

```bash
python scripts/dashboard.py
```

Opens a local Gradio app (default `http://127.0.0.1:7860`, `share=False` —
never leaves your machine). Three tabs:

- **Pipeline Overview** — the table above, live, plus the most recent
  Outreach → Inbox → Data Room activity actually in Postgres.
- **Live Data Browser** — every table (`investor_file`, `canon_facts`,
  `question_bank`, `drafts`, `outreach_touches`, `data_room_*`,
  `activity_log`), read-only, with a Refresh button per table.
- **Interactive Demo** — render any `question_bank` answer against live
  `canon_facts`, or paste a message and run it through the real Inbox
  classifier. Both are pure reads: nothing is written to `drafts` or
  `activity_log` from this tab, ever (no `INSERT`/`UPDATE`/`DELETE`
  anywhere in `dashboard.py`).

Only needs Postgres running — no Gmail/Drive OAuth required to use it.

---

## Running each specialist

### Scout — find and approve funds

In practice this is normally driven interactively (Claude researches via
web search, then calls `add_investor()` from `scripts/add_investor.py`) —
see `workflows/SCOUT_PROCEDURE.md`. Every fact needs a `source` +
`source_date` or `add_investor` raises. Founder approval
(`investor_file.approved`) is required before Outreach will draft
anything to that firm.

### Outreach — first notes, never sent automatically

```bash
python scripts/outreach.py draft --investor-id 2 --to partner@fund.com --deck path/to/deck.pdf
python scripts/outreach.py mark-sent --touch-id 1   # after a human actually sends it
```

Refuses to draft: firms on `do_not_contact`, unapproved firms, and
`local_angel_syndicate` firms with no `warm_path` set (cold outreach is
explicitly the wrong move there).

### Inbox — classify a thread, interactively

```bash
python scripts/classify_thread.py --target-message-id <id> < thread.json
```

`thread.json` is a thread's messages (Claude fetches this via the
`raise-gmail` MCP server — see `.mcp.json` — then pipes it in). Full
procedure with label-scoping safety rules: `workflows/STAGE2_PROCEDURE.md`.

### Inbox — classify a thread, standalone (open-weights orchestrator)

```bash
# .env needs OPEN_WEIGHT_API_KEY / OPEN_WEIGHT_BASE_URL / OPEN_WEIGHT_MODEL set
python scripts/llm_orchestrator.py
```

Runs fully outside Claude Code, connecting to the same
`gmail_mcp_server.py` via `scripts/mcp_gmail_client.py`. The model's only
discretion is which of 4 tools to call next and in what order — actual
drafting is always deterministic Python, never model-generated text.

### Data Room — grant and check access

```bash
python scripts/data_room.py grant --investor-id 2 --tier teaser --email partner@fund.com --deck path/to/deck.pdf
python scripts/data_room.py report
```

`full` tier refuses unless `investor_file.approved = TRUE`. See
`workflows/DATA_ROOM_PROCEDURE.md`, including the
[known view-tracking gap](#known-limitations).

### Drift test — the Stage-1 correctness check

```bash
python scripts/drift_test.py
```

Renders every `question_bank` answer from `canon_facts` and flags
anything unsourced, stale (past `refresh_by`), not agent-quotable, or
containing a raw number outside a `{{field_key}}` placeholder.

---

## Safety model (read this if you're extending the code)

- **Send/reply capability does not exist in this codebase.**
  `gmail_client.py` has no `send`/`reply`/`forward` function defined, full
  stop — not a rule an agent could route around, a function that isn't
  there. `gmail_mcp_server.py` wraps only the safe subset. The OAuth scope
  list never requests `gmail.send`.
- **Real-world testing uses safe recipients only** — the founder's own
  email standing in for a fund, never a guessed or scraped investor
  contact address.
- **Gmail automation is label-scoped**: every `search_threads` call in the
  Stage 2 procedure must start with `label:RAISE/stage2-test`, narrowed
  further, never broadened.
- **Every number traces to `canon_facts`.** No template anywhere contains
  a raw digit outside a `{{field_key}}` placeholder — enforced by
  `render_lib.check_question`'s hygiene check, used by `drift_test.py`,
  `classify_thread.py`, and `outreach_templates.py` alike.
- **`scripts/dashboard.py` is read-only against everything** — see
  [Running the dashboard](#running-the-dashboard) above.

---

## Known limitations

- **Data Room view-tracking does not work for personal Gmail viewers.**
  Confirmed live against both a PDF and a native Google Doc — Drive
  Activity API simply doesn't emit a VIEW record for a non-Workspace
  consumer account, regardless of file type. Folder/watermark/restricted-
  share mechanics are fully verified working; the view log
  (`data_room.py report`) is not currently a trustworthy signal. Full
  detail and a considered (and paused, on cost/infra grounds) alternative
  in `workflows/DATA_ROOM_PROCEDURE.md`.
- **Diligence, Scheduler, Pipeline, Terms** have no dedicated scripts yet
  — see the status table above.
- **Question matching** (`scripts/question_match.py`) is a token-overlap
  heuristic, not semantic — `question_bank.embedding` exists and is unused,
  ready for a future upgrade.

---

## Project structure

```
identity/
  SOUL.md, IDENTITY.md    Why the system exists, hard stops
  USER.md                 About the company (currently pseudo test data --
                           Mazao Analytics -- except FOUNDER_EMAIL, which is real)
  VOICE.md                Founder voice style guide, derived from real sent mail

agents/
  MANAGER.md               The router; never does work itself
  SPECIALISTS.md            All 8 specialist prompts, one lane each

workflows/
  WORKFLOWS.md              Shared record schema, event flows, build order
  STAGE2_PROCEDURE.md        Inbox: safety scoping + procedure
  SCOUT_PROCEDURE.md         Scout: sources + procedure
  DATA_ROOM_PROCEDURE.md     Data Room: procedure + known limitations

db/
  schema.sql                 One running schema file (no migrations)
  seed.sql                   Required field_keys + starter question bank
  seed_pseudo_fixture.sql    Optional: pseudo company data so things render

scripts/
  init_db.py                 Applies schema.sql + seed.sql
  dashboard.py                Read-only Gradio dashboard (see above)
  render_lib.py               Shared canon_facts template rendering + hygiene checks
  drift_test.py                Stage-1 correctness gate
  question_match.py            Token-overlap question matcher
  classify_thread.py           Inbox handling ladder (interactive)
  record_draft.py, measure_survival.py   Stage-2 draft-survival measurement
  add_investor.py              Scout's insert helper
  outreach_templates.py, outreach.py     Outreach drafting (4 templates by capital type)
  google_auth.py               Shared Gmail+Drive OAuth
  gmail_client.py               Direct Gmail API client (no send/reply, ever)
  gmail_mcp_server.py            Self-hosted MCP server wrapping gmail_client.py
  mcp_gmail_client.py            Standalone async MCP client (for the orchestrator)
  llm_orchestrator.py            Standalone open-weights Inbox orchestrator
  drive_client.py, watermark_pdf.py, data_room.py   Data Room (Google Drive-backed)
  generate_pseudo_deck.py        Generates a throwaway pseudo teaser PDF for testing
  voice_stats.py                 One-time founder voice study helper
```

---

## Build order

Each stage has a gate; the intent is not to skip ahead until the prior
stage's gate is actually met (this repo has, at points, jumped ahead of
strict order by explicit choice -- that's a deliberate tradeoff, not the
default recommendation):

1. **Shared record** — canon facts sourced and dated, story pack signed.
2. **Inbox, draft-only** — a person hits send; measure how much of each
   draft survives to what's actually sent.
3. **Data Room** — folders, watermarking, restricted per-firm access.
4. **Outreach** — first notes and follow-ups, still draft-only.
5. **Unattended send** — only safe once 1–4 have proven the numbers hold.

## Still needed from you

`identity/USER.md` still carries pseudo test data (Mazao Analytics) in
most fields, deliberately, so the system can be exercised end to end.
Before using this for a real fundraise, replace every field with your
own: company name/one-liner/sector/stage/amount, incorporation and HQ
jurisdiction, markets operating in vs. targeting, which capital types to
include, the real do-not-contact list, live threads the agent must never
touch, real tooling connections, working languages, and which build-order
stage to actually start at.

## The rules that cannot slip

- Numbers come from the fact sheet or they do not get written.
- A thread the founder already answered is locked.
- Partners get a path to a person.
- The calendar is the source of truth.
- Legal language, price, and signatures never leave the draft queue.
