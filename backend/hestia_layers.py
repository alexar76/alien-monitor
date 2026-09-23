"""HESTIA hearth node — topology anchor + graph links for Alien Monitor.

The hearth hosts sellers on the operator's machines. Hub stays the catalogue;
THEMIS (optional) can still refuse a start; Factory only scaffolds. Agents
appear on the roster only after an explicit signed deploy — an empty hearth
is not an empty market.
"""

from __future__ import annotations

from typing import Any

from ecosystem_layout import node_position
from hestia_status import hestia_links, hestia_public_url

HESTIA_COLOR = "#ff9a3c"


def hestia_node_spec(*, mode: str = "real") -> dict[str, Any]:
    """Static fields shared by TEST, LIVE and UNI."""
    _ = mode
    return {
        "id": "hestia",
        "label": "HESTIA",
        "group": "infra",
        "icon": "hearth",
        "description": (
            "The hearth — isolated hosted runtime for AIMarket capability providers on the "
            "operator's machines. Not the Hub catalogue, not Factory, not a job board. "
            "Agents appear only after an explicit signed deploy onto this host; an empty "
            "roster means nothing is hosted here, not that the market is empty. Isolation "
            "first. THEMIS can still refuse a start. Hub stays the market."
        ),
        "metrics": {"tenants": 0, "announced": 0},
        "status": "offline",
        "position": node_position("hestia"),
        "color": HESTIA_COLOR,
        "url": hestia_public_url(),
        "links": hestia_links(),
    }


def hestia_topology_links() -> list[dict[str, str]]:
    """Directed edges: scaffold → hearth, optional admit, explicit announce.

    Factory writes a signed bundle; the hearth is where that process actually
    runs. THEMIS may refuse a start. Announce is a knock on the Hub catalogue,
    never a listing by itself.
    """
    return [
        {"source": "factory", "target": "hestia", "label": "Signed deploy"},
        {"source": "themis", "target": "hestia", "label": "Optional admit"},
        {"source": "hestia", "target": "hub", "label": "Explicit announce"},
    ]
