# SCOUT PROCEDURE

How target research actually gets done (agents/SPECIALISTS.md #1 SCOUT).

---

## Sources (per the original spec)

Africa: The Big Deal ($100k+ rounds, catches early stage), Partech Africa
report ($200k+, free, methodological gold standard), Briter Intelligence
(paid directory), AVCA member directory (free, good DFI list), Crunchbase
(weak below Series A in Africa), fund websites and LinkedIn for
partner-level thesis detail. DFI seed list: AAIC, BII, DEG, DFC, IFC,
Proparco.

In practice (no direct API access to most of these): WebSearch + WebFetch
against fund websites and press coverage, cross-referenced across at least
two sources per fund where possible. Briter/Partech/AVCA's own published
reports and directories are searched and cited when surfaced, not treated
as unavailable just because there's no API key.

## Procedure

1. Read `identity/USER.md`'s targeting instructions (capital types to
   include, geographic focus, check-size band, exclusions, do-not-contact
   list) before searching anything.
2. Search per capital type -- never assume one search covers all four; the
   four types live in different parts of the ecosystem (VC databases vs.
   DFI directories vs. local angel-network sites).
3. For each candidate fund, verify independently sourced: thesis, check
   size, stage fit, actual deployment markets (not just stated), domicile
   requirements, and at least one portfolio example. Every fact gets its
   source and date -- a fact with no verifiable date is flagged stale, not
   silently used.
4. Insert via `scripts/add_investor.py` (`add_investor()` if scripting
   several at once) -- it refuses to insert anything missing `source` or
   `source_date`. New rows default to `approved = FALSE`.
5. Do not send anything. Surface the notes to the founder for approval or
   rejection (`identity/USER.md`'s do-not-contact list; the founder's own
   judgment). Only once `investor_file.approved = TRUE` is a firm eligible
   for Outreach's first-note drafting (Stage 4).

## Hard rules (from SPECIALISTS.md, restated)

- Never send anything -- Scout produces notes, Outreach acts on them.
- Never add anyone already on the do-not-contact list.
- Flag domicile blockers explicitly -- a structural mismatch is a reason to
  talk to counsel, not a target to pursue.
- Distinguish a fund's stated geography from where it has actually deployed.
- A stale source (no verifiable recent date) gets flagged, not treated as
  current.
