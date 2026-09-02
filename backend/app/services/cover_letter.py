"""generate() — write a cover letter for a job, from the base resume.

Mirrors tailor.py's control flow exactly:

    generate → guardrail (numeric fabrication only) → violations? → regenerate with
    violations fed back → still bad? → fall back to a neutral templated letter

Same fail-closed philosophy as tailoring: an LLM-fabricated letter that failed the
no-fabrication check twice must never ship. The fallback is built with plain string
formatting from fields already in the resume, not a second LLM call, so it cannot itself
introduce a new fabrication.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from app.llm.base import LLMError, LLMProvider
from app.schemas import CoverLetterResult, JobRecord, StructuredResume
from app.services import guardrail

log = logging.getLogger(__name__)

MAX_JD_CHARS = 12000

SYSTEM_PROMPT = """You write a cover letter for a real person applying to a real job.

You are writing on behalf of someone who will have to answer for anything you invent, \
in an interview.

ALLOWED:
- Reference work experience, projects, and skills that already appear in the resume below.
- Use the job description's vocabulary to frame relevant experience.
- Express genuine interest in the role and company, in general terms.

FORBIDDEN — every one of these is fabrication:
- Inventing an employer, job title, school, degree, or project not in the resume.
- Inventing or inflating any number, percentage, or metric not in the resume.
- Claiming a skill or technology the resume never mentions, even if the job asks for it.
- Inventing enthusiasm-metrics (e.g. "I've followed your company for 10 years") that \
aren't in the resume.

Write 200-350 words of plain prose. No letterhead, no address block, no placeholders \
like "[Hiring Manager]" — address it generically ("Dear Hiring Team,").

Return only the letter body."""

RETRY_PREFIX = """Your previous attempt introduced numbers that are not in the base resume.

Violations found:
{violations}

Write the cover letter again. Every number or metric must appear in the base resume \
below. When in doubt, leave numbers out entirely."""


class _LetterBody(BaseModel):
    """The provider interface only does structured extraction — wrap free text in a
    one-field schema rather than inventing a second LLMProvider method for this."""

    body: str


def _build_user_prompt(resume: StructuredResume, job: JobRecord) -> str:
    description = job.description[:MAX_JD_CHARS]
    truncated = " (truncated)" if len(job.description) > MAX_JD_CHARS else ""
    return f"""JOB
Title: {job.title}
Company: {job.company}
Location: {job.location or "Not specified"}

JOB DESCRIPTION{truncated}
{description}

BASE RESUME (the only source of truth — JSON Resume format)
{resume.model_dump_json(indent=2)}"""


def _fallback_letter(resume: StructuredResume, job: JobRecord) -> str:
    """Neutral templated letter from the base resume's own fields. Never LLM-generated,
    so it cannot itself fail the guardrail."""
    name = resume.basics.name or "Applicant"

    highlights: list[str] = []
    for entry in resume.work[:2]:
        if entry.position and entry.name:
            highlights.append(f"{entry.position} at {entry.name}")
        elif entry.position or entry.name:
            highlights.append(entry.position or entry.name)
    if not highlights:
        highlights = [p.name for p in resume.projects[:2] if p.name]

    experience_line = (
        f"My background includes {', '.join(highlights)}."
        if highlights
        else "My resume, attached, details my relevant background."
    )

    return (
        "Dear Hiring Team,\n\n"
        f"I am writing to express my interest in the {job.title} role at {job.company}. "
        f"{experience_line}\n\n"
        "I would welcome the opportunity to discuss how my experience aligns with this "
        "role. Thank you for your consideration.\n\n"
        f"Sincerely,\n{name}"
    )


async def generate(
    provider: LLMProvider, resume: StructuredResume, job: JobRecord
) -> CoverLetterResult:
    base_prompt = _build_user_prompt(resume, job)

    try:
        candidate = (
            await provider.complete_structured(
                system=SYSTEM_PROMPT, user=base_prompt, schema=_LetterBody
            )
        ).body
    except LLMError:
        raise

    violations = guardrail.check_text(resume, candidate)
    if not violations:
        return CoverLetterResult(body=candidate, changed=True)

    # One retry, with the specific violations named — same pattern as tailor.py.
    log.warning(
        "cover_letter: %d guardrail violation(s) on first attempt", len(violations)
    )

    retry_prompt = (
        RETRY_PREFIX.format(violations=guardrail.summarize(violations))
        + "\n\n"
        + base_prompt
    )

    try:
        candidate = (
            await provider.complete_structured(
                system=SYSTEM_PROMPT, user=retry_prompt, schema=_LetterBody
            )
        ).body
    except LLMError as exc:
        log.warning("cover_letter: retry failed (%s); falling back to template", exc)
        return CoverLetterResult(
            body=_fallback_letter(resume, job),
            changed=False,
            fell_back=True,
            violations=violations,
            warning=(
                "Cover letter generation was rejected by the no-fabrication check and "
                "the retry failed. A neutral templated letter was used instead."
            ),
        )

    violations = guardrail.check_text(resume, candidate)
    if not violations:
        return CoverLetterResult(body=candidate, changed=True)

    # Fail closed. The user gets a truthful (if generic) letter and an explicit heads-up.
    log.warning(
        "cover_letter: %d violation(s) persisted after retry; falling back to template",
        len(violations),
    )
    return CoverLetterResult(
        body=_fallback_letter(resume, job),
        changed=False,
        fell_back=True,
        violations=violations,
        warning=(
            "Cover letter generation introduced numbers that aren't in your resume, "
            "twice. A neutral templated letter was used instead. The flagged items are "
            "listed below — a more capable model usually fixes this."
        ),
    )
