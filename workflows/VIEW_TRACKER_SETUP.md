# VIEW TRACKER SETUP

One-time setup for RAISE's own data-room view tracker (replaces Drive
Activity API, which does not reliably report views for personal Gmail
viewers -- see `workflows/DATA_ROOM_PROCEDURE.md`). No new account, no
new cost -- everything here runs on the Google account already
connected for Gmail/Drive.

What this tracker tells you: **a link was opened, when, and how many
times.** Not who/what device/browser -- Google Apps Script's `doGet`
does not expose request headers or IP, only the query string. See
`scripts/view_tracker.py`'s module docstring for the full tradeoff
(Cloudflare Workers would add device/IP data if that's ever needed
later; swapping to it changes nothing on RAISE's Postgres side).

---

## 1. Add the Sheets scope and re-consent

`google_auth.py`'s `SCOPES` now includes
`https://www.googleapis.com/auth/spreadsheets`. Existing cached tokens
do not pick up new scopes automatically:

```bash
rm .gmail_token.json
python scripts/google_auth.py --auth
```

Re-approve consent in the browser window that opens.

## 2. Create the tracker spreadsheet

```bash
python scripts/view_tracker.py setup
```

Creates a Google Sheet named "RAISE View Tracker" with two tabs
(`tokens`, `events`) and prints a spreadsheet ID. Add it to `.env`:

```
VIEW_TRACKER_SHEET_ID=<the printed id>
```

## 3. Create and deploy the Apps Script

1. Go to [script.google.com](https://script.google.com), **New project**.
2. Delete the placeholder code and paste this in:

```javascript
var SHEET_ID = 'PASTE_YOUR_VIEW_TRACKER_SHEET_ID_HERE';

function doGet(e) {
  var token = e.parameter.t;
  var ss = SpreadsheetApp.openById(SHEET_ID);
  var tokens = ss.getSheetByName('tokens').getDataRange().getValues();
  var driveUrl = null;
  for (var i = 1; i < tokens.length; i++) {
    if (tokens[i][0] === token) { driveUrl = tokens[i][3]; break; }
  }
  if (!driveUrl) {
    return HtmlService.createHtmlOutput('Link not found or expired.');
  }
  // The view is logged right here, the moment the link is opened --
  // before the click below even happens.
  ss.getSheetByName('events').appendRow([token, new Date().toISOString()]);

  // Apps Script sandboxes doGet output in an iframe that blocks any
  // script- or meta-refresh-driven top-level navigation (a deliberate
  // Google anti-hijack restriction, not a bug here) -- an invisible
  // auto-redirect is not possible. A real target="_top" link is the
  // documented workaround: https://developers.google.com/apps-script/guides/html/restrictions
  // Styled as a small centered card, not a big empty page.
  var html = '<html><head><base target="_top">' +
             '<meta name="viewport" content="width=device-width, initial-scale=1">' +
             '<style>' +
             'body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;' +
             'background:#f1f3f4;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}' +
             '.card{background:#fff;border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.12),0 1px 2px rgba(0,0,0,.08);' +
             'padding:28px 32px;max-width:300px;text-align:center}' +
             '.card p{margin:0 0 16px 0;color:#202124;font-size:15px}' +
             '.card a{display:inline-block;padding:10px 22px;background:#0b57d0;color:#fff;' +
             'text-decoration:none;border-radius:6px;font-size:14px;font-weight:500}' +
             '</style></head>' +
             '<body><div class="card"><p>Your document is ready.</p>' +
             '<a href="' + driveUrl + '" target="_top">View document</a></div></body></html>';
  return HtmlService.createHtmlOutput(html);
}
```

3. Replace `PASTE_YOUR_VIEW_TRACKER_SHEET_ID_HERE` with the spreadsheet
   ID from step 2.
4. **Deploy > New deployment > Web app.**
   - Execute as: **Me**
   - Who has access: **Anyone**
   - If you're updating an existing deployment's code instead of
     creating a fresh one: **Deploy > Manage deployments > edit (pencil
     icon) > Version: New version > Deploy** -- this keeps the same
     `/exec` URL but serves the updated code.
5. Copy the resulting `https://script.google.com/macros/s/.../exec` URL.
   Add it to `.env`:

```
VIEW_TRACKER_BASE_URL=<the exec URL>
```

## 4. Verify

```bash
python scripts/data_room.py grant --investor-id <id> --tier teaser --email <safe test recipient> --deck <path>
```

The returned `share_url` should now be a `.../exec?t=...` link, not a
raw `drive.google.com` link. Open it (from the test recipient's own
inbox, per this project's safe-testing convention -- never a real
investor address) and confirm it lands on the real file. Then:

```bash
python scripts/data_room.py report
```

should show that view, with a timestamp and the recipient's email.
Running `report` again immediately should **not** duplicate the row --
`data_room_views` now has a unique index on `(file_id, viewed_at)`.

## Known limitations

- **Privacy-hardened browsers can block the card entirely, confirmed live.**
  The "Your document is ready" card isn't served directly -- Apps Script
  loads it into a nested iframe from a second domain
  (`*.script.googleusercontent.com`, separate from `script.google.com`),
  via a client-side `goog.script.init(...)` call. Brave (even with
  Shields explicitly turned off for the page) blocked this in testing --
  the outer page loaded, the Apps Script execution log showed a clean
  100%-complete run with no error, but the card never rendered and Drive
  showed a generic "Sorry, unable to open the file" error instead. Same
  link opened cleanly in a different browser. There is no alternate URL
  to hand out instead -- the inner googleusercontent.com URL is not a
  stable, independently-shareable link (it only works paired with the
  init call that passes it the encoded HTML at load time). If an
  investor reports a dead link, ask them to try a different browser or
  disable aggressive script/tracker blocking before assuming the grant
  itself is broken -- verify token/file/permissions server-side first
  (see Verify above) rather than guessing. If this recurs often, it's a
  real argument for the Cloudflare Workers alternative discussed when
  this tracker was designed: a Worker responds directly from one origin,
  no nested cross-domain iframe, so this specific failure mode wouldn't
  exist -- swapping to it changes nothing on RAISE's Postgres side.
- No device/browser/IP data -- see the top of this doc.
- No forwarding detection -- `flagged_unexpected` is always `FALSE` on
  tracker-sourced rows, since there's no signal to compare against.
- Corporate email security scanners (Microsoft Defender Safe Links,
  similar Google-side scanning, some proxies) can pre-fetch a link
  before a human clicks it -- this can log a false early "view." Not
  unique to this approach; Papermark/DocSend links have the same
  exposure.
- Not an instant HTTP 302 -- Apps Script can't issue one, and its iframe
  sandbox blocks a script-driven auto-redirect too (see the code comment
  above). The investor sees a small "Your document is ready" card with
  one button to click, not a fully invisible pass-through.
