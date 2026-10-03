"""Unapproved hubs appear on the LIVE map — and only there, and only as strangers.

The monitor is the navigator of the real universe, so a hub that turned up on its own
has to be visible. What it must not do is look like a member of the federation, or get
this process to make a single outbound request to a host nobody vouched for.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from hub_discovery import DiscoveryConfig, _build_pending_node, fetch_neighborhood_async  # noqa: E402

# A public IP LITERAL, not a `.example` hostname. These tests used to pass
# `allow_private=True`, which made url_is_safe return True without resolving anything — so a
# name that resolves nowhere was fine. A peer-supplied URL now gets the narrower "loopback"
# allowance (resolve; permit only loopback), because the unconditional bypass was leaking
# from the trusted hub onto every stranger's URL. In production a pending hub's URL does
# resolve: the Hub DNS-validates it at announce time before the row exists at all.
PENDING = {
    "url": "https://93.184.216.34",
    "name": "Stranger Hub",
    "first_seen": "2026-08-28T09:00:00Z",
    "discoverer": "inbound-crawl",
    "preview_capabilities": 4,
    "categories": ["translation", "vision"],
    "trusted": False,
    "status": "pending",
}


def _cfg() -> DiscoveryConfig:
    return DiscoveryConfig(allow_private=True)


def test_pending_hub_becomes_its_own_kind_of_node():
    node = _build_pending_node(PENDING, _cfg())
    assert node is not None
    assert node["group"] == "pending_hub", "must not share a group with approved peers"
    assert node["status"] == "pending"
    assert node["trusted"] is False
    assert node["id"].startswith("pending:"), "id namespace keeps it out of peer lookups"
    assert node["metrics"]["preview_capabilities"] == 4
    assert node["detail"]["discoverer"] == "inbound-crawl"
    assert "until it passes" in node["detail"]["note"]


def test_building_a_pending_node_makes_no_outbound_request(monkeypatch):
    """An unapproved stranger must not be able to make this monitor call it.

    The approved-peer builder fetches the peer's well-known and /api/health. Doing
    that for a hub nobody vouched for would turn 'announce yourself' into 'get the
    operator's monitor to connect to me'.
    """
    import hub_discovery

    async def _boom(*a, **kw):  # pragma: no cover - must never run
        raise AssertionError("pending node builder performed a network fetch")

    monkeypatch.setattr(hub_discovery, "_get_json", _boom)
    assert _build_pending_node(PENDING, _cfg()) is not None


def test_unsafe_pending_url_is_dropped():
    for hostile in ("http://127.0.0.1:9083", "http://169.254.169.254", "", "not-a-url"):
        cfg = DiscoveryConfig(allow_private=False)
        assert _build_pending_node({**PENDING, "url": hostile}, cfg) is None


def test_pending_node_carries_a_position():
    """The frontend dereferences node.position.{x,y,z} with no guard.

    A node without one does not render badly — it throws and takes the ecosystem graph
    with it. This is the cheapest possible test for the most total failure available.
    """
    node = _build_pending_node(PENDING, _cfg())
    assert set(node["position"]) == {"x", "y", "z"}
    assert all(isinstance(v, (int, float)) for v in node["position"].values())


def test_lazy_neighborhood_is_bounded_paginated_and_deduplicated(monkeypatch):
    import asyncio
    import hub_discovery

    async def fake_get(*args, **kwargs):
        return {
            "peers": [
                {"url": "https://a.example", "name": "A", "trusted": True},
                {"url": "https://same.example", "name": "Approved"},
            ],
            "pending": [
                {"url": "https://same.example", "name": "Duplicate"},
                {"url": "https://z.example", "name": "Z"},
            ],
        }

    monkeypatch.setattr(hub_discovery, "_get_json", fake_get)
    monkeypatch.setattr(hub_discovery, "url_is_safe", lambda *args, **kwargs: True)
    first = asyncio.run(fetch_neighborhood_async("https://hub.example", limit=2))
    assert [n["url"] for n in first["neighbors"]] == ["https://a.example", "https://same.example"]
    assert first["count"] == 3
    assert first["next_cursor"] == 2
    second = asyncio.run(fetch_neighborhood_async("https://hub.example", limit=2, cursor=2))
    assert [n["url"] for n in second["neighbors"]] == ["https://z.example"]
    assert second["next_cursor"] is None


def test_pending_copy_of_an_existing_url_is_metadata_not_a_second_planet(monkeypatch):
    import asyncio
    import hub_discovery

    async def fake_get(client, url, **kwargs):
        if url.endswith("/federation/peers"):
            return {
                "peers": [{"url": "https://peer.example", "name": "Peer"}],
                "pending": [{"url": "https://peer.example/", "name": "Peer again"}],
            }
        if "127.0.0.1" in url and "well-known" in url:
            return {"hub_url": "https://ours.example", "name": "Ours"}
        if "peer.example" in url and "well-known" in url:
            return {
                "name": "Peer", "hub_version": "3.2.1", "peers": [],
                "categories": ["oracle"],
            }
        if "peer.example" in url and url.endswith("/api/health"):
            return {"status": "ok"}
        return None

    monkeypatch.setattr(hub_discovery, "_get_json", fake_get)
    monkeypatch.setattr(hub_discovery, "url_is_safe", lambda *a, **k: True)
    result = asyncio.run(hub_discovery.discover_async("http://127.0.0.1:9083"))

    matching = [n for n in result["nodes"] if hub_discovery._norm_url(n.get("url")) == "peer.example"]
    assert len(matching) == 1
    assert not any(n.get("group") == "pending_hub" for n in matching)
    assert result["pending_count"] == 1, "the Hub observation must not be discarded"
    assert result["pending_observations"][0]["matched_node_id"] == matching[0]["id"]


def test_uni_drops_pending_nodes_from_the_simulation():
    """UNI is the sealed universe — and it DOES call federation discovery.

    An earlier version of this test only grepped backend/main.py for
    `discover_cached_async` and concluded UNI never reaches discovery. It does, through
    `discover_cached_sync` in universe.py, and without a filter every announced stranger
    arrived in the simulation styled as a trusted oracle peer (any unmatched node is given
    group="oracle"). The test now reads the code that actually runs.
    """
    universe_src = (Path(__file__).resolve().parent.parent / "backend" / "universe.py").read_text(
        encoding="utf-8"
    )
    assert "discover_cached_sync" in universe_src, (
        "UNI's discovery call moved — re-derive what this test guards before editing it"
    )

    body = universe_src.split("def _apply_discovery", 1)[1].split("\n    def ", 1)[0]
    assert 'n.get("group") == "pending_hub"' in body and "continue" in body, (
        "UNI no longer filters pending peers — unapproved strangers will render inside the "
        "simulation, styled as trusted oracle peers"
    )


def test_live_and_uni_disagree_about_pending_on_purpose():
    """LIVE shows strangers because it is the real universe; UNI hides them because it is not.

    Pinning both halves so a future change cannot quietly make them agree in the wrong
    direction — the dangerous one being UNI starting to show them.
    """
    node = _build_pending_node(PENDING, _cfg())
    assert node["group"] == "pending_hub"          # LIVE renders it, tagged
    universe_src = (Path(__file__).resolve().parent.parent / "backend" / "universe.py").read_text(
        encoding="utf-8"
    )
    assert "pending_hub" in universe_src           # UNI knows to drop it
