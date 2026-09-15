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


def test_reworded_job_title_is_allowed(base: StructuredResume) -> None:
    """Job title is a deliberate exception to the whitelist for employer/dates: honestly
    reframing the same real job (same employer, same dates) for the target role is
    legitimate tailoring, not fabrication — user decision. The reword still has to share
    real ground with that job (here, "Engineer" — same domain, no seniority claimed), see
    `test_retitling_into_an_unrelated_function_is_caught` and
    `test_unearned_seniority_in_a_reworded_title_is_caught` for what isn't allowed."""
    tailored = base.model_copy(deep=True)
    tailored.work[0].position = "Frontend Engineer"
    assert "title" not in _kinds(guardrail.check(base, tailored))


def test_retitling_into_an_unrelated_function_is_caught(base: StructuredResume) -> None:
    """Real bug found live: qwen3:8b retitled an "Insurance Sales Representative" role
    "Software Engineer" — not a rewording of the real function, a different one, with
    nothing in that job's own content to support it."""
    tailored = base.model_copy(deep=True)
    tailored.work[0].position = "Data Scientist"  # shares nothing with "Software Engineer"
    # or with latency/Redis/Flask/FastAPI highlights — same job title case, different
    # domain entirely, deliberately not overlapping "Engineer"
    violations = guardrail.check(base, tailored)
    assert any(v.kind == "title" and v.where == "work[0].position" for v in violations)


def test_unearned_seniority_in_a_reworded_title_is_caught(base: StructuredResume) -> None:
    """Real bug found live: qwen3:8b promoted "AI & Software Engineer" to "Senior Software
    Engineer" unprompted — the base resume never calls this job "Senior"."""
    tailored = base.model_copy(deep=True)
    tailored.work[0].position = "Senior Software Engineer"
    violations = guardrail.check(base, tailored)
    assert any(v.kind == "title" and v.where == "work[0].position" for v in violations)


def test_seniority_already_true_for_that_job_is_not_flagged(base: StructuredResume) -> None:
    """The seniority check is relative to THAT job's own real title, not a blanket ban —
    if the base resume already says "Lead" for this job, reusing it isn't a claim of
    anything new."""
    based_on_lead = base.model_copy(deep=True)
    based_on_lead.work[0].position = "Software Engineer, Team Lead"
    tailored = based_on_lead.model_copy(deep=True)
    tailored.work[0].position = "Lead Engineer"
    violations = guardrail.check(based_on_lead, tailored)
    assert not any(v.kind == "title" for v in violations)


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


def test_reworded_project_name_is_not_flagged(base: StructuredResume) -> None:
    """Fuzzy project-identity match: base has "Ledger" — a rewording that shares enough
    tokens with a real project must pass, unlike a fully unrelated invented name."""
    tailored = base.model_copy(deep=True)
    tailored.projects[0].name = "Ledger — Double-Entry Bookkeeping App"
    assert "project" not in _kinds(guardrail.check(base, tailored))


def test_multiple_fabrications_all_reported(base: StructuredResume) -> None:
    """The retry prompt needs every violation, not just the first."""
    tailored = base.model_copy(deep=True)
    tailored.work[0].name = "Not The Real Employer"
    tailored.work[0].endDate = "2025-12"
    tailored.skills.append(Skill(name="Cloud", keywords=["Terraform"]))
    assert {"employer", "date", "skill"} <= _kinds(guardrail.check(base, tailored))


# --- normalization edge cases -------------------------------------------------


def test_equivalent_number_formats_do_not_false_positive(base: StructuredResume) -> None:
    """`$1,200` vs `1200` is a formatting change, not a fabricated figure."""
    base = base.model_copy(deep=True)
    base.work[0].highlights.append("Saved $1,200.00 per month in hosting costs.")
    tailored = base.model_copy(deep=True)
    tailored.work[0].highlights[-1] = "Saved $1200 monthly in hosting."
    assert "metric" not in _kinds(guardrail.check(base, tailored))


def test_small_incidental_numbers_are_flagged_too(base: StructuredResume) -> None:
    """No "trivial number" exemption, on purpose (see guardrail._numbers_in) — a small
    digit isn't automatically harmless. Previously 0-10 was exempted to cut noise on
    incidental counts like "3 teams", but that same exemption is exactly what let a real
    fabrication ("8+ years of experience", found live against qwen3:8b) through uncaught.
    Per-field repair means the cost of the occasional incidental false positive is just
    reverting one bullet, not the whole resume — worth it for catching the real case."""
    tailored = base.model_copy(deep=True)
    tailored.work[0].highlights.append("Partnered with 3 teams on the rollout.")
    assert "metric" in _kinds(guardrail.check(base, tailored))


def test_fabricated_years_of_experience_is_caught(base: StructuredResume) -> None:
    """The exact real-world failure this module exists to catch: a small number used to
    assert a seniority/experience claim the base resume never supports."""
    tailored = base.model_copy(deep=True)
    tailored.basics.summary = "Experienced engineer with 8+ years building scalable systems."
    violations = guardrail.check(base, tailored)
    assert any(v.kind == "metric" and v.where == "basics.summary" for v in violations)


def test_fabricated_tool_in_headline_is_caught(base: StructuredResume) -> None:
    """Real bug found live: qwen3:8b's tailored `basics.label` claimed "Power BI Analyst"
    for a job that mentioned Power BI — the base resume never mentions it anywhere. Only
    numbers were checked in free text before this; named tools weren't checked at all."""
    tailored = base.model_copy(deep=True)
    tailored.basics.label = "Data & Power BI Analyst"
    violations = guardrail.check(base, tailored)
    assert any(v.kind == "skill" and v.where == "basics.label" and v.value == "power bi" for v in violations)


def test_known_tool_already_in_base_resume_is_not_flagged(base: StructuredResume) -> None:
    """The check is against the base resume's own text, not a blanket ban — a tool the
    user genuinely has is never a violation just for being on the known-tools list."""
    tailored = base.model_copy(deep=True)
    tailored.basics.summary += " Comfortable with Docker for local development."
    base_with_docker = base.model_copy(deep=True)
    base_with_docker.work[0].highlights.append("Used Docker in CI.")
    violations = guardrail.check(base_with_docker, tailored)
    assert not any(v.kind == "skill" and v.value == "docker" for v in violations)


def test_metric_violation_is_attributed_to_its_field(base: StructuredResume) -> None:
    """`where` must point at the exact field, not "document" — tailor.py's partial
    repair needs to know which section to revert without discarding the whole resume."""
    tailored = base.model_copy(deep=True)
    tailored.work[0].highlights.append("Cut latency by 99%.")
    violations = guardrail.check(base, tailored)
    metric = next(v for v in violations if v.kind == "metric")
    assert metric.where == f"work[0].highlights[{len(tailored.work[0].highlights) - 1}]"


def test_summarize_lists_violations(base: StructuredResume) -> None:
    tailored = base.model_copy(deep=True)
    tailored.work[0].name = "Definitely Not Acme Corp"
    text = guardrail.summarize(guardrail.check(base, tailored))
    assert "Definitely Not Acme Corp" in text


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


def test_check_text_flags_small_incidental_numbers_too(base: StructuredResume) -> None:
    """No trivial-number exemption here either, same reasoning as `check()` — a cover
    letter's "3 engineers" is exactly as capable of being a fabricated headcount as any
    other number, e.g. a fabricated "8 years of experience" claim."""
    text = "I led a team of 3 engineers."
    assert guardrail.check_text(base, text) != []


def test_check_text_does_not_flag_false_employer_claims(base: StructuredResume) -> None:
    """Documents the known gap: check_text only catches numbers, not prose claims."""
    text = "I spent five years at Google leading the search infrastructure team."
    assert guardrail.check_text(base, text) == []
