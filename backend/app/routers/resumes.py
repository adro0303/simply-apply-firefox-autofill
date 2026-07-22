"""Resume upload, parse, confirm, and edit.

Upload does NOT store a base resume. It returns the parsed structure for review; the
client sends it back to POST /api/resumes once the user has confirmed it. The parse is
imperfect by nature, and this document anchors every future render and every guardrail
check — an unreviewed error here would propagate silently into every application.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.llm.base import LLMError
from app.llm.registry import build_provider
from app.models import Resume
from app.schemas import ResumeOut, StructuredResume
from app.services.parse import ParseError, extract_text, parse_resume

router = APIRouter(prefix="/api/resumes", tags=["resumes"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class ParsePreview(BaseModel):
    """Unsaved parse result plus the raw text, so the UI can show what was read."""

    data: StructuredResume
    extracted_text: str


class ResumeIn(BaseModel):
    name: str = "My resume"
    data: StructuredResume


def _to_out(row: Resume) -> ResumeOut:
    return ResumeOut(
        id=row.id,
        name=row.name,
        is_base=row.is_base,
        created_at=row.created_at,
        tailored_for_job_id=row.tailored_for_job_id,
        data=StructuredResume.model_validate_json(row.structured_json),
    )


@router.post("/parse", response_model=ParsePreview)
async def parse_upload(
    file: UploadFile = File(...), db: Session = Depends(get_db)
) -> ParsePreview:
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is larger than 10 MB.")
    if not data:
        raise HTTPException(400, "The uploaded file is empty.")

    try:
        text = extract_text(file.filename or "", data)
    except ParseError as exc:
        raise HTTPException(400, str(exc)) from exc

    try:
        provider = build_provider(db)
        structured = await parse_resume(provider, text)
    except LLMError as exc:
        raise HTTPException(400, str(exc)) from exc

    return ParsePreview(data=structured, extracted_text=text)


@router.post("", response_model=ResumeOut)
def create_resume(payload: ResumeIn, db: Session = Depends(get_db)) -> ResumeOut:
    """Store the user-confirmed structure as the base resume."""
    # Single-user app: one base resume at a time. Demote any previous one rather than
    # deleting it, so tailored resumes keep their lineage.
    for existing in db.execute(select(Resume).where(Resume.is_base.is_(True))).scalars():
        existing.is_base = False

    row = Resume(
        name=payload.name,
        structured_json=payload.data.model_dump_json(),
        is_base=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.get("/base", response_model=ResumeOut | None)
def get_base(db: Session = Depends(get_db)) -> ResumeOut | None:
    row = db.execute(
        select(Resume).where(Resume.is_base.is_(True)).order_by(Resume.created_at.desc())
    ).scalars().first()
    return _to_out(row) if row else None


@router.get("", response_model=list[ResumeOut])
def list_resumes(db: Session = Depends(get_db)) -> list[ResumeOut]:
    rows = db.execute(select(Resume).order_by(Resume.created_at.desc())).scalars().all()
    return [_to_out(r) for r in rows]


@router.get("/{resume_id}", response_model=ResumeOut)
def get_resume(resume_id: int, db: Session = Depends(get_db)) -> ResumeOut:
    row = db.get(Resume, resume_id)
    if row is None:
        raise HTTPException(404, "Resume not found.")
    return _to_out(row)


@router.put("/{resume_id}", response_model=ResumeOut)
def update_resume(
    resume_id: int, payload: ResumeIn, db: Session = Depends(get_db)
) -> ResumeOut:
    row = db.get(Resume, resume_id)
    if row is None:
        raise HTTPException(404, "Resume not found.")
    row.name = payload.name
    row.structured_json = payload.data.model_dump_json()
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.delete("/{resume_id}")
def delete_resume(resume_id: int, db: Session = Depends(get_db)) -> dict[str, bool]:
    row = db.get(Resume, resume_id)
    if row is None:
        raise HTTPException(404, "Resume not found.")
    db.delete(row)
    db.commit()
    return {"ok": True}
