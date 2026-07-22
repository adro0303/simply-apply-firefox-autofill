"""The apply loop: tailor → guardrail → render → log → hand off.

Deliberately does not submit anything. The user downloads their files and clicks Submit
on the employer's own form. That's a product decision from the PRD, not a limitation.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.llm.base import LLMError
from app.llm.registry import build_provider
from app.models import Application, Job, Resume
from app.schemas import ApplyResponse, JobRecord, StructuredResume
from app.services.render_docx import render_docx
from app.services.render_pdf import PDFRenderError, render_pdf
from app.services.tailor import tailor

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["apply"])

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(value: str, fallback: str = "resume") -> str:
    cleaned = _UNSAFE.sub("-", (value or "").strip()).strip("-")
    return (cleaned or fallback)[:60]


def _job_record(row: Job) -> JobRecord:
    return JobRecord(
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


@router.post("/apply/{job_id:path}", response_model=ApplyResponse)
async def apply(job_id: str, db: Session = Depends(get_db)) -> ApplyResponse:
    settings = get_settings()

    job_row = db.get(Job, job_id)
    if job_row is None:
        raise HTTPException(404, "Job not found. Run a search first so it gets cached.")

    base_row = (
        db.query(Resume)
        .filter(Resume.is_base.is_(True))
        .order_by(Resume.created_at.desc())
        .first()
    )
    if base_row is None:
        raise HTTPException(
            400, "No base resume yet. Upload and confirm one on the Resume page first."
        )

    base_resume = StructuredResume.model_validate_json(base_row.structured_json)
    job = _job_record(job_row)

    try:
        provider = build_provider(db)
        result = await tailor(provider, base_resume, job)
    except LLMError as exc:
        raise HTTPException(400, str(exc)) from exc

    # Persist the exact document that gets rendered — including the fallback case, so the
    # application log always points at what was actually sent.
    tailored_row = Resume(
        name=f"{job.company} — {job.title}",
        structured_json=result.resume.model_dump_json(),
        is_base=False,
        base_resume_id=base_row.id,
        tailored_for_job_id=job.id,
    )
    db.add(tailored_row)
    db.commit()
    db.refresh(tailored_row)

    stem = f"{_slug(result.resume.basics.name, 'resume')}-{_slug(job.company, 'company')}-{tailored_row.id}"
    docx_path = settings.artifacts_dir / f"{stem}.docx"
    pdf_path = settings.artifacts_dir / f"{stem}.pdf"

    render_docx(result.resume, docx_path)

    # The PDF is a pure-Python render now, so it works on every install. We still guard
    # it: a rendering bug should degrade to "DOCX only" for this one apply rather than
    # 500 the whole request and lose the tailored document the user already generated.
    pdf_error: str | None = None
    try:
        render_pdf(result.resume, pdf_path)
    except PDFRenderError as exc:
        pdf_error = str(exc)
        pdf_path = None  # type: ignore[assignment]
        log.warning("apply: PDF render failed — %s", exc)

    application = Application(
        job_id=job.id,
        resume_id=tailored_row.id,
        applied_at=datetime.now(timezone.utc).replace(tzinfo=None),
        status="prepared",
        docx_path=str(docx_path),
        pdf_path=str(pdf_path) if pdf_path else None,
    )
    db.add(application)
    db.commit()
    db.refresh(application)

    return ApplyResponse(
        application_id=application.id,
        resume_id=tailored_row.id,
        job=job,
        docx_url=f"/api/download/{application.id}/docx",
        pdf_url=f"/api/download/{application.id}/pdf" if pdf_path else None,
        pdf_error=pdf_error,
        tailoring=result,
    )


@router.get("/download/{application_id}/{fmt}")
def download(
    application_id: int, fmt: str, db: Session = Depends(get_db)
) -> FileResponse:
    if fmt not in ("docx", "pdf"):
        raise HTTPException(400, "Format must be 'docx' or 'pdf'.")

    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(404, "Application not found.")

    raw_path = application.docx_path if fmt == "docx" else application.pdf_path
    if not raw_path:
        raise HTTPException(404, f"No {fmt.upper()} was generated for this application.")

    path = Path(raw_path).resolve()

    # The path came from our own DB, but resolve-and-contain anyway: this endpoint returns
    # file bytes, and a containment check is cheap insurance against a future code path
    # that lets a value in here from somewhere less trustworthy.
    artifacts_dir = get_settings().artifacts_dir.resolve()
    if not path.is_relative_to(artifacts_dir):
        raise HTTPException(400, "Refusing to serve a file outside the artifacts directory.")
    if not path.exists():
        raise HTTPException(404, "The generated file is missing. Re-run Apply.")

    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if fmt == "docx"
        else "application/pdf"
    )
    return FileResponse(path, media_type=media_type, filename=path.name)
