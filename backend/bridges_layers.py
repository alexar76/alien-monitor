"""aimarket-bridges node — topology anchor + graph links for Alien Monitor.

The ecosystem's third paid invoke channel. The hub and the mesh are already on the map; the
bridges are the door through which a LangGraph, CrewAI or AutoGen agent walks into the same
catalogue, and until now the map of the economy did not show it at all.

It is drawn as a source of billed traffic INTO the hub, not as an ornament: the edge is the
claim, and the panel is where that claim is either backed by counters or admitted to be
unmeasured.
"""

from __future__ import annotations

from typing import Any

from bridges_status import bridges_links, bridges_public_url
from ecosystem_layout import node_position


def bridges_node_spec(*, mode: str = "real") -> dict[str, Any]:
    """Static ``bridges`` node fields shared by TEST / LIVE / UNI topologies."""
    _ = mode
    return {
        "id": "bridges",
        "label": "Bridges",
        # Same category as the hub and the mesh: a channel through which invokes are billed.
        "group": "core",
        "icon": "bridge",
        "description": (
            "aimarket-bridges — the ecosystem's third paid invoke channel, alongside the hub "
            "and the mesh. It exposes AIMarket capabilities as NATIVE tools inside "
            "LangChain/LangGraph, CrewAI and AutoGen: the hub's catalogue becomes a tool list "
            "the agent's own planner picks from, every call returns a signed receipt verified "
            "against the capability's ORIGIN key (not the hub's — 42 of 47 capabilities are "
            "federated), and a hard per-toolbox budget ceiling is claimed BEFORE each call, so "
            "an agent that loops cannot outspend it. A refused input comes back as a sentence "
            "the model can act on instead of an exception that kills the graph. It is a client "
            "LIBRARY, not a service: it runs inside the buyer's own process, which is why this "
            "node reports no traffic — nothing anywhere counts it."
        ),
        # Deliberately empty, not zeroed. This channel has no counter; `{}` renders as absent,
        # `{"paid_invokes": 0}` would render as measured-and-none. See bridges_status.py.
        "metrics": {},
        "status": "offline",
        "position": node_position("bridges"),
        "url": bridges_public_url(),
        "links": bridges_links(),
    }


def bridges_topology_links() -> list[dict[str, str]]:
    """Directed edges: framework agents bill through the bridges into the hub."""
    return [
        # The load-bearing edge: this is where the money would flow, which is exactly why the
        # node must say out loud that the flow is not measured.
        {"source": "bridges", "target": "hub", "label": "Paid invokes · signed receipts"},
    ]
