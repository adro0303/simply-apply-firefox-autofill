"""Provider-agnostic LLM interface.

One method: given a system prompt, a user prompt, and a Pydantic model, return a
validated instance of that model. Everything the app asks an LLM to do — parsing a
resume, tailoring one — is structured extraction, so a single structured-output method
covers the whole surface.

Pushing schema validation into the interface (rather than returning a string and parsing
downstream) means each provider can use its *native* structured-output mechanism:
Anthropic's `messages.parse`, OpenAI's `chat.completions.parse`, Ollama's `format`
JSON-schema parameter. That is strictly more reliable than asking for JSON in the prompt
and hoping — the model is constrained at decode time rather than corrected after the fact.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """Raised for any provider failure — missing key, transport, or schema violation.

    The routers turn this into a 400 with the message intact, so the user sees
    "no API key configured for anthropic" rather than an opaque 500.
    """


class LLMProvider(ABC):
    name: str = ""
    #: False for local providers (Ollama) — the settings UI hides the key field.
    requires_key: bool = True

    @abstractmethod
    async def complete_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int = 16000,
    ) -> T:
        """Return an instance of `schema`, or raise LLMError."""

    @abstractmethod
    async def health(self) -> tuple[bool, str]:
        """(reachable, detail) — powers the "Test connection" button in Settings."""
