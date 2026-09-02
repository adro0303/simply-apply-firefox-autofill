"""Local application tracker."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_extension_token
from app.models import Application, CoverLetter, Job, Resume
from app.schemas import ApplicationDetail, ApplicationOut, StructuredResume

router = APIRouter(prefix="/api/applications", tags=["applications"])

STATUSES = ("prepared", "applied", "interviewing", "offer", "rejected", "withdrawn")


class ApplicationUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None


def _to_out(row: Application, job: Job | None) -> ApplicationOut:
    return ApplicationOut(
        id=row.id,
        job_id=row.job_id,
        resume_id=row.resume_id,
        applied_at=row.applied_at,
        status=row.status,
        notes=row.notes,
        title=job.title if job else "",
        company=job.company if job else "",
        apply_url=job.apply_url if job else "",
        docx_url=f"/api/download/{row.id}/docx" if row.docx_path else None,
        pdf_url=f"/api/download/{row.id}/pdf" if row.pdf_path else None,
    )


@router.get("", response_model=list[ApplicationOut])
def list_applications(db: Session = Depends(get_db)) -> list[ApplicationOut]:
    rows = (
        db.execute(select(Application).order_by(Application.applied_at.desc()))
        .scalars()
        .all()
    )
    return [_to_out(row, db.get(Job, row.job_id)) for row in rows]


def _normalize_url(url: str) -> str:
    """Scheme + host + path only — query string and fragment vary per visit (UTM tags,
    session tokens, anchors) without changing what page it is."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


@router.get(
    "/by-url",
    response_model=ApplicationDetail,
    dependencies=[Depends(require_extension_token)],
)
def get_by_url(
    url: str = Query(..., description="The job page URL the extension is looking at"),
    db: Session = Depends(get_db),
) -> ApplicationDetail:
    """What the extension calls on every page load to see if this job already has a
    prepared application. 404 means it doesn't — the extension falls back to the
    ad-hoc-ingest + manual-apply flow.

    # ponytail: scans applications newest-first and does one Job lookup each, O(n) in
    # applications count — fine for a single-user local app, add an index/join if this
    # ever needs to scale past a personal job search.
    """
    target = _normalize_url(url)

    rows = (
        db.execute(select(Application).order_by(Application.applied_at.desc()))
        .scalars()
        .all()
    )
    for row in rows:
        job = db.get(Job, row.job_id)
        if job is None or _normalize_url(job.apply_url) != target:
            continue

        resume_row = db.get(Resume, row.resume_id)
        if resume_row is None:
            raise HTTPException(404, "The application's resume record is missing.")
        cover = (
            db.execute(
                select(CoverLetter)
                .where(CoverLetter.application_id == row.id)
                .order_by(CoverLetter.created_at.desc())
            )
            .scalars()
            .first()
        )
        return ApplicationDetail(
            application=_to_out(row, job),
            resume=StructuredResume.model_validate_json(resume_row.structured_json),
            cover_letter=cover.body if cover else None,
            cover_letter_fell_back=cover.fell_back if cover else False,
        )

    raise HTTPException(404, "No application found for this URL.")


@router.patch("/{application_id}", response_model=ApplicationOut)
def update_application(
    application_id: int, payload: ApplicationUpdate, db: Session = Depends(get_db)
) -> ApplicationOut:
    row = db.get(Application, application_id)
    if row is None:
        raise HTTPException(404, "Application not found.")
    if payload.status is not None:
        if payload.status not in STATUSES:
            raise HTTPException(400, f"Status must be one of: {', '.join(STATUSES)}")
        row.status = payload.status
    if payload.notes is not None:
        row.notes = payload.notes
    db.commit()
    db.refresh(row)
    return _to_out(row, db.get(Job, row.job_id))


@router.delete("/{application_id}")
def delete_application(
    application_id: int, db: Session = Depends(get_db)
) -> dict[str, bool]:
    row = db.get(Application, application_id)
    if row is None:
        raise HTTPException(404, "Application not found.")
    db.delete(row)
    db.commit()
    return {"ok": True}
