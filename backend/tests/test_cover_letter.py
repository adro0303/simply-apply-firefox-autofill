"""generate() control-flow tests — same shape as test_tailor.py.

Proves the retry-then-fail-closed behavior: a clean letter ships as-is, a fabricated one
gets one retry with the violation named, and a letter that's still bad falls back to the
templated letter rather than ever shipping flagged prose.
"""

from __future__ import annotations

import pytest

from app.llm.base import LLMError, LLMProvider
from app.schemas import Basics, JobRecord, Skill, StructuredResume, Work
from app.services.cover_letter import _LetterBody, generate


class StubProvider(LLMProvider):
    """Returns a scripted `_LetterBody` per call so each branch is deterministic."""

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


def _clean() -> _LetterBody:
    return _LetterBody(
        body="Dear Hiring Team, I bring Python experience from my time at Acme Corp "
        "where I reduced latency by 15%. Sincerely, Jane Doe"
    )


def _fabricated() -> _LetterBody:
    return _LetterBody(
        body="Dear Hiring Team, I improved performance by 90% at Acme Corp. Sincerely, "
        "Jane Doe"
    )


async def test_clean_first_attempt_is_returned(base, job) -> None:
    provider = StubProvider([_clean()])
    result = await generate(provider, base, job)

    assert result.changed is True
    assert result.fell_back is False
    assert result.violations == []
    assert len(provider.calls) == 1, "a clean result must not trigger a retry"


async def test_violation_triggers_retry_with_feedback(base, job) -> None:
    provider = StubProvider([_fabricated(), _clean()])
    result = await generate(provider, base, job)

    assert result.changed is True
    assert result.fell_back is False
    assert len(provider.calls) == 2
    assert "90%" in provider.calls[1]
    assert "violation" in provider.calls[1].lower()


async def test_persistent_violation_falls_back_to_template(base, job) -> None:
    provider = StubProvider([_fabricated(), _fabricated()])
    result = await generate(provider, base, job)

    assert result.fell_back is True
    assert result.changed is False
    assert "90%" not in result.body
    assert "Acme Corp" in result.body
    assert "Jane Doe" in result.body
    assert result.warning
    assert any(v.value == "90%" for v in result.violations)


async def test_retry_error_falls_back_rather_than_raising(base, job) -> None:
    provider = StubProvider([_fabricated(), LLMError("rate limited")])
    result = await generate(provider, base, job)

    assert result.fell_back is True
    assert "90%" not in result.body


async def test_first_attempt_error_propagates(base, job) -> None:
    provider = StubProvider([LLMError("no API key configured")])
    with pytest.raises(LLMError):
        await generate(provider, base, job)


async def test_prompt_contains_job_and_resume(base, job) -> None:
    provider = StubProvider([_clean()])
    await generate(provider, base, job)

    prompt = provider.calls[0]
    assert "Senior Backend Engineer" in prompt
    assert "Globex" in prompt
    assert "Acme Corp" in prompt
