"""tailor() control-flow tests.

The guardrail tests prove we can *detect* fabrication. These prove we *act* on it
correctly — retry once, then fail closed to the untruthful-but-safe option (the user's
own resume), never shipping flagged content.

A stub provider stands in for the LLM so the control flow is deterministic and testable
without a key or a network call.
"""

from __future__ import annotations

import pytest

from app.llm.base import LLMError, LLMProvider
from app.schemas import Basics, Education, JobRecord, Project, Skill, StructuredResume, Work
from app.services.tailor import tailor


class StubProvider(LLMProvider):
    """Returns a scripted resume per call so we can drive each branch."""

    name = "stub"

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    async def complete_structured(self, *, system, user, schema, max_tokens=16000):
        self.calls.append(user)
        if not self._responses:
            raise AssertionError("StubProvider called more times than scripted")
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    async def health(self):
        return True, "stub"


@pytest.fixture
def base() -> StructuredResume:
    return StructuredResume(
        basics=Basics(name="Jane Doe", email="jane@example.com", summary="Backend engineer."),
        work=[
            Work(
                name="Acme Corp",
                position="Software Engineer",
                startDate="2022-01",
                endDate="2024-06",
                highlights=["Reduced latency by 15%."],
            )
        ],
        education=[
            Education(institution="State University, USA", studyType="BSc (Hons)", area="CS")
        ],
        skills=[
            Skill(name="Languages", keywords=["Python"]),
            Skill(name="Design", keywords=["Figma"]),
        ],
        projects=[Project(name="Ledger", description="Double-entry bookkeeping app.")],
    )


@pytest.fixture
def job() -> JobRecord:
    return JobRecord(
        id="greenhouse:acme:1",
        source="greenhouse",
        title="Senior Backend Engineer",
        company="Globex",
        apply_url="https://example.com/apply",
        description="We need Python and Kubernetes experience.",
    )


def _clean(base: StructuredResume) -> StructuredResume:
    out = base.model_copy(deep=True)
    out.basics.summary = "Backend engineer with a focus on Python services."
    return out


def _fabricated(base: StructuredResume) -> StructuredResume:
    out = base.model_copy(deep=True)
    out.projects.append(Project(name="Distributed Raft Store"))
    return out


async def test_clean_first_attempt_is_returned(base, job) -> None:
    provider = StubProvider([_clean(base)])
    result = await tailor(provider, base, job)

    assert result.changed is True
    assert result.fell_back is False
    assert result.violations == []
    assert len(provider.calls) == 1, "a clean result must not trigger a retry"


async def test_violation_triggers_retry_with_feedback(base, job) -> None:
    provider = StubProvider([_fabricated(base), _clean(base)])
    result = await tailor(provider, base, job)

    assert result.changed is True
    assert result.fell_back is False
    assert len(provider.calls) == 2

    # The retry must name the specific invented value — a generic "try again" doesn't work.
    assert "Distributed Raft Store" in provider.calls[1]
    assert "violation" in provider.calls[1].lower()


def _education_reworded(base: StructuredResume) -> StructuredResume:
    """A real institution, just reworded — not fabricated, but would fail the
    guardrail's exact-match whitelist if it ever reached it."""
    out = base.model_copy(deep=True)
    out.education[0].institution = "State University"  # dropped ", USA"
    out.education[0].studyType = "Bachelor's Degree"  # reworded from "BSc (Hons)"
    return out


async def test_reworded_education_is_replaced_not_flagged(base, job) -> None:
    """Root-cause fix for the false positive seen with qwen3:14b: the model rewording a
    real institution/degree must never reach the guardrail at all, because education is
    now locked to the base resume in code before the check runs."""
    provider = StubProvider([_education_reworded(base)])
    result = await tailor(provider, base, job)

    assert result.violations == []
    assert result.fell_back is False
    assert result.resume.education == base.education
    assert len(provider.calls) == 1, "reworded-but-locked fields must not trigger a retry"


def _education_fabricated(base: StructuredResume) -> StructuredResume:
    out = base.model_copy(deep=True)
    out.education.append(Education(institution="Fake University", studyType="PhD"))
    return out


async def test_fabricated_education_is_silently_replaced(base, job) -> None:
    """A genuinely invented school must also never reach the live application — enforced
    the same way as a rewording, by never letting education leave the base resume."""
    provider = StubProvider([_education_fabricated(base)])
    result = await tailor(provider, base, job)

    assert result.resume.education == base.education
    assert not any(e.institution == "Fake University" for e in result.resume.education)


def _skills_hallucinated(base: StructuredResume) -> StructuredResume:
    out = base.model_copy(deep=True)
    out.skills = [Skill(name="Cloud", keywords=["Kubernetes", "AWS", "Terraform"])]
    return out


async def test_hallucinated_skills_never_reach_the_output(base, job) -> None:
    """The dominant real-world failure: qwen3:8b invented ~30 technologies in one run.
    Skills are never taken from the model's output at all — a deterministic keyword
    filter selects from the base resume's own skills instead, so there's nothing for the
    model to hallucinate into."""
    provider = StubProvider([_skills_hallucinated(base)])
    result = await tailor(provider, base, job)

    assert result.violations == []
    kept = {kw for s in result.resume.skills for kw in s.keywords}
    assert kept == {"Python", "Figma"}
    assert "Kubernetes" not in kept and "AWS" not in kept and "Terraform" not in kept


async def test_skills_are_ranked_by_job_description_overlap(base, job) -> None:
    """job.description is "We need Python and Kubernetes experience." — the base resume's
    Python skill group should rank ahead of the unrelated Figma one."""
    provider = StubProvider([_clean(base)])
    result = await tailor(provider, base, job)

    assert result.resume.skills[0].keywords == ["Python"]


def _work_reframed_with_bad_metric(base: StructuredResume) -> StructuredResume:
    out = base.model_copy(deep=True)
    out.basics.summary = "Backend engineer with strong frontend skills."  # honest reframe
    out.work[0].position = "Frontend Engineer"  # allowed title reframe, same real job
    out.work[0].highlights = ["Cut checkout latency by 99%."]  # fabricated metric
    return out


async def test_metric_violation_reverts_only_that_work_entry(base, job) -> None:
    """Partial repair, the headline feature: a fabricated number in one bullet must not
    cost the honest summary/title reframing elsewhere in the same resume — only the
    offending work entry's highlights revert, everything else keeps the tailored version."""
    provider = StubProvider(
        [_work_reframed_with_bad_metric(base), _work_reframed_with_bad_metric(base)]
    )
    result = await tailor(provider, base, job)

    assert result.fell_back is False
    assert result.changed is True
    assert result.resume.basics.summary == "Backend engineer with strong frontend skills."
    assert result.resume.work[0].position == "Frontend Engineer", "reframe must survive repair"
    assert result.resume.work[0].highlights == base.work[0].highlights, "bad bullet reverted"
    assert any(v.kind == "metric" for v in result.violations)
    assert result.warning and "partially" in result.warning.lower()


def _extra_fake_employer(base: StructuredResume) -> StructuredResume:
    out = base.model_copy(deep=True)
    out.basics.summary = "Backend engineer with strong frontend skills."
    out.work[0].position = "Frontend Engineer"
    out.work.append(Work(name="FakeCorp", position="Engineer"))
    return out


async def test_invented_employer_is_dropped_keeps_other_tailoring(base, job) -> None:
    """An entry with no base equivalent can't be "reverted" — it's dropped entirely, now
    silently during enforcement (see `_enforce_work_facts`), before the guardrail even
    runs — but that must not cost the honest tailoring on the real, unrelated entry."""
    provider = StubProvider([_extra_fake_employer(base)])
    result = await tailor(provider, base, job)

    assert result.changed is True
    assert result.fell_back is False
    assert result.violations == [], "no base equivalent to compare against — never reaches the check"
    assert [w.name for w in result.resume.work] == ["Acme Corp"]
    assert result.resume.work[0].position == "Frontend Engineer"


async def test_mangled_employer_is_matched_by_position_not_dropped(job) -> None:
    """Real bug found live against qwen3:14b: instead of honestly reframing a job title,
    it renamed the employer AND invented a different multi-year date range for two real
    jobs — a different unverifiable "fact" in the same slot, not a rewording. The
    guardrail caught it, but with an unrecognizable employer had nothing to revert it
    *to*, so it dropped two of three real jobs from the resume.

    `_enforce_work_facts` closes this: employer/dates are locked in code before the
    guardrail ever runs, matched by employer name first (so reordering keeps working),
    falling back to "whichever real job hasn't been claimed yet, in base order" for an
    entry whose employer doesn't match anything — losing a real job is worse than a
    best-effort positional guess."""
    base = StructuredResume(
        basics=Basics(name="Jane Doe", summary="Backend engineer."),
        work=[
            Work(name="Acme Corp", position="Software Engineer", startDate="2022-01", endDate="2024-06"),
            Work(name="Beta LLC", position="Data Analyst", startDate="2020-01", endDate="2021-12"),
        ],
    )
    candidate = base.model_copy(deep=True)
    candidate.work[0].position = "Backend Engineer"  # honest reframe, employer/dates untouched
    candidate.work[1] = Work(
        name="Junior Analytics Role",  # not a real employer — the model's invention
        position="Data Analytics Specialist",  # shares "data" with the real "Data Analyst"
        startDate="2018-03",
        endDate="2019-11",
    )

    provider = StubProvider([candidate])
    result = await tailor(provider, base, job)

    assert [w.name for w in result.resume.work] == ["Acme Corp", "Beta LLC"], "both real jobs survive"
    assert result.resume.work[0].position == "Backend Engineer"
    assert result.resume.work[1].position == "Data Analytics Specialist", "honest framing kept even on the guessed match"
    assert result.resume.work[1].startDate == "2020-01"
    assert result.resume.work[1].endDate == "2021-12"


def _fabricated_tool_in_label(base: StructuredResume) -> StructuredResume:
    out = base.model_copy(deep=True)
    out.basics.label = "Data & Power BI Analyst"
    return out


async def test_fabricated_tool_in_headline_reverts_headline(base, job) -> None:
    """Real bug found live: a named tool the user has never touched ("Power BI") slipped
    into the tailored headline unchecked. Must revert, same as a fabricated figure."""
    provider = StubProvider([_fabricated_tool_in_label(base), _fabricated_tool_in_label(base)])
    result = await tailor(provider, base, job)

    assert result.resume.basics.label == base.basics.label
    assert any(v.kind == "skill" and v.where == "basics.label" for v in result.violations)


def _fabricated_tool_in_position(base: StructuredResume) -> StructuredResume:
    out = base.model_copy(deep=True)
    out.work[0].position = "Power BI Developer"
    return out


async def test_fabricated_tool_in_work_title_reverts_the_title_too(base, job) -> None:
    """A fabricated tool inside `position` itself (not just elsewhere in that entry) must
    not survive repair just because title-reframing is normally preserved — the whole
    point of keeping a reworded title is that it's *honest*."""
    provider = StubProvider(
        [_fabricated_tool_in_position(base), _fabricated_tool_in_position(base)]
    )
    result = await tailor(provider, base, job)

    assert result.resume.work[0].position == base.work[0].position
    assert any(v.kind == "skill" and v.where == "work[0].position" for v in result.violations)


def _fabricated_tool_in_project_name(base: StructuredResume) -> StructuredResume:
    out = base.model_copy(deep=True)
    out.projects[0].name = "Ledger — Power BI Edition"  # matches base's "Ledger" project
    return out


async def test_fabricated_tool_in_project_name_reverts_the_name_too(base, job) -> None:
    """Same as the work-title case: a fabricated tool inside the project's own `name`
    must revert even though a fuzzy-matched, honestly-reworded name is normally kept."""
    provider = StubProvider(
        [_fabricated_tool_in_project_name(base), _fabricated_tool_in_project_name(base)]
    )
    result = await tailor(provider, base, job)

    assert result.resume.projects[0].name == base.projects[0].name
    assert any(v.kind == "skill" and v.where == "projects[0].name" for v in result.violations)


def _blank_summary(base: StructuredResume) -> StructuredResume:
    out = base.model_copy(deep=True)
    out.basics.summary = ""
    return out


async def test_blank_summary_falls_back_to_original_even_with_no_violations(base, job) -> None:
    """A blank summary isn't a fabrication (nothing false about an empty string), so the
    guardrail alone would never catch it — qwen3:8b returns one occasionally. Must still
    not ship an empty field just because it's not technically a lie."""
    provider = StubProvider([_blank_summary(base)])
    result = await tailor(provider, base, job)

    assert result.resume.basics.summary == base.basics.summary


def _fabricated_seniority(base: StructuredResume) -> StructuredResume:
    out = base.model_copy(deep=True)
    out.basics.summary = "Experienced engineer with 8+ years building scalable systems."
    return out


async def test_fabricated_years_of_experience_reverts_summary(base, job) -> None:
    """Real bug found live against a job description that heavily implied seniority: the
    old 0-10 "trivial number" exemption let qwen3:8b's "8+ years" claim through
    completely uncaught — a small digit is not automatically a harmless one."""
    provider = StubProvider([_fabricated_seniority(base), _fabricated_seniority(base)])
    result = await tailor(provider, base, job)

    assert result.resume.basics.summary == base.basics.summary
    assert any(v.kind == "metric" and v.where == "basics.summary" for v in result.violations)


def _wiped_work_history(base: StructuredResume) -> StructuredResume:
    out = base.model_copy(deep=True)
    out.work = []
    return out


async def test_empty_work_list_falls_back_to_original(base, job) -> None:
    """Real failure mode seen live: qwen3:8b returned zero work entries in an otherwise
    clean generation. An empty list has no fabricated fact for the guardrail to catch, but
    silently dropping the user's entire employment history is never acceptable."""
    provider = StubProvider([_wiped_work_history(base)])
    result = await tailor(provider, base, job)

    assert result.resume.work == base.work
    assert result.violations == []


def _contact_swapped(base: StructuredResume) -> StructuredResume:
    out = base.model_copy(deep=True)
    out.basics.email = "attacker@evil.example"
    return out


async def test_swapped_contact_info_is_silently_replaced(base, job) -> None:
    """HIGH-1 exploit path: a poisoned JD rewrites basics.email. Contact fields are locked
    to the base resume in code before the guardrail even runs, so the swap never reaches
    the output and never even costs a retry — a stronger guarantee than catch-and-retry."""
    provider = StubProvider([_contact_swapped(base)])
    result = await tailor(provider, base, job)

    assert result.resume.basics.email == base.basics.email
    assert result.violations == []
    assert len(provider.calls) == 1


async def test_persistent_violation_falls_back_to_base(base, job) -> None:
    """The critical path: two bad attempts must ship the user's own resume, not the fake."""
    provider = StubProvider([_fabricated(base), _fabricated(base)])
    result = await tailor(provider, base, job)

    assert result.fell_back is True
    assert result.changed is False
    assert result.resume == base, "fallback must be the untouched base resume"
    assert result.warning and "original" in result.warning.lower()
    assert any(v.value == "Distributed Raft Store" for v in result.violations)


async def test_retry_error_falls_back_rather_than_raising(base, job) -> None:
    """A provider failure mid-retry must not surface flagged content or a 500."""
    provider = StubProvider([_fabricated(base), LLMError("rate limited")])
    result = await tailor(provider, base, job)

    assert result.fell_back is True
    assert result.resume == base


async def test_first_attempt_error_propagates(base, job) -> None:
    """If we never got a result at all, that's a real error the user should see."""
    provider = StubProvider([LLMError("no API key configured")])
    with pytest.raises(LLMError):
        await tailor(provider, base, job)


async def test_prompt_contains_job_and_resume(base, job) -> None:
    provider = StubProvider([_clean(base)])
    await tailor(provider, base, job)

    prompt = provider.calls[0]
    assert "Senior Backend Engineer" in prompt
    assert "Globex" in prompt
    assert "Acme Corp" in prompt
    assert "Kubernetes" in prompt, "the JD text must reach the model"


async def test_long_job_description_is_truncated(base) -> None:
    """Guards against blowing the context window on a pathological posting."""
    huge = JobRecord(
        id="x:1",
        source="x",
        title="Engineer",
        company="Corp",
        apply_url="https://example.com",
        description="word " * 20000,
    )
    provider = StubProvider([_clean(base)])
    await tailor(provider, base, huge)
    assert "(truncated)" in provider.calls[0]
