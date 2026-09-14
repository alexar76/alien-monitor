"""The WARDEN node — the invoke-time MCP firewall, drawn as a layer rather than a host.

Every other security node on this map is a service with an address: THEMIS gates publication, MOMUS
probes, the Treasury pays. WARDEN is the one that is a LIBRARY — `@aimarket/warden` with zero
runtime dependencies, running in-process inside whatever MCP host loads it. It has no port and no
health endpoint, and for a while that was the reason it was missing from the graph entirely: the
assistant, asked "where is WARDEN?", answered "inside ARGUS", which reads as though the firewall
were one agent's feature rather than the ecosystem's invoke-time gate.

So it is a node, with the honest shape of what it is: no host badge, telemetry borrowed from the two
ends that DO have addresses (MOMUS signs the feed it consumes, ARGUS enforces it), and edges that
say which direction each relationship runs.
"""

from __future__ import annotations

from typing import Any

from ecosystem_layout import node_position
from warden_status import warden_links, warden_public_url


def warden_node_spec(*, mode: str = "real") -> dict[str, Any]:
    _ = mode
    return {
        "id": "warden",
        "label": "WARDEN",
        "group": "security",
        "icon": "shield",
        "description": (
            "The invoke-time MCP firewall, shipped as its own zero-dependency npm package "
            "`@aimarket/warden`. It is a LIBRARY, not a service: it runs in-process inside whatever "
            "MCP host loads it, so it has no port, no /health and no daemon — which is why this node "
            "is a LAYER, not a host. Every third-party MCP server is vetted before a single tool "
            "definition reaches the model: static scan of the tool name, description and input schema "
            "(ruleset v3, 25 rules) → signed threat feed → origin (operator-declared vs remote "
            "catalog) → tool-def and launch-identity pinning. The verdict is allow/block plus a 0..1 "
            "composite score, a per-tool partition so one poisoned tool can be quarantined without "
            "severing the connection, and the exact rule table that produced it. It decides from LOCAL "
            "facts only: no oracle is consulted and no socket is opened while vetting, and the score "
            "is its own — NOT a LUMEN reputation score (that gate was removed). ARGUS is its reference "
            "host, so blocks surface as ARGUS telemetry; MOMUS is the reference publisher of its "
            "signed feed. THEMIS gates publication BEFORE a capability is listed; WARDEN gates the "
            "invoke."
        ),
        "metrics": {"feed_records": 0, "builtin_floor": 11, "gates": 4},
        "status": "idle",
        "position": node_position("warden"),
        "url": warden_public_url(),
        "links": warden_links(),
    }


def warden_topology_links() -> list[dict[str, str]]:
    return [
        # The red team feeds the blue team. Signed, one-directional, and the only
        # thing a publisher can do is ADD records — it can never switch a gate off.
        {"source": "momus", "target": "warden", "label": "Signed threat feed (Ed25519)"},
        # The library runs inside the host; the host is where a block becomes visible.
        {"source": "warden", "target": "argus", "label": "Runs in-process · reference host"},
        # Publish-time gate vs invoke-time gate: the pair that is easy to confuse.
        {"source": "themis", "target": "warden", "label": "Publish gate → invoke gate"},
    ]
