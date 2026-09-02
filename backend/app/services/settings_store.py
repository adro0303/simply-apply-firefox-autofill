"""Runtime settings, backed by the SQLite `settings` table.

Precedence: DB value -> environment default. That ordering lets the UI override .env
without a restart, while still letting a user pre-seed config via environment variables
in a Compose deployment.

API keys are write-only over the HTTP API: they can be set, and the API reports whether
one exists, but the value itself is never returned or logged.
"""

from __future__ import annotations

import json
import os
import secrets

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Setting

KEY_PROVIDER = "llm_provider"
KEY_MODEL = "llm_model"
KEY_API_KEY = "llm_api_key"
KEY_OLLAMA_HOST = "ollama_host"
KEY_OPENAI_BASE_URL = "openai_base_url"
KEY_ENABLED_SOURCES = "enabled_sources"
KEY_GREENHOUSE_COMPANIES = "greenhouse_companies"
KEY_EXTENSION_TOKEN = "extension_token"

# Sensible starter set of Greenhouse boards. Greenhouse has no global search endpoint —
# it is per-company by design — so a company list is required input, not a limitation
# we invented. Users extend this in Settings.
DEFAULT_GREENHOUSE_COMPANIES = [
    "stripe",
    "databricks",
    "anthropic",
    "figma",
    "ramp",
    "airtable",
    "discord",
    "robinhood",
    "coinbase",
    "doordash",
    "gitlab",
    "asana",
]


def get(db: Session, key: str, default: str = "") -> str:
    row = db.get(Setting, key)
    if row is not None and row.value != "":
        return row.value
    return default


def set_value(db: Session, key: str, value: str) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value
    db.commit()


def get_list(db: Session, key: str, default: list[str] | None = None) -> list[str]:
    raw = get(db, key, "")
    if not raw:
        return list(default or [])
    try:
        parsed = json.loads(raw)
        return [str(x) for x in parsed] if isinstance(parsed, list) else list(default or [])
    except json.JSONDecodeError:
        return list(default or [])


def set_list(db: Session, key: str, values: list[str]) -> None:
    set_value(db, key, json.dumps(values))


def provider(db: Session) -> str:
    return get(db, KEY_PROVIDER, get_settings().llm_provider)


def model_for(db: Session, prov: str) -> str:
    explicit = get(db, KEY_MODEL, "")
    if explicit:
        return explicit
    s = get_settings()
    return {
        "anthropic": s.anthropic_model,
        "openai": s.openai_model,
        "ollama": s.ollama_model,
    }.get(prov, s.ollama_model)


def api_key(db: Session, prov: str) -> str:
    stored = get(db, KEY_API_KEY, "")
    if stored:
        return stored
    env_name = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}.get(prov)
    return os.environ.get(env_name, "") if env_name else ""


def ollama_host(db: Session) -> str:
    return get(db, KEY_OLLAMA_HOST, get_settings().ollama_host)


def openai_base_url(db: Session) -> str:
    return get(db, KEY_OPENAI_BASE_URL, get_settings().openai_base_url)


def greenhouse_companies(db: Session) -> list[str]:
    return get_list(db, KEY_GREENHOUSE_COMPANIES, DEFAULT_GREENHOUSE_COMPANIES)


def extension_token(db: Session) -> str:
    """The shared secret that gates every endpoint a browser extension calls.

    CORS's `allow_origin_regex` authorizes any `moz-/chrome-extension://` origin, not
    just ours — it can't do better, since CORS is enforced per-origin by the browser, not
    per-extension-identity. This token is the actual access control.

    Generated once (env value if pinned, otherwise random) and persisted, so it survives
    restarts and is stable across the whole DB's lifetime.
    """
    token = get(db, KEY_EXTENSION_TOKEN, get_settings().extension_token)
    if not token:
        token = secrets.token_urlsafe(32)
        set_value(db, KEY_EXTENSION_TOKEN, token)
    return token
