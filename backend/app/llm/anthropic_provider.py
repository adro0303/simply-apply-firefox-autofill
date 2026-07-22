"""Anthropic adapter.

Uses `messages.parse()`, which constrains decoding to the Pydantic schema and returns a
validated instance — the model cannot emit malformed JSON, so there is no parse-and-retry
path to maintain.

Model notes (Claude Opus 4.8):
  * `thinking={"type": "adaptive"}` — the model decides how much to reason per request.
    Tailoring against a long JD genuinely benefits from it; there is no token budget to tune.
  * `temperature` / `top_p` / `top_k` are *removed* on this model and return a 400 if sent.
    Output variation is steered by the prompt instead. Do not reintroduce them.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from app.llm.base import LLMError, LLMProvider

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "claude-opus-4-8"


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    requires_key = True

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        if not api_key:
            raise LLMError(
                "No Anthropic API key configured. Add one in Settings, or switch provider."
            )
        self.model = model or DEFAULT_MODEL
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise LLMError("The `anthropic` package is not installed.") from exc
        self._client = AsyncAnthropic(api_key=api_key)

    async def complete_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int = 16000,
    ) -> T:
        try:
            response = await self._client.messages.parse(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                thinking={"type": "adaptive"},
                messages=[{"role": "user", "content": user}],
                output_format=schema,
            )
        except Exception as exc:
            raise LLMError(f"Anthropic request failed: {exc}") from exc

        if response.stop_reason == "refusal":
            raise LLMError(
                "The model declined this request. If the resume or job description "
                "contains unusual content, try editing it and retrying."
            )
        if response.parsed_output is None:
            raise LLMError(
                f"Model returned no structured output (stop_reason={response.stop_reason}). "
                "This usually means max_tokens was too low for the response."
            )
        return response.parsed_output

    async def health(self) -> tuple[bool, str]:
        try:
            model = await self._client.models.retrieve(self.model)
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"
        return True, f"Reachable — {model.display_name}"
