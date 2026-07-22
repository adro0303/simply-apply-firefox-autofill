"""Builds the configured LLM provider from runtime settings."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.llm.base import LLMError, LLMProvider
from app.services import settings_store

PROVIDERS = ("anthropic", "openai", "ollama")


def build_provider(db: Session) -> LLMProvider:
    """Instantiate the selected provider. Raises LLMError if it can't be configured."""
    name = settings_store.provider(db)
    model = settings_store.model_for(db, name)

    if name == "anthropic":
        from app.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key=settings_store.api_key(db, name), model=model)

    if name == "openai":
        from app.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(
            api_key=settings_store.api_key(db, name),
            model=model,
            base_url=settings_store.openai_base_url(db),
        )

    if name == "ollama":
        from app.llm.ollama_provider import OllamaProvider

        return OllamaProvider(host=settings_store.ollama_host(db), model=model)

    raise LLMError(f"Unknown LLM provider {name!r}. Choose one of: {', '.join(PROVIDERS)}")
