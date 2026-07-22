"""Job search."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.connectors.registry import source_labels
from app.db import get_db
from app.schemas import SearchQuery, SearchResponse
from app.services.search import search_jobs

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search", response_model=SearchResponse)
async def search(
    q: str = Query("", description="Job title or keywords"),
    location: str = Query(""),
    remote_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> SearchResponse:
    return await search_jobs(
        db, SearchQuery(query=q, location=location, remote_only=remote_only, limit=limit)
    )


@router.get("/sources")
def sources() -> dict[str, str]:
    """Source id -> display label, for the settings screen."""
    return source_labels()
