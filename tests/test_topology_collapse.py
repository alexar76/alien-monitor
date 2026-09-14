"""Topology fallback must match WebSocket graph (collapsed catalog, not loose product planets)."""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from factory_products import CATALOG_CLUSTER_ID  # noqa: E402
from universe import VirtualUniverse  # noqa: E402


def test_universe_topology_collapses_product_planets():
    u = VirtualUniverse()
    u.seed_entities()
    u.materialize_product({"id": "prod-a", "name": "Alpha", "category": "saas"})
    u.materialize_product({"id": "prod-b", "name": "Beta", "category": "saas"})

    nodes = [e.to_node() for e in u.entities.values()]
    links = u.get_topology_links()
    from factory_products import collapse_graph_products

    nodes, links = collapse_graph_products(nodes, links)

    assert not any(n.get("group") == "product" for n in nodes)
    assert any(n.get("id") == CATALOG_CLUSTER_ID and n.get("group") == "cluster" for n in nodes)
    assert any(lnk.get("target") == CATALOG_CLUSTER_ID for lnk in links)
