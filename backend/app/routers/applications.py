"""Local application tracker."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Application, Job
from app.schemas import ApplicationOut

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
