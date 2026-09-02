"""Guardrail tests.

These are the tests that matter most in this project. The guardrail is the only thing
standing between a language model and a resume that claims a job the user never had, so
each test below is a specific fabrication we must catch — and, just as importantly, a
legitimate edit we must NOT flag.
"""

from __future__ import annotations

import pytest

from app.schemas import Basics, Education, Location, Profile, Project, Skill, StructuredResume, Work
from app.services import guardrail


@pytest.fixture
def base() -> StructuredResume:
    return StructuredResume(
        basics=Basics(
            name="Jane Doe",
            email="jane@example.com",
            phone="+34 675 931 520",
            url="https://janedoe.dev",
            summary="Backend engineer focused on Python services.",
            location=Location(city="Berlin", region="Berlin", countryCode="DE"),
            profiles=[Profile(network="GitHub", username="janedoe", url="https://github.com/janedoe")],
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


def test_untouched_basics_pass(base: StructuredResume) -> None:
    """Reordering/rephrasing elsewhere, with basics left alone, must not flag contact info."""
    tailored = base.model_copy(deep=True)
    tailored.basics.summary = "Backend engineer, Python and distributed systems."
    tailored.work[0].highlights = list(reversed(tailored.work[0].highlights))
    assert "contact" not in _kinds(guardrail.check(base, tailored))


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


def test_swapped_email_is_caught(base: StructuredResume) -> None:
    """The exploit: a poisoned JD makes the model rewrite contact info."""
    tailored = base.model_copy(deep=True)
    tailored.basics.email = "attacker@evil.example"
    violations = guardrail.check(base, tailored)
    assert "contact" in _kinds(violations)
    assert any(v.where == "basics.email" for v in violations)


def test_swapped_phone_url_name_location_and_profile_are_all_caught(
    base: StructuredResume,
) -> None:
    tailored = base.model_copy(deep=True)
    tailored.basics.name = "John Attacker"
    tailored.basics.phone = "+1 555 000 0000"
    tailored.basics.url = "https://evil.example"
    tailored.basics.location.city = "Nowhere"
    tailored.basics.profiles[0].url = "https://github.com/attacker"
    wheres = {v.where for v in guardrail.check(base, tailored)}
    assert {
        "basics.name",
        "basics.phone",
        "basics.url",
        "basics.location.city",
        "basics.profiles[0].url",
    } <= wheres


def test_added_profile_is_caught(base: StructuredResume) -> None:
    tailored = base.model_copy(deep=True)
    tailored.basics.profiles.append(
        Profile(network="Twitter", username="attacker", url="https://twitter.com/attacker")
    )
    violations = guardrail.check(base, tailored)
    assert any(v.where.startswith("basics.profiles[1]") for v in violations)


def test_cosmetic_phone_and_url_formatting_does_not_false_positive(
    base: StructuredResume,
) -> None:
    """`+34 675 931 520` vs `+34675931520`, and a trailing slash, are formatting only."""
    tailored = base.model_copy(deep=True)
    tailored.basics.phone = "+34675931520"
    tailored.basics.url = "https://janedoe.dev/"
    assert "contact" not in _kinds(guardrail.check(base, tailored))


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


# --- check_text (free-prose cover letters) ------------------------------------


def test_check_text_clean_prose_passes(base: StructuredResume) -> None:
    text = (
        "I built a Redis cache layer at Acme Corp that cut p95 latency by 15%, and "
        "migrated 12 services from Flask to FastAPI."
    )
    assert guardrail.check_text(base, text) == []


def test_check_text_catches_fabricated_metric(base: StructuredResume) -> None:
    text = "I improved performance by 60% at Acme Corp."
    violations = guardrail.check_text(base, text)
    assert _kinds(violations) == {"metric"}
    assert any(v.value == "60%" for v in violations)


def test_check_text_ignores_small_incidental_numbers(base: StructuredResume) -> None:
    text = "I led a team of 3 engineers."
    assert guardrail.check_text(base, text) == []


def test_check_text_does_not_flag_false_employer_claims(base: StructuredResume) -> None:
    """Documents the known gap: check_text only catches numbers, not prose claims."""
    text = "I spent five years at Google leading the search infrastructure team."
    assert guardrail.check_text(base, text) == []
