"""FastAPI entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import init_db
from app.routers import applications, apply, resumes, search, settings

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    token = init_db()
    log = logging.getLogger(__name__)
    log.info(
        "SimplyApply backend ready — data dir: %s", get_settings().data_dir.resolve()
    )
    log.info(
        "Extension auth token (paste into the extension's Options page once): %s", token
    )
    yield


app = FastAPI(
    title="SimplyApply",
    description="Self-hosted job search + truthful resume tailoring.",
    version="0.1.0",
    lifespan=lifespan,
)

# In normal use the browser only talks to the Next.js origin, which proxies /api to here,
# so CORS never comes into play. These entries exist for the case where someone runs the
# backend standalone and pokes at it directly during development, plus the Firefox/Chrome
# extension, which runs as a moz-extension://<uuid> / chrome-extension://<id> origin.
# Firefox assigns a new random UUID on most temporary-install reloads, so there's no one
# origin string to pin — a regex is required, not a shortcut.
#
# IMPORTANT: this regex is NOT the access control. CORS is enforced per-origin by the
# browser, not per-extension-identity — it authorizes every extension installed, not just
# ours. The real gate on every route an extension calls is the X-SimplyApply-Token header
# (see app/deps.py:require_extension_token); this regex only saves a *legitimate* holder
# of that token from a same-machine preflight failure.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"^(moz|chrome)-extension://.*$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search.router)
app.include_router(resumes.router)
app.include_router(apply.router)
app.include_router(applications.router)
app.include_router(settings.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "simplyapply"}
