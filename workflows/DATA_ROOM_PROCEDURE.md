# DATA ROOM PROCEDURE

How the data room actually works (agents/SPECIALISTS.md #5 DATA ROOM),
built on Google Drive rather than Papermark or DocSend -- see the "why"
in the handoff conversation: neither was a quick plug-in, and this reuses
the OAuth grant already set up for Gmail.

---

## What's built

- `scripts/google_auth.py` -- one shared OAuth token, Gmail + Drive +
  Drive Activity scopes (`drive.file` only: this app sees only files it
  creates, never the founder's wider Drive).
- `scripts/drive_client.py` -- create folders, upload + restricted-share a
  file to one specific email, read view activity.
- `scripts/watermark_pdf.py` -- stamps "CONFIDENTIAL -- Prepared for
  {firm} -- Do not distribute" on every page before upload.
- `scripts/data_room.py` -- orchestration: `grant`, `report`.
- Schema: `data_room_links` (per-firm grant, tier, expiry),
  `data_room_files` (per-firm watermarked copy, restricted share),
  `data_room_views` (the log).

## Why every share is restricted, never a public link

Two independent reasons converge on the same design: SPECIALISTS.md
requires "unique link, never shared across firms," and Drive can only
attribute a view to a named identity when the file was shared with that
person's specific email -- a public "anyone with the link" share gives
little to no usable view log. So every grant targets exactly one email,
which satisfies both requirements at once.

## Procedure

1. `python scripts/data_room.py grant --investor-id N --tier teaser|standard|full --email partner@fund.com --deck path/to/deck.pdf`
   - `full` tier is refused unless `investor_file.approved = TRUE` for that
     row -- full access still requires explicit founder approval per firm.
   - Creates `{Firm Name} -- {tier}` folder under one root Drive folder,
     watermarks the deck for that firm, uploads it, shares with exactly
     that email, sets a 30-day expiry (Drive honors this natively for
     Workspace recipients; RAISE's own `data_room_links.expiry_date`
     enforces it regardless of recipient type).
2. `python scripts/data_room.py report` -- the morning report: queries
   Drive Activity for every active file, logs each view into
   `data_room_views`, and flags any view Drive could not attribute to the
   email the link was actually issued to.

## Known limitations (first pass)

- **Drive Activity API does not reliably emit VIEW activity for personal
  (non-Workspace) Gmail viewers, confirmed live.** Two diagnostics: a
  watermarked PDF shared with and opened by a real second test account
  (`killianfumez@gmail.com`), and a native Google Doc shared with and opened
  by the same account -- neither produced a VIEW record in
  `activity.query()`, only the original create/permission-change events.
  This rules out a PDF-specific or propagation-delay explanation; it is a
  platform-level gap in what Drive Activity reports for consumer accounts.
  `data_room.py grant`'s folder/watermark/restricted-share mechanics are
  verified working end to end; `data_room.py report`'s view-log is **not**
  currently a trustworthy signal for real investor contacts (most of whom
  will be on personal Gmail, per Scout's own research) and should not be
  read as "no one has looked yet" -- it may simply never register a view at
  all. Revisit with a purpose-built tool (e.g. Papermark) if per-viewer
  tracking becomes load-bearing; that migration was scoped and paused on
  cost/infra grounds (self-host needs its own Next.js/Prisma app plus
  Resend + Tinybird + S3-compatible storage; hosted access needs Papermark's
  Data Rooms plan, ~EUR99+/mo).
- View-log identity resolution is best-effort: Drive Activity returns a
  person resource name, not a resolved email. Confirming it actually
  matches `shared_with_email` needs the People API, not wired up here yet
  -- for now, `flagged_unexpected` is set whenever Drive could not name a
  known user at all, not a true email-match check. Treat an unflagged view
  as "someone signed in," not yet as proven-correct-recipient.
- Drive's own link-expiration (`expirationTime`) only applies reliably to
  Google Workspace accounts; a personal Gmail recipient may retain access
  past the stated expiry at the Drive layer even though RAISE's own record
  considers it expired. `grant_access` retries without it if Drive rejects
  the field, so a grant never silently fails over this.
- No morning-report automation/schedule yet -- run `report` manually or
  wire it to a scheduled task.
