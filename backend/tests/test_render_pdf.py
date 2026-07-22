"""PDF render tests — the single-page guarantee, plus content survival.

The product promise is "always a single PDF file with one page." These tests hold the
renderer to that: a normal resume renders to one page, and — the case that actually
threatens the guarantee — a resume with far too much content is *scaled down* to fit one
page rather than spilling onto a second. Content is read back out of the generated PDF so
the assertions are about a real file, not the model.
"""

from __future__ import annotations

import pypdfium2 as pdfium
import pytest

from app.schemas import (
    Basics,
    Education,
    Project,
    Skill,
    StructuredResume,
    Work,
)
from app.services.render_pdf import PDFRenderError, render_pdf


@pytest.fixture
def resume() -> StructuredResume:
    return StructuredResume(
        basics=Basics(
            name="Jane Doe",
            label="Backend Engineer",
            email="jane@example.com",
            phone="+1 555 0100",
            summary="Backend engineer focused on Python services.",
        ),
        work=[
            Work(
                name="Acme Corp",
                position="Software Engineer",
                startDate="2022-01",
                endDate="2024-06",
                highlights=["Reduced p95 latency by 15%.", "Migrated 12 services."],
            ),
        ],
        education=[
            Education(institution="State University", studyType="BSc", area="Computer Science"),
        ],
        skills=[Skill(name="Languages", keywords=["Python", "SQL"])],
        projects=[Project(name="Ledger", description="Double-entry bookkeeping.")],
    )


def _page_count(path) -> int:
    pdf = pdfium.PdfDocument(str(path))
    try:
        return len(pdf)
    finally:
        pdf.close()


def _text(path) -> str:
    pdf = pdfium.PdfDocument(str(path))
    try:
        return "\n".join(
            pdf[i].get_textpage().get_text_range() for i in range(len(pdf))
        )
    finally:
        pdf.close()


def test_output_is_a_real_pdf(resume, tmp_path) -> None:
    out = render_pdf(resume, tmp_path / "resume.pdf")
    assert out.exists()
    assert out.read_bytes()[:5] == b"%PDF-"


def test_normal_resume_is_one_page(resume, tmp_path) -> None:
    out = render_pdf(resume, tmp_path / "resume.pdf")
    assert _page_count(out) == 1


def test_content_survives_into_the_pdf(resume, tmp_path) -> None:
    out = render_pdf(resume, tmp_path / "resume.pdf")
    text = _text(out)
    assert "Jane Doe" in text
    assert "Acme Corp" in text
    assert "15%" in text


def test_oversized_resume_is_shrunk_to_one_page(tmp_path) -> None:
    """The real threat to the guarantee: enough content to overflow. Must stay one page."""
    huge = StructuredResume(
        basics=Basics(name="Jane Doe", email="jane@example.com"),
        work=[
            Work(
                name=f"Company {i}",
                position="Engineer",
                startDate="2020-01",
                endDate="2024-01",
                highlights=[f"Did an important and lengthy thing number {j}." for j in range(8)],
            )
            for i in range(12)
        ],
    )
    out = render_pdf(huge, tmp_path / "huge.pdf")
    assert _page_count(out) == 1


def test_special_characters_do_not_break_the_render(tmp_path) -> None:
    """<, >, & are markup to reportlab — unescaped they raise or corrupt the layout."""
    resume = StructuredResume(
        basics=Basics(name="A&B <Test>", email="a@b.com", summary="Scaled 3x & <fast>"),
        work=[Work(name="R&D <Labs>", position="Eng", highlights=["Cut cost by 5% <win>"])],
    )
    out = render_pdf(resume, tmp_path / "special.pdf")
    assert _page_count(out) == 1
    assert "A&B" in _text(out)


def test_empty_resume_does_not_crash(tmp_path) -> None:
    out = render_pdf(StructuredResume(basics=Basics()), tmp_path / "empty.pdf")
    assert out.exists()
    assert _page_count(out) == 1
