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
from app.schemas import Basics, JobRecord, Skill, StructuredResume, Work
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
        basics=Basics(name="Jane Doe", summary="Backend engineer."),
        work=[
            Work(
                name="Acme Corp",
                position="Software Engineer",
                startDate="2022-01",
                endDate="2024-06",
                highlights=["Reduced latency by 15%."],
            )
        ],
        skills=[Skill(name="Languages", keywords=["Python"])],
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
    out.skills.append(Skill(name="Infra", keywords=["Kubernetes"]))
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
    assert "Kubernetes" in provider.calls[1]
    assert "violation" in provider.calls[1].lower()


async def test_persistent_violation_falls_back_to_base(base, job) -> None:
    """The critical path: two bad attempts must ship the user's own resume, not the fake."""
    provider = StubProvider([_fabricated(base), _fabricated(base)])
    result = await tailor(provider, base, job)

    assert result.fell_back is True
    assert result.changed is False
    assert result.resume == base, "fallback must be the untouched base resume"
    assert result.warning and "original" in result.warning.lower()
    assert any(v.value == "Kubernetes" for v in result.violations)


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
