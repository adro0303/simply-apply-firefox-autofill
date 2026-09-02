"""Shared fixtures for the HTTP-level (TestClient) tests."""

from __future__ import annotations

import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A fully isolated app instance with its own SQLite file and artifacts dir.

    Carries the real extension auth token as a default header, so every existing test
    that exercises a now-token-gated endpoint keeps working without individually passing
    it. Tests that specifically want to exercise the auth gate (test_auth.py) override or
    drop the header per-request instead.
    """
    monkeypatch.setenv("SIMPLYAPPLY_DATA_DIR", str(tmp_path / "data"))

    # The engine, the settings cache, and the artifacts path are all module-level
    # singletons bound at import time. Dropping every `app.*` module forces them to be
    # rebuilt against this test's temp data dir, so tests can't leak state into each other.
    for module in [m for m in list(sys.modules) if m == "app" or m.startswith("app.")]:
        del sys.modules[module]

    from app.db import init_db
    from app.main import app as fresh_app

    token = init_db()

    with TestClient(fresh_app) as c:
        c.headers["X-SimplyApply-Token"] = token
        yield c
