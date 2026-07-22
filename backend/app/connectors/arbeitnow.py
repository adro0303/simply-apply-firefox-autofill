"""Arbeitnow — free remote/EU job board API, no auth, no key.

Verified endpoint (2026-07): https://www.arbeitnow.com/api/job-board-api
Response shape (confirmed live):
    {"data": [{"slug", "company_name", "title", "description" (HTML),
               "remote" (bool), "url", "tags", "job_types", "location",
               "created_at" (unix seconds)}],
     "links": {...}, "meta": {...}}

There is no server-side query parameter, so filtering happens client-side. We walk a
bounded number of pages rather than the whole board — unbounded pagination on every
search would be slow and rude to a free service.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.connectors.base import DEFAULT_TIMEOUT, JobConnector, html_to_text
from app.schemas import JobRecord, SearchQuery

API_URL = "https://www.arbeitnow.com/api/job-board-api"
MAX_PAGES = 3


class ArbeitnowConnector(JobConnector):
    source = "arbeitnow"
    label = "Arbeitnow (remote / EU)"
    priority = 40

    async def fetch(self, client: httpx.AsyncClient, q: SearchQuery) -> list[JobRecord]:
        out: list[JobRecord] = []

        for page in range(1, MAX_PAGES + 1):
            resp = await client.get(
                API_URL, params={"page": page}, timeout=DEFAULT_TIMEOUT
            )
            resp.raise_for_status()
            payload = resp.json()
            rows = payload.get("data") or []
            if not rows:
                break

            for raw in rows:
                record = self._normalize(raw)
                if record is None:
                    continue
                if q.remote_only and not record.remote:
                    continue
                if not self.matches(q, record.title, record.description, record.location):
                    continue
                out.append(record)

            if len(out) >= q.limit:
                break

        return out

    def _normalize(self, raw: dict) -> JobRecord | None:
        slug = raw.get("slug")
        title = (raw.get("title") or "").strip()
        url = raw.get("url")
        if not slug or not title or not url:
            return None

        created = raw.get("created_at")
        posted_at: datetime | None = None
        if isinstance(created, (int, float)):
            posted_at = datetime.fromtimestamp(created, tz=timezone.utc)

        return JobRecord(
            id=f"arbeitnow:{slug}",
            source=self.source,
            title=title,
            company=(raw.get("company_name") or "").strip(),
            location=(raw.get("location") or "").strip(),
            remote=bool(raw.get("remote")),
            posted_at=posted_at,
            apply_url=url,
            description=html_to_text(raw.get("description") or ""),
        )
