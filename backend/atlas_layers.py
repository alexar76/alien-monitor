"""ATLAS physical sensor-map node — topology anchor for Alien Monitor."""

from __future__ import annotations

from typing import Any

from atlas_status import atlas_links, atlas_public_url
from ecosystem_layout import node_position


def atlas_node_spec(*, mode: str = "real") -> dict[str, Any]:
    _ = mode
    return {
        "id": "atlas",
        "label": "ATLAS",
        "group": "physical",
        "icon": "globe",
        "description": (
            "Physical sensor map — live weather, air, tide, river, marine, grid "
            "carbon and earthquakes plotted from GAIA relays. Single shared poller "
            "fans out snapshots over SSE; click for mini-map embed or open the full map."
        ),
        "metrics": {"stations": 0, "online": 0, "quakes": 0},
        "status": "offline",
        "position": node_position("atlas"),
        "url": atlas_public_url(),
        "links": atlas_links(),
    }


def atlas_topology_links() -> list[dict[str, str]]:
    return [
        {"source": "atlas", "target": "gaia", "label": "Live relays"},
        {"source": "atlas", "target": "hub", "label": "Map surface"},
    ]
