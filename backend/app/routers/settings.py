"""Settings: LLM provider + key, enabled sources, Greenhouse company list.

API keys are write-only over HTTP. They can be set, and the API reports whether one
exists, but the value is never returned — a local-only app still shouldn't hand a key
back out over an endpoint any page on localhost can call.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_settings
from app.connectors.registry import available_sources
from app.db import get_db
from app.llm.base import LLMError
from app.llm.registry import PROVIDERS, build_provider
from app.schemas import SettingsIn, SettingsOut
from app.services import settings_store

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _current(db: Session) -> SettingsOut:
    provider = settings_store.provider(db)
    return SettingsOut(
        llm_provider=provider,
        model=settings_store.model_for(db, provider),
        has_key=bool(settings_store.api_key(db, provider)),
        ollama_host=settings_store.ollama_host(db),
        openai_base_url=settings_store.openai_base_url(db),
        enabled_sources=settings_store.get_list(
            db, settings_store.KEY_ENABLED_SOURCES, available_sources()
        ),
        available_sources=available_sources(),
        cache_ttl_minutes=get_settings().cache_ttl_minutes,
    )


@router.get("", response_model=SettingsOut)
def read_settings(db: Session = Depends(get_db)) -> SettingsOut:
    return _current(db)


@router.put("", response_model=SettingsOut)
def write_settings(payload: SettingsIn, db: Session = Depends(get_db)) -> SettingsOut:
    if payload.llm_provider is not None:
        if payload.llm_provider not in PROVIDERS:
            raise HTTPException(400, f"Provider must be one of: {', '.join(PROVIDERS)}")
        settings_store.set_value(db, settings_store.KEY_PROVIDER, payload.llm_provider)
        # The model is provider-specific; clear it so the new provider's default applies
        # unless the same request also sets one explicitly.
        if payload.model is None:
            settings_store.set_value(db, settings_store.KEY_MODEL, "")

    if payload.model is not None:
        settings_store.set_value(db, settings_store.KEY_MODEL, payload.model.strip())

    if payload.api_key is not None:
        # Empty string is a meaningful value here: it clears the stored key.
        settings_store.set_value(db, settings_store.KEY_API_KEY, payload.api_key.strip())

    if payload.ollama_host is not None:
        settings_store.set_value(
            db, settings_store.KEY_OLLAMA_HOST, payload.ollama_host.strip()
        )

    if payload.openai_base_url is not None:
        settings_store.set_value(
            db, settings_store.KEY_OPENAI_BASE_URL, payload.openai_base_url.strip()
        )

    if payload.enabled_sources is not None:
        known = set(available_sources())
        unknown = [s for s in payload.enabled_sources if s not in known]
        if unknown:
            raise HTTPException(400, f"Unknown source(s): {', '.join(unknown)}")
        settings_store.set_list(
            db, settings_store.KEY_ENABLED_SOURCES, payload.enabled_sources
        )

    if payload.greenhouse_companies is not None:
        cleaned = [c.strip().lower() for c in payload.greenhouse_companies if c.strip()]
        settings_store.set_list(db, settings_store.KEY_GREENHOUSE_COMPANIES, cleaned)

    return _current(db)


@router.get("/greenhouse-companies", response_model=list[str])
def greenhouse_companies(db: Session = Depends(get_db)) -> list[str]:
    return settings_store.greenhouse_companies(db)


@router.post("/test-llm")
async def test_llm(db: Session = Depends(get_db)) -> dict[str, object]:
    """Ping the configured provider so the user finds out here, not mid-apply."""
    try:
        provider = build_provider(db)
    except LLMError as exc:
        return {"ok": False, "detail": str(exc)}

    ok, detail = await provider.health()
    return {"ok": ok, "detail": detail, "provider": provider.name}


@router.get("/capabilities")
def capabilities() -> dict[str, object]:
    """What this install can actually do, so the UI never promises a missing feature."""
    # PDF is a pure-Python (reportlab) render with no system dependency, so it is always
    # available. The field is kept so the frontend contract doesn't change.
    return {
        "pdf": True,
        "pdf_detail": "PDF rendering available — every resume renders to a single-page PDF.",
    }
