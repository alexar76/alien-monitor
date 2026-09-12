"""Factory-born agents appear on the map as economy participants."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import factory_agents  # noqa: E402
from ecosystem_layout import NODE_POSITIONS, ring_position  # noqa: E402
from oracle_family import ORACLE_FAMILY  # noqa: E402


@pytest.fixture(autouse=True)
def _no_cache():
    if hasattr(factory_agents.fetch_agents_sync, "cache_clear"):
        factory_agents.fetch_agents_sync.cache_clear()
    yield


def _dist(a, b):
    return math.sqrt((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2 + (a["z"] - b["z"]) ** 2)


def _node():
    return dict(factory_agents.factory_agents_node_spec())


REGISTRY = {
    "agents": [
        {
            "agent_id": "sentinel-1",
            "name": "Sentinel",
            "product_id": "prod-bdb1634806de",
            "sdk": "aimarket-agent@2.2.0",
            "public_url": "https://sentinel.vercel.app",
            "status": "live",
            "verified": True,
            "age_sec": 12,
            "capabilities_used": ["atlas.situation.brief@v1"],
            "stats": {"invokes_total": 40, "spend_usd_total": 2.4, "errors_24h": 1},
        },
        {
            "agent_id": "old-1",
            "name": "Retired",
            "sdk": "@aimarket/agent@0.1.4",
            "status": "offline",
            "age_sec": 90000,
            "stats": {"invokes_total": 5, "spend_usd_total": 0.1},
        },
    ],
    "summary": {
        "agents_total": 2,
        "invokes_total": 45,
        "spend_usd_total": 2.5,
        "sdks": {"aimarket-agent@2.2.0": 1, "@aimarket/agent@0.1.4": 1},
        "capabilities": {"atlas.situation.brief@v1": 1},
    },
}


def test_node_slot_is_clear_of_every_other_node_and_the_oracle_ring():
    pos = NODE_POSITIONS["factory_agents"]
    for nid, other in NODE_POSITIONS.items():
        if nid == "factory_agents":
            continue
        assert _dist(pos, other) >= 4.5, f"too close to {nid}"
    total = len(ORACLE_FAMILY)
    for i in range(total):
        assert _dist(pos, ring_position(i, total)) >= 4.5, f"too close to oracle[{i}]"


def test_node_group_is_not_argus():
    """App.tsx routes every argus-group node to the ARGUS run panel — this roster
    must reach NodeDetail so its own card renders."""
    assert factory_agents.factory_agents_node_spec()["group"] == "agent"


def test_topology_links_connect_factory_hub_and_atlas():
    edges = {(e["source"], e["target"]) for e in factory_agents.factory_agents_topology_links()}
    assert ("factory", "factory_agents") in edges
    assert ("factory_agents", "hub") in edges
    assert ("factory_agents", "atlas") in edges


def test_roster_fills_the_ball(monkeypatch):
    monkeypatch.setattr(factory_agents, "fetch_agents_sync", lambda **kw: REGISTRY)
    nodes = [_node()]
    factory_agents.apply_factory_agents_graph(nodes)
    node = nodes[0]

    assert node["label"] == "Agents"
    assert node["status"] == "active"
    assert node["metrics"]["agents_live"] == 1
    assert node["metrics"]["spend_usd_total"] == 2.5

    rows = node["factory_agents_live"]["agents"]
    assert [r["agent_id"] for r in rows] == ["sentinel-1", "old-1"]
    assert rows[0]["sdk"] == "aimarket-agent@2.2.0"
    assert rows[0]["invokes_total"] == 40
    assert rows[0]["capabilities_used"] == ["atlas.situation.brief@v1"]


def test_unreachable_registry_is_reported_not_faked(monkeypatch):
    """A monitor that invents participants is worse than one that says nothing."""
    monkeypatch.setattr(factory_agents, "fetch_agents_sync", lambda **kw: None)
    nodes = [_node()]
    factory_agents.apply_factory_agents_graph(nodes)
    live = nodes[0]["factory_agents_live"]
    assert live["stale"] is True
    assert live["agents"] == []
    assert nodes[0]["label"] == "Agents"
    assert nodes[0]["status"] == "idle"


def test_no_agents_yet_is_idle_not_active(monkeypatch):
    monkeypatch.setattr(
        factory_agents, "fetch_agents_sync", lambda **kw: {"agents": [], "summary": {}}
    )
    nodes = [_node()]
    factory_agents.apply_factory_agents_graph(nodes)
    assert nodes[0]["status"] == "idle"
    assert nodes[0]["label"] == "Agents"
