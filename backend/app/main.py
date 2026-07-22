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
    init_db()
    logging.getLogger(__name__).info(
        "SimplyApply backend ready — data dir: %s", get_settings().data_dir.resolve()
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
# backend standalone and pokes at it directly during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
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
