"""PDF renderer — pure-Python, always one page.

The product guarantee is a single-page PDF on every apply, with no system dependencies.
That rules out the old LaTeX/Tectonic path (a heavy external binary that had to be
installed separately and could be absent). Instead this builds the document with
reportlab, which ships as a normal Python wheel and therefore works everywhere the app
runs.

Two things make the "always one page" guarantee hold:

  * Every flowable is wrapped in a single ``KeepInFrame(mode="shrink")`` sized to the
    page's printable area. If the content is taller than one page, reportlab scales it
    down to fit rather than spilling onto a second page. Nothing is ever truncated — a
    dense resume just renders slightly smaller.
  * The frame fills exactly one page, so the document can only ever be one page long.

The DOCX renderer remains the primary ATS output; this PDF is the human-facing copy, so
it can afford a little more polish (section rules, greyed metadata).
"""

from __future__ import annotations

import logging
from pathlib import Path
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib.colors import Color
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    HRFlowable,
    KeepInFrame,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from app.schemas import StructuredResume

log = logging.getLogger(__name__)

# Helvetica is a built-in PDF base-14 font: no font file to ship, present in every
# viewer, and metrically close to Arial so it reads like a normal resume.
BODY_FONT = "Helvetica"
BOLD_FONT = "Helvetica-Bold"

INK = Color(0x26 / 255, 0x31 / 255, 0x37 / 255)
MUTED = Color(0x5A / 255, 0x63 / 255, 0x68 / 255)

# Page geometry (points). Margins mirror the DOCX renderer so the two documents feel
# like the same resume.
LEFT_MARGIN = RIGHT_MARGIN = 54
TOP_MARGIN = BOTTOM_MARGIN = 44
_PAGE_W, _PAGE_H = LETTER
FRAME_W = _PAGE_W - LEFT_MARGIN - RIGHT_MARGIN
FRAME_H = _PAGE_H - TOP_MARGIN - BOTTOM_MARGIN


class PDFRenderError(RuntimeError):
    """reportlab produced no usable PDF. Actionable, not a 500."""


_NAME = ParagraphStyle(
    "Name", fontName=BOLD_FONT, fontSize=19, leading=22,
    alignment=TA_CENTER, textColor=INK, spaceAfter=2,
)
_LABEL = ParagraphStyle(
    "Label", fontName=BODY_FONT, fontSize=11, leading=13,
    alignment=TA_CENTER, textColor=MUTED, spaceAfter=2,
)
_CONTACT = ParagraphStyle(
    "Contact", fontName=BODY_FONT, fontSize=8.5, leading=11,
    alignment=TA_CENTER, textColor=MUTED, spaceAfter=8,
)
_HEADING = ParagraphStyle(
    "Heading", fontName=BOLD_FONT, fontSize=11, leading=13,
    textColor=INK, spaceBefore=9, spaceAfter=1,
)
_ENTRY = ParagraphStyle(
    "Entry", fontName=BODY_FONT, fontSize=10.5, leading=13,
    textColor=INK, spaceBefore=5,
)
_META = ParagraphStyle(
    "Meta", fontName=BODY_FONT, fontSize=8.5, leading=11,
    textColor=MUTED, spaceAfter=1,
)
_BODY = ParagraphStyle(
    "Body", fontName=BODY_FONT, fontSize=10, leading=13,
    textColor=INK, spaceAfter=1,
)
_BULLET = ParagraphStyle(
    "Bullet", fontName=BODY_FONT, fontSize=10, leading=13,
    textColor=INK, leftIndent=12, bulletIndent=1, spaceAfter=1,
)


def _esc(value) -> str:
    """Escape user text for reportlab's mini-markup, which parses & < > as XML."""
    return _xml_escape("" if value is None else str(value))


def _date_range(start: str, end: str) -> str:
    if start and end:
        return f"{start} – {end}"
    return start or end or ""


def _contact_line(resume: StructuredResume) -> str:
    basics = resume.basics
    location = ", ".join(p for p in (basics.location.city, basics.location.region) if p)
    pieces = [basics.email, basics.phone, location, basics.url]
    pieces += [p.url for p in basics.profiles if p.url]
    return "  ·  ".join(p for p in pieces if p)


def _heading(text: str) -> list:
    """A section heading followed by a thin rule — the one bit of visual polish."""
    return [
        Paragraph(_esc(text.upper()), _HEADING),
        HRFlowable(width="100%", thickness=0.6, color=MUTED,
                   spaceBefore=1, spaceAfter=3),
    ]


def _flowables(resume: StructuredResume) -> list:
    story: list = []

    # --- header ----------------------------------------------------------
    story.append(Paragraph(_esc(resume.basics.name), _NAME))
    if resume.basics.label:
        story.append(Paragraph(_esc(resume.basics.label), _LABEL))
    contact = _contact_line(resume)
    if contact:
        story.append(Paragraph(_esc(contact), _CONTACT))

    # --- summary ---------------------------------------------------------
    if resume.basics.summary:
        story += _heading("Summary")
        story.append(Paragraph(_esc(resume.basics.summary), _BODY))

    # --- experience ------------------------------------------------------
    if resume.work:
        story += _heading("Experience")
        for job in resume.work:
            title = _esc(job.position)
            if job.name:
                sep = " — " if job.position else ""
                title = f"<b>{title}</b>{_esc(sep)}{_esc(job.name)}"
            elif job.position:
                title = f"<b>{title}</b>"
            if title:
                story.append(Paragraph(title, _ENTRY))
            meta = "  ·  ".join(
                p for p in (_date_range(job.startDate, job.endDate), job.location) if p
            )
            if meta:
                story.append(Paragraph(_esc(meta), _META))
            if job.summary:
                story.append(Paragraph(_esc(job.summary), _BODY))
            for highlight in job.highlights:
                story.append(Paragraph(_esc(highlight), _BULLET, bulletText="•"))

    # --- education -------------------------------------------------------
    if resume.education:
        story += _heading("Education")
        for edu in resume.education:
            degree = " ".join(p for p in (edu.studyType, edu.area) if p)
            line = f"<b>{_esc(degree)}</b>" if degree else ""
            if edu.institution:
                sep = " — " if degree else ""
                line += f"{_esc(sep)}{_esc(edu.institution)}"
            if line:
                story.append(Paragraph(line, _ENTRY))
            meta = "  ·  ".join(
                p for p in (
                    _date_range(edu.startDate, edu.endDate),
                    f"GPA {edu.score}" if edu.score else "",
                ) if p
            )
            if meta:
                story.append(Paragraph(_esc(meta), _META))
            if edu.courses:
                story.append(
                    Paragraph(f"Relevant coursework: {_esc(', '.join(edu.courses))}", _BODY)
                )

    # --- skills ----------------------------------------------------------
    if resume.skills:
        story += _heading("Skills")
        # Mirror the DOCX renderer: a skill is either a labelled group
        # ("Languages: Python, SQL") or a bare skill. Emitting "name: "
        # unconditionally would leave a dangling colon on bare entries.
        for skill in resume.skills:
            if skill.name and skill.keywords:
                text = f"<b>{_esc(skill.name)}:</b> {_esc(', '.join(skill.keywords))}"
            elif skill.name:
                text = _esc(skill.name)
            elif skill.keywords:
                text = _esc(", ".join(skill.keywords))
            else:
                continue
            story.append(Paragraph(text, _BODY))

    # --- projects --------------------------------------------------------
    if resume.projects:
        story += _heading("Projects")
        for project in resume.projects:
            line = f"<b>{_esc(project.name)}</b>" if project.name else ""
            date_range = _date_range(project.startDate, project.endDate)
            if date_range:
                line += f"  ({_esc(date_range)})"
            if line:
                story.append(Paragraph(line, _ENTRY))
            if project.description:
                story.append(Paragraph(_esc(project.description), _BODY))
            for highlight in project.highlights:
                story.append(Paragraph(_esc(highlight), _BULLET, bulletText="•"))
            if project.keywords:
                story.append(
                    Paragraph(f"Technologies: {_esc(', '.join(project.keywords))}", _BODY)
                )

    return story


def render_pdf(resume: StructuredResume, output_path: Path) -> Path:
    """Render ``resume`` to a single-page PDF at ``output_path``.

    Preconditions:
    output_path names a .pdf file in a writable directory.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    story = _flowables(resume)
    if not story:
        # An empty resume would otherwise make KeepInFrame divide by a zero height.
        # reportlab's base unit is the point, so this is a 1pt spacer.
        story = [Spacer(1, 1)]

    # One frame, one page. mode="shrink" scales the whole story down if it is taller than
    # the printable area — the guarantee that the output is always exactly one page.
    fitted = KeepInFrame(
        FRAME_W, FRAME_H, content=story, mode="shrink", hAlign="LEFT", vAlign="TOP",
    )

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
        title=f"{resume.basics.name} — Resume" if resume.basics.name else "Resume",
    )

    try:
        doc.build([fitted])
    except Exception as exc:  # reportlab raises bare Exceptions on layout failure
        raise PDFRenderError(f"PDF generation failed: {exc}") from exc

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise PDFRenderError("PDF generation produced an empty file.")

    return output_path
