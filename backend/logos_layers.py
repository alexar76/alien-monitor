"""LOGOS node definition for the Alien Monitor ecosystem graph."""

from __future__ import annotations

from ecosystem_layout import node_position


def logos_node_spec() -> dict:
    return {
        "id": "logos",
        "label": "LOGOS",
        "group": "cognition",
        "icon": "🧠",
        "description": (
            "Read-only federation analytics — real source snapshots, measured "
            "settlement volume, rolling z-score anomalies and Metis-assisted insights."
        ),
        "metrics": {},
        "status": "unknown",
        "position": node_position("logos"),
        "url": "",
        "links": {
            "github": "https://github.com/alexar76/logos",
        },
    }


def logos_topology_links() -> list[dict]:
    """Links from LOGOS to the hub and Metis."""
    return [
        {"source": "logos", "target": "hub", "label": "federation data"},
        {"source": "logos", "target": "metis", "label": "NL understanding"},
        {"source": "logos", "target": "momus", "label": "findings"},
        {"source": "logos", "target": "treasury", "label": "balance"},
    ]
