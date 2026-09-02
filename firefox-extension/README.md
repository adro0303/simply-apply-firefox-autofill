# SimplyApply Autofill (Firefox extension)

Fills the personal-info fields and drops a tailored cover letter into
Greenhouse/Lever/Workday application pages, using data your local SimplyApply
backend already generated. **It never clicks Submit** — you still review and
submit the form yourself, same as SimplyApply's own downloaded-docx flow.

## Requirements

- The SimplyApply backend running locally at `http://localhost:8000` (see
  `../backend/README.md`). Nothing in this extension talks to any other host.
- Firefox.

## One-time setup: extension token

The backend requires every request to carry an `X-SimplyApply-Token` header —
this is what lets it tell "this extension" apart from any other extension
installed in your browser. On startup, the backend prints the token once to
its terminal/log output. Copy it from there, then:

1. Open the extension's Options page (right-click the extension icon →
   **Manage Extension** → **Preferences**, or `about:addons`).
2. Paste the token into the field and click **Save**.

If you skip this, requests come back `401 Unauthorized` and the popup will
tell you to set up the token in Options.

## Install (temporary add-on, for development)

1. Open `about:debugging#/runtime/this-firefox`.
2. Click **Load Temporary Add-on…**.
3. Select `manifest.json` in this directory.
4. The extension reloads each time Firefox restarts — repeat this step, or
   package it properly if you want a persistent install.

## Use

1. Make sure the backend is running.
2. Open a job application page on Greenhouse, Lever, or Workday.
3. Click the extension icon.
   - If SimplyApply already has a prepared application for this exact page
     URL, you'll see the job title/company and a **Fill this page** button.
   - Otherwise you get a small form (company, title, paste the job
     description) — submitting it creates the job, tailors your resume, and
     writes a cover letter against your local model, then shows the same
     **Fill this page** button.
4. Click **Fill this page**. Personal-info fields and (where a suitable field
   exists) the cover letter get filled in. Review everything yourself, then
   submit the form manually.

Any guardrail warning from the backend (fell back to a generic resume/letter
instead of a tailored one) is shown plainly in the popup — it is never
hidden.

## Known limitations

- **File upload is not automated.** Browsers block scripts from assigning a
  file to `<input type="file">`, and this extension does not attempt a
  DataTransfer/drag-simulation workaround (those are unreliable and easily
  break). Instead, any file input found on the page is outlined and tagged
  with a tooltip, and the popup shows the resume's actual filename (from the
  backend's `docx_url`) so you know what to attach from your Downloads
  folder.
- **Selectors are best-effort, not verified against a live posting.** This
  extension was built without browser access to a real Greenhouse/Lever/
  Workday posting. Every `content/*.js` file starts with a
  `SELECTORS UNVERIFIED` comment. Each field tries several candidate CSS
  selectors covering known conventions for that platform, but they have not
  been confirmed to work end-to-end. Test against a real posting before
  relying on this for an actual application, and expect to need selector
  tweaks — especially for Greenhouse (legacy `boards.greenhouse.io` embed vs.
  newer `job-boards.greenhouse.io` React app use different markup).
- **Workday coverage is deliberately partial.** Workday is a heavily
  customized per-tenant SPA — field naming, page order, and
  `data-automation-id` values vary by employer, and applications are a
  multi-page wizard. This extension only attempts the first "Personal
  Information" page. It does **not** attempt the later Experience/Education
  wizard pages, which use dynamic "add another" list UIs that would need
  per-tenant guesses to fill reliably. Fill those pages by hand.
- **Cover letter field detection is best-effort per ATS.** Greenhouse and
  Lever each have at most one plausible free-text field guessed (Greenhouse:
  a "cover letter" textarea when the posting allows pasting one in; Lever: the
  "Additional Information" `comments` field, since Lever has no dedicated
  cover-letter field on most postings). Workday's Personal Information page
  has no such field at all — the cover letter is reported as "not found" for
  Workday and you'll need to attach or paste it wherever the later pages of
  that tenant's flow expect it.

## Step-by-step first test (no prior extension experience assumed)

1. **Load it.** Open Firefox, go to `about:debugging#/runtime/this-firefox`, click
   **Load Temporary Add-on…**, and select `manifest.json` in this directory. It should
   appear in the list with no red error text. It's temporary — reload it here again after
   restarting Firefox.
2. **Set the token.** Click the extension's icon (find it under the puzzle-piece icon in
   the toolbar if it's not pinned) → right-click → **Manage Extension** → **Preferences**.
   Paste the token the backend printed at startup and save. Without this every request
   comes back 401 and the popup tells you to do this step.
3. **Make sure the backend is running**: `curl localhost:8000/api/health` should return
   `{"status":"ok",...}`. Start it per the root README if not.
4. **Find a real posting.** Open `http://localhost:3000` (the SimplyApply frontend),
   search for something, and open a listing whose Apply link is a Greenhouse-hosted page
   (`boards.greenhouse.io/...` or `job-boards.greenhouse.io/...`) — start there, its field
   markup is the most standard of the three ATSes this supports.
5. **Fill it.** On the application page, click the extension icon. If SimplyApply already
   prepared this job you'll see a **Fill this page** button directly; otherwise paste the
   job's company/title/description into the small form first (this calls your local model
   — can take a minute or more) and the button appears once that's done. Click it.
6. **Check what happened.** Which fields filled correctly, which didn't, any error text in
   the popup. Repeat on a Lever (`jobs.lever.co`) and, if you're feeling patient, a Workday
   (`*.myworkdayjobs.com`) posting — Workday only attempts the first "Personal Information"
   page, see Known limitations above.

Whatever breaks, the fix is almost always a selector tweak in the matching
`content/<ats>.js` file — open dev tools (`F12`) on the application page, inspect the
field that didn't fill, and compare its actual `id`/`name`/`data-*` attributes against the
candidates listed in that file.

## Security

An AGPL derivative doesn't get a pass on saying what changed for safety — two things this
fork does differently from a "just wire it up" version, both because a security review of
this exact extension work found them:

- **The `basics` block (name/email/phone/URLs/profiles) is now covered by the
  no-fabrication guardrail**, same as work/education/skills always were. Before this fix,
  a job description could make the tailoring model silently swap in a different email or
  LinkedIn URL and nothing would flag it — the resume that got typed into the real
  application form would carry it. Fixed in `backend/app/services/guardrail.py`.
- **Every endpoint this extension calls requires an `X-SimplyApply-Token` header.**
  CORS alone can't tell "this extension" apart from any other extension installed in your
  browser — a completely unrelated extension with zero declared permissions on this API
  could otherwise read your resume, or worse, rewrite `PUT /api/settings` to redirect all
  future LLM calls (and a stored API key, if you use a paid provider) to an attacker's
  server, persistently. The token is generated once on first backend startup and stored
  server-side; CORS still restricts *which kinds* of origins can even attempt a request,
  the token decides whether that request is honored.

Both close real, verified exploit paths — not theoretical ones — found by testing against
the actual code, not by inspection alone.

## Architecture (for hacking on this)

- `background.js` — the only file that calls `fetch()` against the backend.
  Content scripts and the popup route all backend calls through it via
  `browser.runtime.sendMessage`.
- `content/common.js` — `setNativeValue()` (works around React/Ember
  controlled-input value tracking), a `fillFields()` helper that tries a list
  of candidate selectors per field, a file-input highlighter, and the
  `runtime.onMessage` listener that dispatches an incoming `fillPage` message
  to whichever ATS handler is loaded on the page.
- `content/greenhouse.js`, `content/lever.js`, `content/workday.js` — each
  attaches `window.SimplyApplyATS = { name, fill(data) }` with that
  platform's field-selector map. Manifest `content_scripts` entries load
  `common.js` before the matching ATS file per site, so there's no runtime
  hostname sniffing needed.
- `popup/popup.html` + `popup/popup.js` — looks up the current page, shows
  either the "ready to fill" view or the ad-hoc job form, and sends the
  `fillPage` message to the active tab on click. No framework, no build step.
- `options/options.html` + `options/options.js` — one field for the backend
  auth token, saved to `browser.storage.local`. `background.js` reads it from
  there and attaches it as `X-SimplyApply-Token` on every backend request.
