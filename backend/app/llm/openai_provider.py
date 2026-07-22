"""OpenAI adapter — also covers any OpenAI-compatible endpoint.

The base URL is configurable, so this single adapter serves OpenAI, Groq, Together,
OpenRouter, and a local LM Studio server. That is most of the "plug in any API key"
requirement satisfied by one file.

`chat.completions.parse()` is the structured-output path: the schema is enforced at
decode time and the SDK hands back a validated Pydantic instance.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from app.llm.base import LLMError, LLMProvider

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "gpt-4o"


class OpenAIProvider(LLMProvider):
    name = "openai"
    requires_key = True

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        if not api_key:
            raise LLMError(
                "No OpenAI API key configured. Add one in Settings, or switch provider."
            )
        self.model = model or DEFAULT_MODEL
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise LLMError("The `openai` package is not installed.") from exc
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url or None)

        # The structured-output helper moved from `beta.chat.completions.parse` to
        # `chat.completions.parse` partway through the 1.x line. Contributors will have
        # whatever version their lockfile resolved, so bind to whichever exists rather
        # than pinning users to one SDK generation.
        chat = self._client.chat.completions
        self._parse = (
            chat.parse
            if hasattr(chat, "parse")
            else self._client.beta.chat.completions.parse
        )

    async def complete_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int = 16000,
    ) -> T:
        try:
            completion = await self._parse(
                model=self.model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format=schema,
            )
        except Exception as exc:
            raise LLMError(f"OpenAI request failed: {exc}") from exc

        message = completion.choices[0].message
        if getattr(message, "refusal", None):
            raise LLMError(f"The model declined this request: {message.refusal}")
        if message.parsed is None:
            raise LLMError("Model returned no structured output.")
        return message.parsed

    async def health(self) -> tuple[bool, str]:
        """Send a tiny real structured request rather than probing a metadata endpoint.

        `models.retrieve()` is not implemented consistently across OpenAI-compatible
        providers — OpenRouter 404s on it — so a working key would report as broken. More
        importantly, what the user needs to know is "can this config produce structured
        output?", and only an actual completion answers that. Cost is a few tokens.
        """

        class _Ping(BaseModel):
            ok: bool

        try:
            await self.complete_structured(
                system="Reply with ok=true.",
                user="ping",
                schema=_Ping,
                max_tokens=64,
            )
        except LLMError as exc:
            return False, str(exc)
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"
        return True, f"Reachable — {self.model}"
