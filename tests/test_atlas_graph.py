"""ATLAS graph node — topology + health polling."""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from atlas_layers import atlas_node_spec, atlas_topology_links  # noqa: E402
from atlas_status import apply_atlas_graph, apply_atlas_to_nodes  # noqa: E402
from main import build_topology  # noqa: E402


def test_topology_includes_atlas_node():
    nodes, links = build_topology()
    ids = {n["id"] for n in nodes}
    assert "atlas" in ids
    assert any(l["source"] == "atlas" and l["target"] == "gaia" for l in links)
    assert any(l["source"] == "atlas" and l["target"] == "hub" for l in links)


def test_atlas_node_spec_defaults_offline():
    spec = atlas_node_spec()
    assert spec["id"] == "atlas"
    assert spec["group"] == "physical"
    assert spec["status"] == "offline"
    assert atlas_topology_links()


def test_atlas_links_point_at_the_satellite_repo():
    """atlas/ is stripped from the public aicom mirror — that path 404s."""
    from atlas_status import atlas_links

    links = atlas_links()
    assert links["github"] == "https://github.com/alexar76/atlas"
    assert "aicom/tree/main/atlas" not in links["github"]
    assert links["docs"].startswith("https://github.com/alexar76/atlas")
    assert links["embed"].endswith("/embed")


def test_apply_atlas_graph_marks_offline_when_unreachable(monkeypatch):
    nodes = [atlas_node_spec()]
    monkeypatch.setattr("atlas_status.fetch_atlas_status_sync", lambda **_: None)
    apply_atlas_graph(nodes, mode="real")
    assert nodes[0]["status"] == "offline"


def test_apply_atlas_graph_marks_active_on_health(monkeypatch):
    nodes = [atlas_node_spec()]
    status = {
        "health": {"ok": True, "version": "0.1.0", "stations": 3},
        "monitor": {
            "version": "0.1.0",
            "status": "ok",
            "station_count": 3,
            "online": 3,
            "quake_count": 1,
            "layers": ["weather", "quake"],
            "embed_url": "https://atlas.example/embed",
            "map_url": "https://atlas.example",
            "stations": [{"id": "om-wx-01", "layer": "weather", "headline": "22 °C", "online": True}],
            "quakes": [{"id": "q1", "lat": 1.0, "lon": 2.0, "magnitude": 4.2}],
        },
    }
    monkeypatch.setattr("atlas_status.fetch_atlas_status_sync", lambda **_: status)
    apply_atlas_graph(nodes, mode="real")
    assert nodes[0]["status"] == "active"
    assert nodes[0]["atlas_live"]["station_count"] == 3
    assert nodes[0]["metrics"]["quakes"] == 1
    assert nodes[0]["atlas_live"]["embed_url"].endswith("/embed")


def test_apply_atlas_to_nodes_offline_clears_live():
    nodes = [atlas_node_spec()]
    nodes[0]["atlas_live"] = {"station_count": 9}
    apply_atlas_to_nodes(nodes, None)
    assert nodes[0]["status"] == "offline"
    assert "atlas_live" not in nodes[0]


def test_atlas_demo_stations_include_river_marine():
    from atlas_status import atlas_demo_stations, fill_atlas_sim_node

    ids = {s["id"] for s in atlas_demo_stations()}
    assert {"usgs-river-01", "ndbc-01", "om-marine-01"} <= ids
    node = atlas_node_spec()
    fill_atlas_sim_node(node)
    assert {"river", "marine"} <= set(node["atlas_live"]["layers"])
    assert node["metrics"]["live"] >= 5
