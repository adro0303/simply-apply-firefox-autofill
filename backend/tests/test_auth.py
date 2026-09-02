"""X-SimplyApply-Token gate on extension-facing endpoints.

The CORS regex in app/main.py authorizes any moz-/chrome-extension:// origin — it can't
tell "our" extension apart from any other one installed, since CORS is enforced
per-origin by the browser, not per-extension-identity. This token is the actual access
control (see app/deps.py). `/api/resumes/base` stands in here for "a protected route";
the same dependency gates by-url, jobs/adhoc, apply/{job_id} (both variants), and
download.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_missing_token_is_rejected(client) -> None:
    with TestClient(client.app) as bare:  # no default headers — nothing sent
        res = bare.get("/api/resumes/base")
    assert res.status_code == 401


def test_wrong_token_is_rejected(client) -> None:
    res = client.get("/api/resumes/base", headers={"X-SimplyApply-Token": "not-the-token"})
    assert res.status_code == 401


def test_correct_token_is_accepted(client) -> None:
    res = client.get("/api/resumes/base")  # `client` fixture carries the real token
    assert res.status_code == 200


def test_health_needs_no_token(client) -> None:
    with TestClient(client.app) as bare:
        res = bare.get("/api/health")
    assert res.status_code == 200
