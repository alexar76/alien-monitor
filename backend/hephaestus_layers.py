"""HEPHAESTUS studio node — topology anchor + graph links for Alien Monitor.

Placed between the hub (where the signed catalogue is) and the factory (where the pipeline
executor is), because that is literally what it does: read what is on sale, compose a
graph, hand it to the executor, and show the bill of materials that comes back.
"""

from __future__ import annotations

from typing import Any

from ecosystem_layout import node_position
from hephaestus_status import hephaestus_links, hephaestus_public_url


def hephaestus_node_spec(*, mode: str = "real") -> dict[str, Any]:
    _ = mode
    return {
        "id": "hephaestus",
        "label": "HEPHAESTUS",
        "group": "studio",
        "icon": "forge",
        "description": (
            "The forge — compose capability chains from the live signed catalogue, price the "
            "graph BEFORE spending anything, then run it and keep the signed bill of materials. "
            "Hop-level blame included: when a chain fails, the failing hop is named, and the "
            "upstream hops that did their work are explicitly cleared. Reads the hub manifest, "
            "submits to the factory's pipeline executor. Click for real runs and how much of the "
            "catalogue is actually composable."
        ),
        "metrics": {"runs": 0, "spend_usd": 0, "capabilities": 0},
        "status": "offline",
        "position": node_position("hephaestus"),
        "url": hephaestus_public_url(),
        "links": hephaestus_links(),
    }


def hephaestus_topology_links() -> list[dict[str, str]]:
    """Directed edges: what the studio reads, what it submits, what comes back."""
    return [
        {"source": "hephaestus", "target": "hub", "label": "Catalogue + prices"},
        {"source": "hephaestus", "target": "factory", "label": "Pipeline submit"},
        {"source": "factory", "target": "hephaestus", "label": "Signed BoM"},
    ]
