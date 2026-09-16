# RAISE -- Fundraising Agent System

A manager-plus-specialists agent system for running a venture fundraise across
African and Africa-active capital markets, structured using the identity-file
and manager-agent pattern.

---

## Files

```
identity/
  SOUL.md        Why the system exists, five commitments, hard stops
  IDENTITY.md    What RAISE is, eight stations, autonomy ladder, Africa knowledge
  USER.md        About you and the company -- HAS PLACEHOLDERS TO FILL
  VOICE.md       (created after the voice study)

agents/
  MANAGER.md     The router. Never does work. Runs pre-send checks.
  SPECIALISTS.md All eight specialist prompts, one lane each

workflows/
  WORKFLOWS.md   Shared record schema, event flows, kill switches, build order

db/
  schema.sql     Postgres + pgvector DDL for the shared record (Stage 1)
  seed.sql       Required field_keys and starter question bank -- no invented facts

scripts/
  init_db.py     Applies schema.sql and seed.sql to DATABASE_URL
  drift_test.py  Renders every question_bank answer from canon_facts and flags
                 anything unsourced, stale, or containing a raw (non-templated) number
```

---

## Setup order

1. Fill `identity/USER.md`. Every `[FILL]` marker. RAISE refuses to send while a
   `[FILL]` remains in a section it needs. The do-not-contact list and live-threads
   table matter most -- those prevent the failure that costs meetings.

2. Build the shared record. Canon facts with source and date on every field.
   Story pack, founder-signed. This comes before any agent runs.

3. Load 40 expected questions and correct answers until numbers stop drifting.
   Nothing goes out during this stage.

4. Run the voice study (prompt in `workflows/WORKFLOWS.md`). Iterate until clean.

5. Advance the build order one stage at a time. Each stage has a gate. Do not
   skip -- stage 5 unattended send is only safe because stages 1-4 proved the
   numbers hold.

---

## Running the Stage 1 database

```bash
docker compose up -d
cp .env.example .env      # then set DATABASE_URL if not using the default
pip install -r requirements.txt
python scripts/init_db.py
python scripts/drift_test.py
```

`drift_test.py` should report every seeded question as MISSING until real
canon facts are loaded -- that is the correct Stage 1 state. Load facts, add
questions, and re-run until nothing drifts.

---

## How to run the agents

Load `identity/SOUL.md`, `identity/IDENTITY.md`, and `identity/USER.md` as
persistent context. Then load `agents/MANAGER.md` as the routing agent. The
Manager spins up specialists from `agents/SPECIALISTS.md` -- one agent, one
lane, per job.

---

## Still needed from you

These were asked and not yet answered. The files carry placeholders in their
place:

- Company name, one-liner, sector, stage, amount, currency
- Incorporation and HQ jurisdiction (routes fund eligibility -- a locally
  incorporated company and a flipped company reach different funds)
- Markets operating in vs. targeting
- Which of the four capital types to include
- Excluded fund types and the do-not-contact list
- Live threads the agent must not touch
- Tooling: email, calendar, data room
- Working languages
- Which build-order stage to start at

---

## The rules that cannot slip

Carried from the source document, encoded across SOUL, MANAGER, and WORKFLOWS:

- Numbers come from the fact sheet or they do not get written
- A thread the founder already answered is locked
- Partners get a path to a person
- The calendar is the source of truth
- Legal language, price, and signatures never leave the draft queue
