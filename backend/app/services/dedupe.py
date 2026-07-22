"""Cross-source deduplication.

The same role legitimately appears on both an employer's ATS board and an aggregator.
We collapse on a normalized `company + title + location` key and keep the record from the
lowest-`priority` connector, because the ATS `apply_url` is the employer's real form while
the aggregator's is usually a redirect or a wrapper page.
"""

from __future__ import annotations

import re
import unicodedata

from app.schemas import JobRecord

# Suffixes that differ between sources for the same employer ("Stripe" vs "Stripe, Inc.")
_COMPANY_NOISE = re.compile(
    r"\b(inc|llc|ltd|limited|corp|corporation|gmbh|bv|nv|sa|ag|plc|co|company|group)\b\.?",
    re.IGNORECASE,
)
_SENIORITY_PAREN = re.compile(r"\((?:[^)]*)\)")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _normalize(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value or "")
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return _NON_ALNUM.sub(" ", folded.lower()).strip()


def _company_key(company: str) -> str:
    return _NON_ALNUM.sub("", _COMPANY_NOISE.sub("", _normalize(company)))


def _title_key(title: str) -> str:
    # Drop parenthetical qualifiers — "(Remote)", "(Contract)", "(f/m/d)" — which vary by
    # source for what is unambiguously the same posting.
    return _NON_ALNUM.sub("", _normalize(_SENIORITY_PAREN.sub("", title)))


def _location_key(location: str, remote: bool) -> str:
    if remote:
        return "remote"
    normalized = _normalize(location)
    # Compare on the city only. Sources disagree on how much of the address they include
    # ("Berlin" vs "Berlin, Germany" vs "Berlin, BE, Germany").
    return _NON_ALNUM.sub("", normalized.split(" ")[0]) if normalized else ""


def dedupe_key(job: JobRecord) -> tuple[str, str, str]:
    return (
        _company_key(job.company),
        _title_key(job.title),
        _location_key(job.location, job.remote),
    )


def dedupe(jobs: list[JobRecord], priorities: dict[str, int]) -> list[JobRecord]:
    """Collapse duplicates, preferring the highest-authority source.

    Ties break on richer description, since a fuller JD produces better tailoring.
    """
    best: dict[tuple[str, str, str], JobRecord] = {}

    for job in jobs:
        key = dedupe_key(job)
        incumbent = best.get(key)
        if incumbent is None:
            best[key] = job
            continue

        challenger_rank = priorities.get(job.source, 50)
        incumbent_rank = priorities.get(incumbent.source, 50)

        if challenger_rank < incumbent_rank:
            best[key] = job
        elif challenger_rank == incumbent_rank and len(job.description) > len(
            incumbent.description
        ):
            best[key] = job

    return list(best.values())
