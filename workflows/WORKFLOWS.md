# WORKFLOWS

The shared record and the event flows. Build the record first -- every agent
reads from it, and if a number is not in it, nobody is allowed to invent it.

---

## The shared record -- build this before any agent runs

### Canon facts

Revenue, burn, runway, customers, retention, pricing, headcount. Each field
carries four attributes:

```
FIELD        [name]
VALUE        [the number]
AS OF        [date]
SOURCE       [where it came from -- system, statement, founder]
PUBLIC?      [can this be shared freely]
REFRESH BY   [date after which it is stale and pulled from circulation]
```

Africa-specific fields that belong here from day one:
- Currency of revenue, and FX exposure
- Revenue split by market
- Regulatory licences held, by market
- Domicile and any planned flip

These are first-round diligence questions in most African raises. Having them
unsourced when asked costs a week.

### Story pack

One-liner, problem, why now, product, go-to-market, use of funds.
Founder-signed only. No agent edits this.

### Question bank

Every diligence question already answered, with the approved reply, sources, and
which firms have asked it. Owned by the Diligence agent.

### Investor file

Firm, partner, thesis, check size, capital type, how we know them, where they sit
in our process. Owned by Scout, read by everyone.

### Assets and rules

Deck (public version), dashboards, data-room folders. Plus: who we may email,
what we may never say, when to stop and ask.

### Activity log

Every outbound note, every link granted, every number quoted, every escalation,
every approval. Needed if a thread is ever reviewed later.

---

## Event flows

### New inbound email

```
Email arrives
  -> Manager reads, classifies
  -> Founder already replied in thread?      -> LOCKED, stop
  -> Contains price/legal/board/signature?   -> ESCALATE, stop
  -> Sender is partner-level?                -> Inbox drafts only, no send
  -> Contains a question?
        -> in question bank?  -> Diligence returns approved answer
        -> not in bank?       -> Diligence drafts UNAPPROVED -> founder signs
  -> Contains meeting request?               -> Scheduler
  -> Contains data room request?             -> Data room (founder approves tier)
  -> Inbox composes reply
  -> Manager runs all 8 pre-send checks
  -> Send (per autonomy level) or queue as draft
  -> Pipeline updates stage, heat, next action
  -> Activity log written
```

### New target identified

```
Scout identifies fund
  -> Checks do-not-contact list
  -> Checks domicile compatibility
  -> Checks conflicts against portfolio
  -> Writes one-page note with sources
  -> Adds to investor file, marks NOT APPROVED
  -> Manager surfaces in daily digest
  -> Founder approves or rejects
  -> If approved -> Outreach drafts first note (template by capital type)
  -> Manager runs pre-send checks
  -> Draft or send per autonomy level
  -> Pipeline creates record at stage: Contacted
```

### Data room access request

```
Request arrives
  -> Inbox hands to Data room
  -> Data room checks: which tier is this firm approved for?
  -> Not yet approved -> Manager escalates to founder for tier decision
  -> Founder sets tier
  -> Data room issues unique watermarked link with expiry
  -> View log begins
  -> Morning report includes all opens
  -> Unexpected domain opens link -> immediate escalation
```

### Weekly pipeline review

```
Manager triggers Pipeline agent
  -> Pipeline scores every firm on behavioural signals only
  -> Flags: stalled threads, stage-time outliers, heat changes
  -> Produces "who is real" ranking
  -> Recommends drops with reasoning
  -> Manager delivers one-page summary + three threads worth founder time
  -> Founder decides drops
  -> Pipeline updates; Outreach stops cadence on dropped firms
```

### Term sheet arrives

```
Offer detected anywhere in the system
  -> ALL automation halts on that thread
  -> Manager escalates to founder immediately, no digest delay
  -> Terms agent builds neutral side-by-side comparison
  -> Output goes to founder and counsel only
  -> No agent replies to the investor
  -> No agent characterises the terms
  -> Founder and counsel own everything from here
```

---

## Kill switches

Any of these halts the relevant automation until a human clears it:

| Trigger | Halts |
|---|---|
| Two figures for the same metric found in circulation | All outbound |
| A fact-sheet field passes its refresh date | Outbound citing that field |
| Founder replies in a thread | That thread, permanently |
| Partner asks twice for a person | That thread's automation |
| Data-room link opened by unissued party | That firm's access |
| Term sheet or offer language detected | That thread, entirely |
| Pre-send check fails twice on one thread | That thread |

---

## Build order -- do not skip

| Stage | Enable | Gate to advance |
|---|---|---|
| 1 | Load fact sheet, deck, 40 expected questions. Nothing goes out. | Numbers stop drifting across repeated tests |
| 2 | Inbox drafts only. A person hits send. | Measure how much of each draft survives. Stable at high survival |
| 3 | Data room, one link per firm, morning open report | View log accurate for one full week |
| 4 | Target list and first-note drafts. Send stays manual. | Founder approves 10 consecutive drafts without material edit |
| 5 | Calendar and pipeline board. Only now allow unattended send on cold, low-risk mail. | -- |

See workflows/STAGE2_PROCEDURE.md for the exact Stage 2 procedure and safety scoping.

Stage 5 unattended send applies to cold, low-risk first notes only. Partner-level
mail, diligence answers, and anything price-adjacent stay in the draft queue
permanently.

---

## Voice study -- run before Stage 2

Connect to my email and read my last 50 sent messages. Study how I actually
write -- my tone, my greetings and sign-offs, how long my sentences are, the
phrases I use the most. Then write a style guide that captures my voice and
tone. To test it: draft a reply to my newest unread email as me, and I will tell
you what is off so you can tighten it.

Output goes to identity/VOICE.md. Iterate until the founder stops finding
things off. Outbound stays disabled until this is done.

---

## What good looks like

Every inbound answered the same day. Every number matching every other number.
A data room that is not a shared folder of leftovers. The founder spending time
on partners and terms instead of repeating the deck in email.

Not: the software raised the round.
