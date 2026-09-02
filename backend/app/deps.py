"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import settings_store


def require_extension_token(
    x_simplyapply_token: str | None = Header(default=None, alias="X-SimplyApply-Token"),
    db: Session = Depends(get_db),
) -> None:
    """Gate for every endpoint an installed browser extension can call.

    `main.py`'s CORS `allow_origin_regex` authorizes any `moz-/chrome-extension://`
    origin — CORS is enforced per-origin by the browser, not per-extension-identity, so
    it can't distinguish "our" extension from any other one installed. This shared-secret
    header is the actual access control; the CORS regex is just a browser-side nicety
    layered on top of it.
    """
    expected = settings_store.extension_token(db)
    if not x_simplyapply_token or x_simplyapply_token != expected:
        raise HTTPException(401, "Missing or invalid X-SimplyApply-Token header.")
