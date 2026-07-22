"""Ollama adapter — fully local, no key, nothing leaves the machine.

Ollama's `/api/chat` accepts a JSON Schema in the `format` field and constrains decoding
to it, which is the same guarantee the cloud providers give. We pass the Pydantic model's
generated schema straight through, then validate the response ourselves — small local
models honor the schema shape but occasionally drift on optional fields, so the
`model_validate_json` call is a real check rather than a formality.

httpx here rather than an SDK: Ollama's API is two endpoints, and adding a dependency for
that isn't worth it.
"""

from __future__ import annotations

from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.llm.base import LLMError, LLMProvider

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "qwen2.5:7b"
# Local models are slow — a 7B model tailoring against a long JD can take minutes on CPU.
TIMEOUT = httpx.Timeout(600.0, connect=10.0)


class OllamaProvider(LLMProvider):
    name = "ollama"
    requires_key = False

    def __init__(
        self, host: str = "http://localhost:11434", model: str = DEFAULT_MODEL
    ) -> None:
        self.host = (host or "http://localhost:11434").rstrip("/")
        self.model = model or DEFAULT_MODEL

    async def complete_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int = 16000,
    ) -> T:
        payload = {
            "model": self.model,
            "stream": False,
            "format": schema.model_json_schema(),
            "options": {"num_predict": max_tokens},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.post(f"{self.host}/api/chat", json=payload)
                resp.raise_for_status()
                body = resp.json()
        except httpx.ConnectError as exc:
            raise LLMError(
                f"Cannot reach Ollama at {self.host}. Is it running? (`ollama serve`)"
            ) from exc
        except Exception as exc:
            raise LLMError(f"Ollama request failed: {exc}") from exc

        content = (body.get("message") or {}).get("content", "")
        if not content:
            raise LLMError("Ollama returned an empty response.")

        try:
            return schema.model_validate_json(content)
        except ValidationError as exc:
            raise LLMError(
                f"Ollama returned output that did not match the expected schema. "
                f"A larger model usually fixes this. Details: {exc}"
            ) from exc

    async def health(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                resp = await client.get(f"{self.host}/api/tags")
                resp.raise_for_status()
                tags = resp.json()
        except Exception as exc:
            return False, f"Cannot reach Ollama at {self.host}: {exc}"

        installed = [m.get("name", "") for m in tags.get("models", [])]
        if self.model not in installed:
            return False, (
                f"Ollama is running but `{self.model}` is not installed. "
                f"Run: ollama pull {self.model}"
            )
        return True, f"Reachable — {self.model}"
