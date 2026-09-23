"""HISTOR node — the public memory of what MCP servers advertised.

WARDEN decides at connect time, on one client, from what that client sees. HISTOR records what
every remote endpoint in the official MCP registry advertised, day after day, as signed MTL/1
labels in an RFC 9162 Merkle log — so a client can ask whether what it received is what everyone
else is seeing. It sits in the security sector next to WARDEN (whose published gates its scanner
runs; WARDEN does not call HISTOR today) and the Hub (to which it offers ``histor.check@v1``). It says what was advertised and when it changed; it never calls a server
safe, and the node's copy does not either.
"""

from __future__ import annotations

from typing import Any

from ecosystem_layout import node_position
from histor_status import histor_links, histor_public_url

HISTOR_COLOR = "#ffd58a"


def histor_node_spec(*, mode: str = "real") -> dict[str, Any]:
    """Static fields shared by TEST, LIVE and UNI."""
    _ = mode
    return {
        "id": "histor",
        "label": "HISTOR",
        "group": "security",
        "icon": "scroll",
        "description": (
            "Public transparency log of MCP tool definitions. Reads what every remote endpoint in the "
            "official MCP registry advertises (initialize + tools/list, never a tool call), signs it as MTL/1 labels on "
            "AWR/2, appends every label to an RFC 9162 Merkle log with signed tree heads, dates each "
            "change with a per-tool diff, and answers /check: is what a client received what was "
            "observed at that endpoint? Advertised text only — not the code, not behaviour, never a "
            "safety rating."
        ),
        "metrics": {},
        "status": "offline",
        "position": node_position("histor"),
        "color": HISTOR_COLOR,
        "url": histor_public_url(),
        "links": histor_links(),
    }


def histor_topology_links() -> list[dict[str, str]]:
    """Only edges that exist: HISTOR runs WARDEN's published gates in its scanner sidecar, and
    it is an AIMarket peer offering ``histor.check@v1`` to the Hub."""
    return [
        {"source": "warden", "target": "histor", "label": "Pattern set + gates (@aimarket/warden)"},
        {"source": "histor", "target": "hub", "label": "histor.check@v1"},
    ]
