"""Greenhouse job boards.

Greenhouse exposes a public, unauthenticated board API *per company* — there is no global
search. So this connector fans out across a configurable company list (see
`settings_store.greenhouse_companies`). That is a property of Greenhouse, not a shortcut:
the whole point of an ATS board API is that it serves one employer.

Verified endpoint (2026-07): https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true
Note this is `boards-api.greenhouse.io`, not the `api.greenhouse.io` host named in the PRD —
that one does not serve the public board endpoint.

Response shape (confirmed live):
    {"jobs": [{"id", "title", "absolute_url", "location": {"name"},
               "updated_at", "first_published", "content" (HTML), "company_name"}]}
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import httpx

from app.connectors.base import DEFAULT_TIMEOUT, JobConnector, html_to_text
from app.schemas import JobRecord, SearchQuery

BOARD_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"

REMOTE_HINTS = ("remote", "anywhere", "distributed", "work from home")


class GreenhouseConnector(JobConnector):
    source = "greenhouse"
    label = "Greenhouse (ATS boards)"
    priority = 10  # original employer board — beats aggregators in dedupe

    def __init__(self, companies: list[str] | None = None, max_concurrent: int = 6) -> None:
        self.companies = companies or []
        self._sem = asyncio.Semaphore(max_concurrent)

    async def fetch(self, client: httpx.AsyncClient, q: SearchQuery) -> list[JobRecord]:
        if not self.companies:
            return []

        results = await asyncio.gather(
            *(self._fetch_company(client, slug, q) for slug in self.companies),
            return_exceptions=True,
        )

        jobs: list[JobRecord] = []
        failures = 0
        for item in results:
            if isinstance(item, BaseException):
                failures += 1
                continue
            jobs.extend(item)

        # One dead company board is normal (renamed slug, board taken down). All of them
        # failing means the endpoint or our network is broken, and that should surface.
        if failures == len(self.companies):
            raise RuntimeError(
                f"all {failures} Greenhouse boards failed — endpoint or network issue"
            )
        return jobs

    async def _fetch_company(
        self, client: httpx.AsyncClient, slug: str, q: SearchQuery
    ) -> list[JobRecord]:
        async with self._sem:
            resp = await client.get(BOARD_URL.format(slug=slug), timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
            payload = resp.json()

        out: list[JobRecord] = []
        for raw in payload.get("jobs", []):
            record = self._normalize(raw, slug)
            if record is None:
                continue
            if q.remote_only and not record.remote:
                continue
            if not self.matches(q, record.title, record.description, record.location):
                continue
            out.append(record)
        return out

    def _normalize(self, raw: dict, slug: str) -> JobRecord | None:
        job_id = raw.get("id")
        apply_url = raw.get("absolute_url")
        title = (raw.get("title") or "").strip()
        if not job_id or not apply_url or not title:
            return None

        location = ((raw.get("location") or {}).get("name") or "").strip()
        description = html_to_text(raw.get("content") or "")
        company = (raw.get("company_name") or slug.replace("-", " ").title()).strip()

        blob = f"{title} {location}".lower()
        remote = any(hint in blob for hint in REMOTE_HINTS)

        return JobRecord(
            id=f"greenhouse:{slug}:{job_id}",
            source=self.source,
            title=title,
            company=company,
            location=location,
            remote=remote,
            posted_at=_parse_ts(raw.get("first_published") or raw.get("updated_at")),
            apply_url=apply_url,
            description=description,
        )


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
