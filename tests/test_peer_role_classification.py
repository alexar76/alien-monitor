"""A peer's declared role survives discovery, layout and its detail-card affiliation."""

from __future__ import annotations

import asyncio
import math
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import hub_discovery  # noqa: E402
from ecosystem_layout import local_ecosystem_radius, node_position  # noqa: E402
from hub_affiliation import apply_hub_affiliation  # noqa: E402


PRIMARY = "https://operator.example"
POLL_BASE = "http://127.0.0.1:9083"


def discover_peer(monkeypatch, declaration, *, url="https://unseen.example.net"):
    """Exercise the public discovery pipeline with all outbound JSON fetches mocked."""
    fetched = []
    document = {"name": "Previously Unseen Catalogue", **declaration}
    peer_row = {"url": url, "name": document["name"],
                "capabilities_count": 0, "trust_score": 0.265}

    async def fake_get_json(client, target, **kwargs):
        fetched.append(target)
        if target == f"{POLL_BASE}/ai-market/v2/federation/peers":
            return {"peers": [peer_row], "pending": []}
        if target == f"{POLL_BASE}/.well-known/ai-market.json":
            return {"name": "Operator Catalogue", "hub_url": PRIMARY, "hub_version": "3.16.1"}
        if target == f"{url}/.well-known/ai-market.json":
            return document
        if target in {f"{url}/api/health", f"{url}/health", f"{url}/ai-market/v2/health"}:
            return {"ok": True}
        return None

    monkeypatch.setattr(hub_discovery, "_get_json", fake_get_json)
    monkeypatch.setattr(hub_discovery, "url_is_safe", lambda *args, **kwargs: True)
    monkeypatch.setenv("ALIEN_DISCOVERY_ENABLED", "1")
    monkeypatch.setenv("ALIEN_ECOSYSTEM_PROFILE", "generic")
    monkeypatch.setenv("ALIEN_PUBLIC_HUB_URL", PRIMARY)
    monkeypatch.delenv("ALIEN_DISCOVERY_CATEGORIES", raising=False)
    monkeypatch.delenv("ALIEN_KEEP_SILENT_NODES", raising=False)
    monkeypatch.setenv("ALIEN_DISCOVERY_HUB_CHILDREN", "12")
    result = asyncio.run(hub_discovery.discover_async(POLL_BASE))
    assert not result["errors"], result
    nodes = result["nodes"]
    apply_hub_affiliation(nodes, primary_hub_url=PRIMARY)
    parents = [node for node in nodes if node.get("url") == url]
    assert len(parents) == 1, result
    return parents[0], nodes, fetched


@pytest.mark.parametrize("url", ["https://unseen.example.net", "https://new.operator.example"])
@pytest.mark.parametrize("role_declaration", [{"federation": {"role": "hub"}}, {"role": "hub"}])
@pytest.mark.parametrize("protocol_declaration", [{}, {"protocol_versions": ["mcp"]},
                                                {"protocol_versions": ["v-future"]}])
def test_explicit_hub_is_a_distant_hub_without_protocol_or_existing_peers(
    monkeypatch, url, role_declaration, protocol_declaration,
):
    node, nodes, fetched = discover_peer(
        monkeypatch, {**role_declaration, **protocol_declaration, "peers": []}, url=url,
    )
    assert len(nodes) == 1
    assert (node["group"], node["role"], node["icon"], node["hop"]) == ("peer_hub", "hub", "hub", 1)
    assert node["hub"]["id"] == node["id"]
    assert node["hub"]["url"] == url
    assert node["metrics"]["capabilities"] == 0
    assert node["metrics"]["trust_score"] == 0.265
    centre = node_position("hub")
    assert math.dist([node["position"][k] for k in ("x", "y", "z")],
                     [centre[k] for k in ("x", "y", "z")]) > local_ecosystem_radius()
    assert f"{url}/api/health" in fetched
    assert f"{url}/ai-market/v2/health" not in fetched, "hub role must not invent protocol support"


@pytest.mark.parametrize("role_declaration", [
    {"federation": {"role": "provider"}},
    {"federation": {"role": "service"}},
    {"role": "provider"},
    {"role": "service"},
])
def test_explicit_service_role_beats_legacy_hub_version_and_v2(monkeypatch, role_declaration):
    node, _, fetched = discover_peer(monkeypatch, {
        **role_declaration, "hub_version": "1.0.0", "protocol_versions": ["v2"],
        "manifest_url": "https://unseen.example.net/manifest", "categories": ["oracle"],
    })
    assert node["group"] != "peer_hub"
    assert node.get("role") != "hub"
    assert node["hub"]["id"] == "hub"
    assert node["hub"]["id"] != node["id"]
    assert "https://unseen.example.net/ai-market/v2/health" not in fetched


def test_bare_v2_node_is_not_promoted_to_hub_by_its_protocol(monkeypatch):
    node, _, _ = discover_peer(monkeypatch, {
        "node_version": "aimarket-node 1.0.0", "protocol_versions": ["v2"],
        "manifest_url": "https://unseen.example.net/manifest", "categories": ["oracle"],
    })
    assert node["group"] != "peer_hub"
    assert node.get("role") != "hub"
    assert node["hub"]["id"] == "hub"


def test_legacy_v1_catalogue_keeps_its_hub_role(monkeypatch):
    node, _, fetched = discover_peer(monkeypatch, {
        "protocol_versions": ["v1", "mcp"],
        "manifest_url": "https://unseen.example.net/ai-market/manifest",
    })
    assert (node["group"], node["role"], node["icon"]) == ("peer_hub", "hub", "hub")
    assert node["hub"]["id"] == node["id"]
    assert "https://unseen.example.net/health" in fetched


def test_ordinary_discovered_service_does_not_call_itself_a_hub(monkeypatch):
    node, _, _ = discover_peer(monkeypatch, {"categories": ["oracle"]})
    assert node["group"] == "oracle"
    assert node["hub"]["id"] == "hub"
    assert node["hub"]["url"] == PRIMARY


def test_discovered_provider_card_belongs_to_its_parent_hub(monkeypatch):
    node, nodes, _ = discover_peer(monkeypatch, {
        "federation": {"role": "hub"}, "protocol_versions": ["mcp"],
        "ecosystem": {"nodes": [{
            "id": "provider-one", "name": "A Provider", "role": "provider",
            "url": "https://provider.example.net", "capabilities_count": 1,
        }]},
    })
    child = next(n for n in nodes if n.get("url") == "https://provider.example.net")
    assert child["role"] == "provider"
    assert child["parent_id"] == node["id"]
    assert child["hub"] == node["hub"]
    assert child["hub"]["id"] != child["id"]
