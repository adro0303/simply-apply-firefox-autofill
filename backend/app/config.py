"""Process-level configuration.

These are *defaults*. Anything the user can change at runtime (LLM provider, API keys,
enabled sources) lives in the SQLite `settings` table instead, so the app never requires
an edit-and-restart cycle. See `app.services.settings_store`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SIMPLYAPPLY_",
        env_file=(".env", "../.env"),
        extra="ignore",
    )

    data_dir: Path = Path("./data")
    cache_ttl_minutes: int = 60

    # Defaults to a cloud provider with no key on purpose: that state is detectable, so
    # a fresh install prompts for setup on first load. Defaulting to `ollama` would look
    # "configured" while silently failing on the first upload for anyone without it
    # installed — a worse first run than being asked a question.
    llm_provider: str = "anthropic"

    anthropic_model: str = "claude-sonnet-5"
    openai_model: str = "gpt-4o"
    openai_base_url: str = "https://api.openai.com/v1"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "simplyapply.db"

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / "artifacts"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
