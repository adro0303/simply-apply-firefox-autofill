"""Search orchestration: fan out, isolate failures, dedupe, rank, cache.

Failure isolation is the important property here. Public job APIs go down, rename slugs,
and rate-limit. One bad source must degrade the result list, never fail the search — so
every connector runs inside its own try/except and reports back in `sources_failed`,
which the UI surfaces to the user rather than hiding.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.connectors.base import USER_AGENT
from app.connectors.registry import build_enabled
from app.models import Job, SearchCache
from app.schemas import JobRecord, SearchQuery, SearchResponse
from app.services.dedupe import dedupe
from app.services.rank import rank

log = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_fresh(db: Session, source: str, query_key: str, ttl_minutes: int) -> bool:
    row = db.execute(
        select(SearchCache).where(
            SearchCache.source == source, SearchCache.query_key == query_key
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    fetched = row.fetched_at
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return _utcnow() - fetched < timedelta(minutes=ttl_minutes)


def _touch_cache(db: Session, source: str, query_key: str) -> None:
    row = db.execute(
        select(SearchCache).where(
            SearchCache.source == source, SearchCache.query_key == query_key
        )
    ).scalar_one_or_none()
    if row is None:
        db.add(SearchCache(source=source, query_key=query_key, fetched_at=_utcnow()))
    else:
        row.fetched_at = _utcnow()


def _persist_jobs(db: Session, jobs: list[JobRecord]) -> None:
    """Upsert postings so /apply can look one up later without re-searching."""
    for job in jobs:
        existing = db.get(Job, job.id)
        payload = dict(
            source=job.source,
            title=job.title,
            company=job.company,
            location=job.location,
            remote=job.remote,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            currency=job.currency,
            posted_at=job.posted_at.replace(tzinfo=None) if job.posted_at else None,
            apply_url=job.apply_url,
            description=job.description,
            fetched_at=_utcnow().replace(tzinfo=None),
        )
        if existing is None:
            db.add(Job(id=job.id, **payload))
        else:
            for key, value in payload.items():
                setattr(existing, key, value)
    db.commit()


def _cached_jobs(db: Session, sources: list[str], q: SearchQuery) -> list[JobRecord]:
    stmt = select(Job).where(Job.source.in_(sources))
    rows = db.execute(stmt).scalars().all()

    out: list[JobRecord] = []
    for row in rows:
        if q.remote_only and not row.remote:
            continue
        haystack = f"{row.title} {row.description}".lower()
        if q.query and not all(t in haystack for t in q.query.lower().split()):
            continue
        if q.location and q.location.lower().strip() not in (row.location or "").lower():
            continue
        out.append(
            JobRecord(
                id=row.id,
                source=row.source,
                title=row.title,
                company=row.company,
                location=row.location,
                remote=row.remote,
                salary_min=row.salary_min,
                salary_max=row.salary_max,
                currency=row.currency,
                posted_at=row.posted_at,
                apply_url=row.apply_url,
                description=row.description,
            )
        )
    return out


async def search_jobs(db: Session, q: SearchQuery) -> SearchResponse:
    settings = get_settings()
    connectors = build_enabled(db)
    if not connectors:
        return SearchResponse(jobs=[], sources_ok=[], sources_failed={})

    query_key = q.cache_key()
    priorities = {c.source: c.priority for c in connectors}

    stale = [c for c in connectors if not _is_fresh(db, c.source, query_key, settings.cache_ttl_minutes)]
    fresh_sources = [c.source for c in connectors if c not in stale]

    collected: list[JobRecord] = []
    sources_ok: list[str] = []
    sources_failed: dict[str, str] = {}

    if fresh_sources:
        collected.extend(_cached_jobs(db, fresh_sources, q))
        sources_ok.extend(fresh_sources)

    if stale:
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, follow_redirects=True
        ) as client:
            results = await asyncio.gather(
                *(connector.fetch(client, q) for connector in stale),
                return_exceptions=True,
            )

        for connector, result in zip(stale, results):
            if isinstance(result, BaseException):
                log.warning("connector %s failed: %s", connector.source, result)
                sources_failed[connector.source] = f"{type(result).__name__}: {result}"
                # Fall back to whatever we last cached for this source, so a transient
                # outage degrades to stale results rather than to nothing.
                collected.extend(_cached_jobs(db, [connector.source], q))
                continue

            collected.extend(result)
            sources_ok.append(connector.source)
            _persist_jobs(db, result)
            _touch_cache(db, connector.source, query_key)

        db.commit()

    deduped = dedupe(collected, priorities)
    ranked = rank(deduped, q)

    return SearchResponse(
        jobs=ranked[: q.limit],
        sources_ok=sorted(set(sources_ok)),
        sources_failed=sources_failed,
        from_cache=not stale,
    )
