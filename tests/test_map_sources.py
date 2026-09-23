"""A fresh deployment should be able to find the map, not be told where it is.

A hub on a new server has an empty federation of its own, and the only address the monitor
knew to ask was `HUB_URL` — itself. So it drew an empty universe until somebody
hand-configured it, which is the configuration this whole line of work removes.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import hub_discovery  # noqa: E402
from map_sources import DEFAULT_MAP_SOURCES, map_sources  # noqa: E402


def test_a_deployment_with_no_hub_of_its_own_still_knows_where_to_ask(monkeypatch):
    monkeypatch.delenv("ALIEN_MAP_SOURCES", raising=False)
    assert map_sources() == list(DEFAULT_MAP_SOURCES)


def test_its_own_hub_is_asked_first(monkeypatch):
    """A hub with a federation draws its own, and only borrows a view when it cannot."""
    monkeypatch.delenv("ALIEN_MAP_SOURCES", raising=False)
    ordered = map_sources("http://127.0.0.1:9083")
    assert ordered[0] == "http://127.0.0.1:9083"
    assert DEFAULT_MAP_SOURCES[0] in ordered


def test_the_operator_can_replace_the_fallbacks(monkeypatch):
    monkeypatch.setenv("ALIEN_MAP_SOURCES", "https://a.example, https://b.example/")
    assert map_sources("http://own") == ["http://own", "https://a.example", "https://b.example"]


def test_nothing_is_asked_twice(monkeypatch):
    monkeypatch.setenv("ALIEN_MAP_SOURCES", "https://a.example,https://a.example")
    assert map_sources("https://a.example") == ["https://a.example"]


def _fake_discovery(answers: dict[str, dict]):
    async def _discover(url, *, allow_private=False):
        return answers.get(url.rstrip("/"), {"nodes": [], "links": [], "events": [],
                                             "peer_count": 0, "pending_count": 0,
                                             "errors": ["unreachable"]})
    return _discover


def test_the_first_source_that_answers_wins(monkeypatch):
    monkeypatch.setenv("ALIEN_MAP_SOURCES", "https://down.example,https://up.example")
    monkeypatch.setattr(hub_discovery, "discover_async", _fake_discovery({
        "https://up.example": {"nodes": [{"id": "peer"}], "links": [], "events": [],
                               "peer_count": 1, "pending_count": 0, "errors": []},
    }))
    out = asyncio.run(hub_discovery.discover_from_sources("https://own.example"))
    assert [n["id"] for n in out["nodes"]] == ["peer"]
    assert out.get("map_source") == "https://up.example", (
        "a borrowed map should say whose it is"
    )


def test_a_hub_with_its_own_federation_does_not_borrow(monkeypatch):
    monkeypatch.setenv("ALIEN_MAP_SOURCES", "https://elsewhere.example")
    monkeypatch.setattr(hub_discovery, "discover_async", _fake_discovery({
        "https://own.example": {"nodes": [{"id": "mine"}], "links": [], "events": [],
                                "peer_count": 1, "pending_count": 0, "errors": []},
        "https://elsewhere.example": {"nodes": [{"id": "theirs"}], "links": [], "events": [],
                                      "peer_count": 9, "pending_count": 0, "errors": []},
    }))
    out = asyncio.run(hub_discovery.discover_from_sources("https://own.example"))
    assert [n["id"] for n in out["nodes"]] == ["mine"]
    assert "map_source" not in out


def test_every_source_being_down_is_reported_not_swallowed(monkeypatch):
    monkeypatch.setenv("ALIEN_MAP_SOURCES", "https://a.example,https://b.example")
    monkeypatch.setattr(hub_discovery, "discover_async", _fake_discovery({}))
    out = asyncio.run(hub_discovery.discover_from_sources("https://own.example"))
    assert out["nodes"] == []
    assert len(out["errors"]) == 3, out["errors"]
    assert all("unreachable" in e for e in out["errors"])
