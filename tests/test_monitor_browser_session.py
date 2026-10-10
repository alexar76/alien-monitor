"""The monitor root token never needs to enter a compiled browser bundle."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from main import app  # noqa: E402
from monitor_auth import (  # noqa: E402
    MONITOR_SESSION_COOKIE,
    create_monitor_session,
    monitor_session_valid,
)


def test_signed_session_round_trip_and_tamper_rejection() -> None:
    token = create_monitor_session()
    assert monitor_session_valid(token)
    assert not monitor_session_valid(token[:-1] + ("0" if token[-1] != "0" else "1"))


def test_browser_exchanges_root_token_for_httponly_session() -> None:
    client = TestClient(app)

    response = client.post("/api/auth/session", json={"token": "test-monitor-token"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert "test-monitor-token" not in response.text
    cookie_header = response.headers["set-cookie"]
    assert MONITOR_SESSION_COOKIE in cookie_header
    assert "HttpOnly" in cookie_header
    assert "SameSite=strict" in cookie_header
    assert client.get("/api/universe/status").status_code == 200


def test_invalid_root_token_does_not_create_session() -> None:
    client = TestClient(app)
    response = client.post("/api/auth/session", json={"token": "wrong"})
    assert response.status_code == 401
    assert MONITOR_SESSION_COOKIE not in response.headers.get("set-cookie", "")


def test_cookie_authenticated_mutation_requires_csrf_and_origin() -> None:
    client = TestClient(app)
    assert client.post("/api/auth/session", json={"token": "test-monitor-token"}).status_code == 200

    missing = client.post("/api/universe/stop")
    assert missing.status_code == 403

    allowed = client.post(
        "/api/universe/stop",
        headers={"Origin": "http://testserver", "X-Alien-CSRF": "1"},
    )
    assert allowed.status_code == 200
