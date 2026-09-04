# SimplyApply — + Firefox autofill & cover letters

<div align="center">

[![Fork of artbyjazi/simply-apply](https://img.shields.io/badge/Fork_of-artbyjazi%2Fsimply--apply-181717.svg?style=for-the-badge&logo=github&logoColor=white)](https://github.com/artbyjazi/simply-apply)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL--3.0-3DA639.svg?style=for-the-badge)](LICENSE)
[![Firefox Extension](https://img.shields.io/badge/+_Firefox_Extension-FF7139.svg?style=for-the-badge&logo=firefoxbrowser&logoColor=white)](firefox-extension/README.md)

🌍 **Extension docs:** [English](firefox-extension/README.md) · [Español](firefox-extension/README.es.md)

</div>

**Free, open-source, self-hosted job search + truthful resume tailoring.**

Search real job postings, click Apply on one, and get an ATS-safe resume regenerated from
your structured data and tailored to that posting — with a mechanical guarantee that
nothing was invented.

```
search  →  pick a posting  →  tailor()  →  no-fabrication check  →  docx + PDF  →  apply link
```

Your resume, your API keys, and your application history never leave your machine.

> All credit for the original search → tailor → guardrail → docx/pdf pipeline, and the
> no-fabrication design described below, belongs to
> **[artbyjazi/simply-apply](https://github.com/artbyjazi/simply-apply)** — go star/use the
> upstream project too. This fork stays AGPL-3.0, same as upstream (see `LICENSE`).
>
> **What this fork adds** — full details, install steps, and a security writeup in
> [`firefox-extension/README.md`](firefox-extension/README.md):
> - `POST /api/apply/{job_id}/cover-letter` — guardrailed cover-letter generation, same
>   fail-closed design as resume tailoring.
> - `POST /api/jobs/adhoc` + `GET /api/applications/by-url` — lets a browser extension
>   ingest a job found outside SimplyApply's own search (a Greenhouse/Lever/Workday page
>   LinkedIn or Indeed redirected you to) and look up what's already prepared for the page
>   you're on.
> - `firefox-extension/` — a Manifest V3 Firefox WebExtension that autofills those ATS
>   pages using only this backend and your local LLM (Ollama/LM Studio/etc.) — no paid API,
>   no subscription.
> - An `X-SimplyApply-Token` auth requirement on every extension-facing endpoint, and a
>   guardrail fix so `basics` (name/email/phone/URLs) is checked for fabrication the same
>   way work/education/skills already were — both added after a security review found the
>   originals let a rogue browser extension or a poisoned job posting silently rewrite
>   contact info or backend LLM settings.
>
> Selectors in `firefox-extension/content/*.js` were written without live browser access
> and are explicitly marked unverified — see the extension README before relying on them.

---

## Why this exists

Most resume tailoring tools either paywall the useful part or quietly let a language model
embellish your experience. SimplyApply does neither:

- **Tailoring is the product, and it's free.** No autofill engine, no accounts, no SaaS.
- **The no-fabrication rule is enforced in code, not in a prompt.** See below.
- **Your resume is structured data, not a file.** Every output is regenerated from it; no
  PDF is ever edited in place.

---

## The no-fabrication guardrail

This is the part that matters, so it's worth being precise about how it works.

Telling a model "don't invent experience" is a request, not a control. So after every
tailoring run, `backend/app/services/guardrail.py` validates the output against your base
resume:

| Checked | Rule |
|---|---|
| Employers, job titles, schools, degrees | Must match a value in your base resume |
| Every date | Must match a date in your base resume — no stretching to close a gap |
| Every number, percentage, and metric | Must appear in your base resume — 15% cannot become 40% |
| Every skill and keyword | Must appear *somewhere* in your base resume |

Reordering, rephrasing, dropping irrelevant bullets, and rewriting your summary are all
free — that's what tailoring is. Surfacing a skill that's buried inside a bullet is
allowed. Adding one because the job description asked for it is not.

**If the check fails, it retries once with the specific violations fed back. If it fails
again, you get your original resume plus an explicit warning** — never silently
fabricated content. The worst case is a generic application, not a rescinded offer.

It's a whitelist over your resume rather than a blocklist of suspicious phrases, so its
failure mode is a false positive (mildly annoying) instead of a false negative (career
damage).

---

## Quick start

### Docker (recommended)

```bash
git clone <your-fork-url> simplyapply
cd simplyapply
cp .env.example .env      # optional — you can set everything in the UI instead
docker compose up
```

Open <http://localhost:3000>.

> ⚠️ **Not yet verified.** The Compose setup was written but has not been run — Docker
> wasn't available on the machine where this was built. The native path below *has* been
> verified end to end. If `docker compose up` fails, please open an issue.

### Native (verified)

Requires Python 3.12+ and Node 20+.

```bash
# backend
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt      # Windows: .venv\Scripts\pip
.venv/bin/uvicorn app.main:app --port 8000

# frontend (second terminal)
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000>. The frontend proxies `/api` to the backend, so the browser
only ever talks to one origin.

---

## Configuring an AI provider

Tailoring and resume parsing need a model. Open **Settings** and pick one:

| Provider | Notes |
|---|---|
| **Anthropic** | Recommended. Defaults to `claude-opus-4-8`. Strongest at structured extraction and at respecting the no-fabrication rules. |
| **OpenAI-compatible** | Works with OpenAI, Groq, Together, OpenRouter, or a local LM Studio server — just change the base URL. |
| **Ollama** | Free, fully local, nothing leaves your machine. Smaller models make more parsing mistakes, so review the confirm screen carefully. |

Keys are stored in the local SQLite database and are **write-only over the API** — once
saved, no endpoint will hand the value back out.

---

## How it works

```
┌──────────────────────────────────────────────────────┐
│  docker compose up  (your machine)                    │
│                                                       │
│   Next.js  ──/api rewrite──▶  FastAPI                 │
│                                 ├── source connectors │
│                                 ├── dedupe + rank     │
│                                 ├── tailor()          │
│                                 ├── guardrail  ◀── the important bit
│                                 └── docx + PDF render │
│                                        │              │
│                                   SQLite (1 file)     │
└──────────────────────────────────────────────────────┘
          │                              │
   public job APIs              your LLM provider
```

**Resume format.** Stored as [JSON Resume](https://jsonresume.org) — a community
standard, so your data stays portable to other tooling.

**Outputs.** Every apply produces both files. The **PDF** is the human-facing copy —
always exactly one page, rendered with reportlab (pure Python, no system dependency) and
scaled to fit rather than truncated when content runs long. The **DOCX** is the safest
choice for ATS uploads (single column, no tables, standard headings — it survives naive
parsers most reliably). If PDF rendering ever fails, the apply degrades to DOCX-only for
that one job with a clear message rather than erroring.

---

## Adding a job source

One file. Drop it in `backend/app/connectors/` — it's discovered automatically, with no
registry to update:

```python
class MyBoardConnector(JobConnector):
    source = "myboard"
    label = "My Board"
    priority = 30          # lower wins when deduping across sources

    async def fetch(self, client, q) -> list[JobRecord]:
        resp = await client.get("https://example.com/api/jobs")
        resp.raise_for_status()
        return [self._normalize(row) for row in resp.json()]
```

Two rules: return normalized `JobRecord`s, and **raise on failure rather than returning
`[]`** — the search layer catches per-connector and reports the failure in the UI, but a
swallowed error would look identical to "no results."

Shipping today: **Greenhouse** (per-company ATS boards) and **Arbeitnow** (remote/EU).
Both verified live.

---

## Project status

Milestones M0–M5 of the PRD are complete: the full search → tailor → render → apply loop
works end to end.

**Verified:** 58 passing tests covering the guardrail (fabrication detection across
employers, titles, dates, inflated metrics, and phantom skills), the tailor retry and
fallback control flow, DOCX text-extraction ordering, single-page PDF rendering (page
count read back from the generated file, including an oversized resume shrunk to fit),
and the complete apply loop through the real app. Both connectors were hit live.

**Not yet verified:** `docker compose up` (no Docker available during development). The
image is implemented but has not been built.

**Not built yet (M6+):** remaining Tier-1 connectors, Adzuna and USAJOBS, JD-match
ranking, a two-column PDF theme, and the Tauri desktop wrap.

---

## Running the tests

```bash
cd backend
.venv/bin/python -m pytest        # Windows: .venv\Scripts\python -m pytest
```

If you touch `guardrail.py`, run these first. They're the difference between a tool that
tailors resumes and one that fabricates them.

---

## License

[AGPL-3.0](LICENSE). Chosen deliberately: you can run, modify, and share this freely, but
if you host a modified version as a service, you have to share your changes too.
