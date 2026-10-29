"""A renamed provider stays one searchable node instead of collapsing into its Hub."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import hub_discovery
from canonical_peers import canonical_node_id_for_peer
from oracle_family import merge_discovered_peers
from product_display import symmartys_identity_url


CURRENT = "https://modelmarket.dev/providers/symmartys"
LEGACY = "https://modelmarket.dev/providers/emporion"
ALIASES = (CURRENT, LEGACY, "https://symmartys.modelmarket.dev", "https://emporion.modelmarket.dev")


@pytest.mark.parametrize("url", ALIASES)
def test_provider_addresses_do_not_fold_onto_the_primary_hub(url):
    assert symmartys_identity_url(url) == CURRENT
    assert canonical_node_id_for_peer({"url": url, "label": "SYMMARTYS"}) is None
    assert hub_discovery._node_id({"name": "an observed old name"}, url) == "symmartys"
    assert hub_discovery._norm_url(url) == hub_discovery._norm_url(CURRENT)


def test_aliases_never_use_a_strangers_label_or_other_services_on_the_same_host():
    for url in ("https://stranger.example/symmartys", "https://modelmarket.dev/providers/symmartys-copy",
                "https://symmartys.modelmarket.dev/another-service",
                "https://modelmarket.dev:8443/providers/symmartys"):
        assert symmartys_identity_url(url) is None
    assert canonical_node_id_for_peer({"url": "https://modelmarket.dev"}) == "hub"
    assert canonical_node_id_for_peer({"url": "https://modelmarket.dev/studio"}) == "hephaestus"
    assert canonical_node_id_for_peer({"url": "https://stranger.example", "label": "SYMMARTYS"}) is None


def test_primary_provider_and_legacy_gossip_become_one_node_in_live_and_uni_discovery(monkeypatch):
    provider = {"name": "SYMMARTYS — public-record facts", "hub_version": "0.5.0",
                "categories": ["commerce", "kyb"], "capabilities_count": 16,
                "ecosystem": {"product": "symmartys"}}
    other = {"name": "Another Hub", "hub_version": "3.16.2", "peers": [
        {"url": LEGACY, "name": "EMPORION — public-record facts", "capabilities_count": 16}]}

    async def fake_get_json(client, url, **kwargs):
        if url == "https://modelmarket.dev/ai-market/v2/federation/peers":
            return {"peers": [{"url": CURRENT, "capabilities_count": 16},
                              {"url": LEGACY, "capabilities_count": 16},
                              {"url": "https://other.example"}], "pending": []}
        if url.endswith("/.well-known/ai-market.json"):
            if url.startswith(CURRENT) or url.startswith(LEGACY):
                return provider
            if url.startswith("https://other.example"):
                return other
            return {"name": "Primary Hub", "hub_version": "3.16.2"}
        if url.endswith("/health"):
            return {"status": "ok"}
        return {}

    monkeypatch.setattr(hub_discovery, "_get_json", fake_get_json)
    monkeypatch.setattr(hub_discovery, "url_is_safe", lambda *args, **kwargs: True)
    for allow_private in (False, True):  # LIVE and UNI share this discovery path.
        discovered = asyncio.run(hub_discovery.discover_async(
            "https://modelmarket.dev", allow_private=allow_private))
        service_nodes = [node for node in discovered["nodes"] if node["id"] == "symmartys"]
        assert len(service_nodes) == 1
        assert service_nodes[0]["label"].startswith("SYMMARTYS")
        assert service_nodes[0]["metrics"]["capabilities"] == 16
        assert not any(node["id"].startswith("fedchild:") and "emporion" in node["id"]
                       for node in discovered["nodes"])
        assert any(link.get("kind") == "shared" and link["target"] == "symmartys"
                   for link in discovered["links"])
        nodes = [{"id": "hub", "label": "Primary Hub"}, {"id": "federation", "label": "Federation"}]
        merge_discovered_peers(nodes, [], discovered)
        assert len([node for node in nodes if node["id"] == "symmartys"]) == 1


def test_uni_replaces_a_stale_discovered_emporion_entity_with_symmartys(monkeypatch):
    from universe_discovery import DiscoveryMixin
    from universe_entities import EcosystemEntity

    class Universe(DiscoveryMixin):
        def __init__(self):
            self.entities = {
                "hub": EcosystemEntity("hub", "UNI Hub", "core"),
                "federation": EcosystemEntity("federation", "Federation", "core"),
                "emporion": EcosystemEntity("emporion", "EMPORION", "federation"),
            }
            self._discovered_ids = {"emporion"}

    monkeypatch.setattr(hub_discovery, "discover_cached_sync", lambda *args, **kwargs: {
        "nodes": [{"id": "symmartys", "label": "SYMMARTYS", "url": CURRENT,
                   "group": "oracle", "status": "active", "metrics": {"capabilities": 16}}],
        "links": [], "events": [],
    })
    universe = Universe()
    universe._apply_discovery("https://uni.example")
    assert "emporion" not in universe.entities
    assert universe.entities["symmartys"].to_node()["label"] == "SYMMARTYS"
    assert universe.entities["symmartys"].metrics["capabilities"] == 16
