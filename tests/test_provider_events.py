from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import provider_events  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ALIEN_ENV", "production")
    monkeypatch.setenv("ALIEN_PUBLIC_READ", "1")
    monkeypatch.setenv("ALIEN_PROVIDER_EVENTS_TOKEN", "events-token")
    monkeypatch.setenv("ALIEN_PROVIDER_EVENTS_DB", str(tmp_path / "events.sqlite3"))
    app = FastAPI()
    app.include_router(provider_events.router)
    return TestClient(app)


PATH = "/api/provider-events"
AUTH = {"Authorization": "Bearer events-token"}


def event(provider="laso", source="argus", operation="card_checkout", status="succeeded"):
    return {
        "event_id": str(uuid4()), "provider": provider, "source": source,
        "operation": operation, "status": status,
    }


def test_authenticated_events_count_once_and_only_aggregates_are_public(client):
    checkout = event()
    assert client.post(PATH, json=checkout).status_code == 401
    assert client.post(PATH, json=checkout, headers=AUTH).json() == {"ok": True, "duplicate": False}
    assert client.post(PATH, json=checkout, headers=AUTH).json() == {"ok": True, "duplicate": True}
    assert client.post(PATH, json={**checkout, "status": "failed"}, headers=AUTH).status_code == 409
    assert client.post(PATH, json=event(status="attempted"), headers=AUTH).status_code == 200
    assert client.post(PATH, json=event("tavily", "metis", "search", "failed"), headers=AUTH).status_code == 200
    assert client.post(
        PATH, json=event("coinmarketcap", "argus", "quotes"),
        headers={"Authorization": "Bearer test-monitor-token"},
    ).status_code == 200
    summary = client.get(PATH)
    assert checkout["event_id"] not in summary.text
    assert "received_at" not in summary.text
    payload = summary.json()
    assert payload["window_seconds"] == 86400
    metrics = {(row["id"], op["source"], op["operation"]): (op["succeeded"], op["failed"], op["attempted"])
               for row in payload["providers"] for op in row["operations"]}
    assert metrics == {
        ("laso", "argus", "card_quote"): (0, 0, 0),
        ("laso", "argus", "card_issue"): (0, 0, 0),
        ("laso", "argus", "card_checkout"): (1, 0, 1),
        ("coinmarketcap", "argus", "quotes"): (1, 0, 0),
        ("tavily", "argus", "search"): (0, 0, 0),
        ("tavily", "metis", "search"): (0, 1, 0),
    }


def test_rejects_unknown_fields_provider_combos_and_oversized_body(client):
    bad_payloads = [
        {**event(), "email": "private@example.com"}, event(source="metis"),
        event(status="pending"), {**event(), "event_id": "wallet-secret"},
    ]
    for payload in bad_payloads:
        response = client.post(PATH, json=payload, headers=AUTH)
        assert response.status_code == 422
        assert response.json() == {"detail": "Invalid provider event"}
    assert client.post(PATH, content="x" * 513, headers={
        **AUTH, "Content-Type": "application/json",
    }).status_code == 413
    assert client.post(PATH, content="data", headers=AUTH).status_code == 415


def test_window_expiry_and_storage_disable(client, monkeypatch):
    now = 1800000000
    monkeypatch.setattr(provider_events.time, "time", lambda: now)
    assert client.post(PATH, json=event(), headers=AUTH).status_code == 200
    now += provider_events.WINDOW_S
    assert all(
        op["succeeded"] == 0
        for row in client.get(PATH).json()["providers"] for op in row["operations"]
    )
    now += provider_events.WINDOW_S + 1
    client.get(PATH)
    with sqlite3.connect(provider_events.os.environ["ALIEN_PROVIDER_EVENTS_DB"]) as conn:
        assert conn.execute("SELECT COUNT(*) FROM provider_events").fetchone() == (0,)
    monkeypatch.delenv("ALIEN_PROVIDER_EVENTS_DB")
    assert client.get(PATH).json() == {"state": "disabled"}
    assert client.post(PATH, json=event(), headers=AUTH).status_code == 503
