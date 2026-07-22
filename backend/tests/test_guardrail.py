"""Guardrail tests.

These are the tests that matter most in this project. The guardrail is the only thing
standing between a language model and a resume that claims a job the user never had, so
each test below is a specific fabrication we must catch — and, just as importantly, a
legitimate edit we must NOT flag.
"""

from __future__ import annotations

import pytest

from app.schemas import Basics, Education, Project, Skill, StructuredResume, Work
from app.services import guardrail


@pytest.fixture
def base() -> StructuredResume:
    return StructuredResume(
        basics=Basics(
            name="Jane Doe",
            email="jane@example.com",
            summary="Backend engineer focused on Python services.",
        ),
        work=[
            Work(
                name="Acme Corp",
                position="Software Engineer",
                startDate="2022-01",
                endDate="2024-06",
                highlights=[
                    "Reduced p95 API latency by 15% by adding a Redis cache layer.",
                    "Migrated 12 services from Flask to FastAPI.",
                ],
            )
        ],
        education=[
            Education(
                institution="State University",
                studyType="BSc",
                area="Computer Science",
                startDate="2018-09",
                endDate="2022-05",
            )
        ],
        skills=[Skill(name="Languages", keywords=["Python", "SQL"])],
        projects=[Project(name="Ledger", description="Double-entry bookkeeping in Django.")],
    )


def _kinds(violations) -> set[str]:
    return {v.kind for v in violations}


# --- legitimate tailoring must pass ------------------------------------------


def test_clean_rewrite_passes(base: StructuredResume) -> None:
    """Rephrasing, reordering, and dropping bullets are the point of tailoring."""
    tailored = base.model_copy(deep=True)
    tailored.basics.summary = "Backend engineer specializing in high-throughput Python APIs."
    tailored.work[0].highlights = [
        "Migrated 12 services from Flask to FastAPI.",
        "Cut p95 API latency 15% via a Redis caching layer.",
    ]
    assert guardrail.check(base, tailored) == []


def test_surfacing_a_buried_skill_passes(base: StructuredResume) -> None:
    """Redis appears in a bullet, not the skills list. Promoting it is honest."""
    tailored = base.model_copy(deep=True)
    tailored.skills.append(Skill(name="Infrastructure", keywords=["Redis"]))
    assert guardrail.check(base, tailored) == []


def test_accent_and_case_differences_pass(base: StructuredResume) -> None:
    """Cosmetic normalization must not read as a changed employer."""
    tailored = base.model_copy(deep=True)
    tailored.work[0].name = "ACME  Corp"
    assert guardrail.check(base, tailored) == []


def test_dropping_an_entry_passes(base: StructuredResume) -> None:
    tailored = base.model_copy(deep=True)
    tailored.projects = []
    assert guardrail.check(base, tailored) == []


# --- fabrication must be caught ----------------------------------------------


def test_invented_employer_is_caught(base: StructuredResume) -> None:
    tailored = base.model_copy(deep=True)
    tailored.work.append(
        Work(name="Google", position="Software Engineer", startDate="2022-01", endDate="2024-06")
    )
    assert "employer" in _kinds(guardrail.check(base, tailored))


def test_promoted_job_title_is_caught(base: StructuredResume) -> None:
    """The subtlest fabrication: same employer, same dates, inflated title."""
    tailored = base.model_copy(deep=True)
    tailored.work[0].position = "Senior Staff Software Engineer"
    assert "title" in _kinds(guardrail.check(base, tailored))


def test_stretched_end_date_is_caught(base: StructuredResume) -> None:
    """Closing an employment gap by extending a date."""
    tailored = base.model_copy(deep=True)
    tailored.work[0].endDate = "2025-06"
    assert "date" in _kinds(guardrail.check(base, tailored))


def test_inflated_metric_is_caught(base: StructuredResume) -> None:
    """Every word around it is true; the number is not."""
    tailored = base.model_copy(deep=True)
    tailored.work[0].highlights[0] = "Reduced p95 API latency by 60% with a Redis cache."
    violations = guardrail.check(base, tailored)
    assert "metric" in _kinds(violations)
    assert any(v.value == "60%" for v in violations)


def test_phantom_skill_from_jd_is_caught(base: StructuredResume) -> None:
    """The failure mode we most expect: JD says Kubernetes, model adds Kubernetes."""
    tailored = base.model_copy(deep=True)
    tailored.skills.append(Skill(name="Orchestration", keywords=["Kubernetes"]))
    violations = guardrail.check(base, tailored)
    assert "skill" in _kinds(violations)
    assert any(v.value == "Kubernetes" for v in violations)


def test_bare_skill_with_no_keywords_is_still_checked(base: StructuredResume) -> None:
    """Category labels are free, but a standalone skill entry is a real claim."""
    tailored = base.model_copy(deep=True)
    tailored.skills.append(Skill(name="Kubernetes"))
    assert "skill" in _kinds(guardrail.check(base, tailored))


def test_regrouping_skills_under_new_labels_passes(base: StructuredResume) -> None:
    """Renaming "Languages" to "Core Technologies" reorganizes; it doesn't assert."""
    tailored = base.model_copy(deep=True)
    tailored.skills[0].name = "Core Technologies"
    assert guardrail.check(base, tailored) == []


def test_invented_degree_is_caught(base: StructuredResume) -> None:
    tailored = base.model_copy(deep=True)
    tailored.education[0].studyType = "MSc"
    assert "degree" in _kinds(guardrail.check(base, tailored))


def test_invented_institution_is_caught(base: StructuredResume) -> None:
    tailored = base.model_copy(deep=True)
    tailored.education[0].institution = "Stanford University"
    assert "institution" in _kinds(guardrail.check(base, tailored))


def test_invented_project_is_caught(base: StructuredResume) -> None:
    tailored = base.model_copy(deep=True)
    tailored.projects.append(Project(name="Distributed Raft Store"))
    assert "project" in _kinds(guardrail.check(base, tailored))


def test_multiple_fabrications_all_reported(base: StructuredResume) -> None:
    """The retry prompt needs every violation, not just the first."""
    tailored = base.model_copy(deep=True)
    tailored.work[0].position = "Principal Engineer"
    tailored.work[0].endDate = "2025-12"
    tailored.skills.append(Skill(name="Cloud", keywords=["Terraform"]))
    assert {"title", "date", "skill"} <= _kinds(guardrail.check(base, tailored))


# --- normalization edge cases -------------------------------------------------


def test_equivalent_number_formats_do_not_false_positive(base: StructuredResume) -> None:
    """`$1,200` vs `1200` is a formatting change, not a fabricated figure."""
    base = base.model_copy(deep=True)
    base.work[0].highlights.append("Saved $1,200.00 per month in hosting costs.")
    tailored = base.model_copy(deep=True)
    tailored.work[0].highlights[-1] = "Saved $1200 monthly in hosting."
    assert "metric" not in _kinds(guardrail.check(base, tailored))


def test_small_incidental_numbers_are_not_flagged(base: StructuredResume) -> None:
    """Flagging "3" in "3 teams" would bury real violations in noise."""
    tailored = base.model_copy(deep=True)
    tailored.work[0].highlights.append("Partnered with 3 teams on the rollout.")
    assert "metric" not in _kinds(guardrail.check(base, tailored))


def test_summarize_lists_violations(base: StructuredResume) -> None:
    tailored = base.model_copy(deep=True)
    tailored.work[0].position = "VP of Engineering"
    text = guardrail.summarize(guardrail.check(base, tailored))
    assert "VP of Engineering" in text
