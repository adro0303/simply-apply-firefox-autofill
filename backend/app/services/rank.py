"""Search result ranking.

v1 default is recency. It is cheap, predictable, and honest: a "match score" computed
before tailoring would mostly measure keyword overlap, which is exactly the signal the
tailoring step is meant to fix. Ranking by a number that the next step invalidates would
be theatre.

The interface exists so JD-match ranking can be added in v2 without touching the router.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Protocol

from app.schemas import JobRecord, SearchQuery


class Ranker(Protocol):
    name: str

    def __call__(self, jobs: list[JobRecord], q: SearchQuery) -> list[JobRecord]: ...


def _posted_sort_value(job: JobRecord) -> datetime:
    if job.posted_at is None:
        # Undated postings sort last rather than randomly — treat as maximally stale.
        return datetime.min.replace(tzinfo=timezone.utc)
    if job.posted_at.tzinfo is None:
        return job.posted_at.replace(tzinfo=timezone.utc)
    return job.posted_at


def by_recency(jobs: list[JobRecord], q: SearchQuery) -> list[JobRecord]:
    return sorted(jobs, key=_posted_sort_value, reverse=True)


RANKERS: dict[str, Callable[[list[JobRecord], SearchQuery], list[JobRecord]]] = {
    "recency": by_recency,
}

DEFAULT_RANKER = "recency"


def rank(jobs: list[JobRecord], q: SearchQuery, strategy: str = DEFAULT_RANKER) -> list[JobRecord]:
    ranker = RANKERS.get(strategy, by_recency)
    return ranker(jobs, q)
