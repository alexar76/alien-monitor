"""The public map must show the same graph the authenticated one does.

`/api/state` is authenticated; an anonymous browser falls back to `/api/topology`, and
that route rebuilt the graph from `build_topology()` — the seeded shelf — then merged back
a hand-written pair of groups from the live snapshot: {"cluster", "factory_product"}. That
list was written before federation discovery existed, so everything discovery produces was
dropped from the one payload the public actually renders.

Measured on monitor.modelmarket.dev, 2026-09-16: 73 nodes in /api/state, 61 in
/api/topology. The twelve missing were both federated hubs — Attested Memory and
Independent AI — every provider hanging off them, and CHARON. Present on the authenticated
map, absent from every anonymous screen, with nothing in any log to say so.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


DISCOVERED = [
    {"id": "attested-memory-hub", "group": "peer_hub", "label": "Attested Memory Hub",
     "url": "https://hub.attestedmemory.net", "status": "active", "metrics": {},
     "hub_env_snippet": "SECRET=should-not-be-served"},
    {"id": "provider:attested-memory-hub:truth-layer", "group": "peer_hub_provider",
     "label": "Truth Layer", "url": "https://truth.attestedmemory.net", "metrics": {}},
    {"id": "independent-ai-hub", "group": "peer_hub", "label": "Independent AI Hub",
     "url": "https://independentai.network/hub", "status": "active", "metrics": {}},
]


@pytest.fixture()
def snapshot_with_federation(monkeypatch):
    """A real snapshot that carries discovered peers, as the live one does."""
    seeded, seeded_links = main.build_topology()
    base = {n["id"]: n for n in seeded}

    # The real snapshot enriches seeded nodes with their live card payloads.
    base["momus"] = {**base["momus"], "status": "active", "metrics": {"findings": 20},
                     "momus_live": {"service": "momus", "prod": True},
                     "hub_env_snippet": "SECRET=should-not-be-served"}

    async def _fake_real_metrics():
        return {
            "nodes": list(base.values()) + DISCOVERED,
            "links": [
                {"source": "hub", "target": "attested-memory-hub", "label": "federates"},
                {"source": "attested-memory-hub",
                 "target": "provider:attested-memory-hub:truth-layer", "label": "provides"},
                {"source": "hub", "target": "independent-ai-hub", "label": "federates"},
                # A link to something nobody has on the map must not drag in a dangling id.
                {"source": "hub", "target": "ghost-node-nobody-has", "label": "federates"},
            ],
        }

    monkeypatch.setattr(main, "fetch_real_metrics", _fake_real_metrics)
    return TestClient(main.app)


def test_discovered_hubs_reach_the_public_map(snapshot_with_federation):
    body = snapshot_with_federation.get("/api/topology?mode=real").json()
    ids = {n["id"] for n in body["nodes"]}
    assert "attested-memory-hub" in ids
    assert "independent-ai-hub" in ids
    assert "provider:attested-memory-hub:truth-layer" in ids


def test_the_seeded_shelf_is_still_there(snapshot_with_federation):
    """Carrying the extras must not cost the nodes the route already served."""
    body = snapshot_with_federation.get("/api/topology?mode=real").json()
    ids = {n["id"] for n in body["nodes"]}
    for required in ("hub", "factory", "mesh", "momus"):
        assert required in ids


def test_a_carried_node_does_not_bring_its_secrets(snapshot_with_federation):
    """This route is read-public; `hub_env_snippet` is what the public WS tier strips."""
    body = snapshot_with_federation.get("/api/topology?mode=real").json()
    carried = next(n for n in body["nodes"] if n["id"] == "attested-memory-hub")
    assert "hub_env_snippet" not in carried


def test_links_to_nodes_nobody_has_are_dropped(snapshot_with_federation):
    """A dangling endpoint draws a line to nowhere, which the layout then tries to place."""
    body = snapshot_with_federation.get("/api/topology?mode=real").json()
    ids = {n["id"] for n in body["nodes"]}
    for link in body["links"]:
        assert str(link.get("source")) in ids
        assert str(link.get("target")) in ids


def test_the_federation_links_survive(snapshot_with_federation):
    body = snapshot_with_federation.get("/api/topology?mode=real").json()
    pairs = {(str(l.get("source")), str(l.get("target"))) for l in body["links"]}
    assert ("hub", "attested-memory-hub") in pairs
    assert ("attested-memory-hub", "provider:attested-memory-hub:truth-layer") in pairs



def test_a_seeded_node_keeps_its_live_card_payload(snapshot_with_federation):
    """MOMUS showed "Frozen — unreachable, no live data" on the public LIVE map while it
    answered in half a second: this route copied metrics and status and dropped momus_live."""
    body = snapshot_with_federation.get("/api/topology?mode=real").json()
    momus = next(n for n in body["nodes"] if n["id"] == "momus")
    assert momus["momus_live"] == {"service": "momus", "prod": True}
    assert momus["metrics"] == {"findings": 20} and momus["status"] == "active"
    assert "hub_env_snippet" not in momus
