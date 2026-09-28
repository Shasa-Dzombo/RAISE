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
- `scripts/drive_client.py` -- create folders, upload + share a file
  ("anyone with the link, reader" -- see below for why), read view
  activity (legacy fallback only, see Known limitations).
- `scripts/watermark_pdf.py` -- stamps "CONFIDENTIAL -- Prepared for
  {firm} -- Do not distribute" on every page before upload.
- `scripts/data_room.py` -- orchestration: `grant`, `report`.
- `scripts/view_tracker.py` -- own link-click view tracker (Google Apps
  Script + a Sheet), the actual source of `data_room_views` now. See
  `workflows/VIEW_TRACKER_SETUP.md` for the one-time setup and why this
  exists instead of relying on Drive Activity.
- Schema: `data_room_links` (per-firm grant, tier, expiry),
  `data_room_files` (per-firm watermarked copy, restricted share,
  `tracking_token`), `data_room_views` (the log).

## Why every share is "anyone with the link," not restricted to one email

Changed from the original design. SPECIALISTS.md's "unique link, never
shared across firms" still holds -- each firm gets its own folder and
its own file copy -- but the share itself is no longer restricted to one
email. It used to be, on the theory that Drive could attribute a view to
that identity. It never actually could for personal Gmail viewers (see
Known limitations below), and the restriction caused a real "you need
access" / sign-in friction point once RAISE's own tracker took over
attribution instead. The tracker token now *is* the identity, by
construction (one token per firm+file) -- so the Drive-level restriction
was pure friction with no remaining upside. Real access control now lives
entirely in the tracker link itself (96 bits of randomness), the same
model DocSend/Papermark links use.

## Procedure

1. `python scripts/data_room.py grant --investor-id N --tier teaser|standard|full --email partner@fund.com --deck path/to/deck.pdf`
   - `full` tier is refused unless `investor_file.approved = TRUE` for that
     row -- full access still requires explicit founder approval per firm.
   - Creates `{Firm Name} -- {tier}` folder under one root Drive folder,
     watermarks the deck for that firm, uploads it, shares it as "anyone
     with the link, reader." `email` is still recorded (for reporting)
     but no longer restricts who can open the file. Drive's own
     `expirationTime` isn't supported on "anyone"-type permissions, so a
     grant always falls back to relying on RAISE's own
     `data_room_links.expiry_date` for enforcement (never silently
     fails over this -- the retry-without-expiry path is now the
     expected path, not an edge case).
2. `python scripts/data_room.py report` -- the morning report: for any
   file with a `tracking_token`, pulls new events from the view-tracker
   Sheet and logs each into `data_room_views` (`viewer_email` is the
   email the link was issued to, guaranteed by the token being unique
   per firm+file). Falls back to querying Drive Activity for any older
   file granted before the tracker existed (`tracking_token IS NULL`).

## Known limitations

- **Fixed**: Drive Activity API does not reliably emit VIEW activity for
  personal (non-Workspace) Gmail viewers, confirmed live twice (a PDF and
  a native Google Doc, both opened by a real second test account,
  neither producing a VIEW record). That ruled out self-hosting
  Papermark (needs its own Next.js/Prisma app plus Resend + Tinybird +
  S3-compatible storage) or paying for its hosted Data Rooms plan
  (~EUR99+/mo) as overkill for what was actually needed. Fixed instead
  with RAISE's own link-click tracker (`scripts/view_tracker.py`, a free
  Google Apps Script Web App) -- see `workflows/VIEW_TRACKER_SETUP.md`.
  This is now the primary path; Drive Activity is kept only as a fallback
  for any file granted before the tracker existed.
- The tracker's own limitation, carried over rather than solved: no
  device/browser/IP data (Apps Script's `doGet` exposes neither), so
  `flagged_unexpected` is always `FALSE` on tracker-sourced rows -- there
  is no signal to detect a forwarded link with. `viewer_email` on a
  tracker-sourced view is the email the link was issued to, guaranteed by
  the token's construction (one token per firm+file) rather than by
  resolving an identity after the fact -- stronger attribution than Drive
  Activity ever gave, just without the forwarding check.
- Drive's `expirationTime` field isn't supported on "anyone"-type
  permissions at all -- a recipient may retain Drive-level access past
  the stated expiry even though RAISE's own record considers it expired.
  `grant_access` always retries without it, so a grant never silently
  fails over this; expiry enforcement is entirely on RAISE's side
  (`data_room_links.expiry_date`), not Drive's.
- No morning-report automation/schedule yet -- run `report` manually or
  wire it to a scheduled task.
