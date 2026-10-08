"""BASANOS touchstone node — topology anchor + graph links for Alien Monitor.

Placed on the contract side of the hub, next to the Solidity it actually reads:
``basanos/basanos/inventory.py`` resolves its root ids to ``acex/contracts/evm/src``,
``lottery/contracts/src``, ``contracts/evm/src`` and ``contracts/zk/verifier``, and
those trees are what the incoming edges below stand for.

The outgoing edge is deliberately labelled advisory. The pack is an Ed25519-signed
technical verdict pinned to a commit and tree digest — it is not insurance, does not
mint ``scoreBps``, and coverage on AgentAuditPool stays a human call.
"""

from __future__ import annotations

from typing import Any

from basanos_status import basanos_links, basanos_public_url
from ecosystem_layout import node_position

BASANOS_COLOR = "#e8c36a"


def basanos_node_spec(*, mode: str = "real") -> dict[str, Any]:
    """Static fields shared by TEST, LIVE and UNI."""
    _ = mode
    return {
        "id": "basanos",
        "label": "BASANOS",
        "group": "security",
        "icon": "stone",
        "description": (
            "The Lydian touchstone for ecosystem Solidity — scrape the alloy and emit an "
            "Ed25519-signed assurance pack (PASS, REVIEW or FAIL) pinned to a commit and a "
            "tree digest. Detector set is closed: allowlisted OSV/GHSA intel may reorder it, "
            "never extend it, and no verdict here mints a score. Not AgentAuditPool insurance, "
            "not HEPHAESTUS the forge, not MOMUS runtime probes, not THEMIS admission. Click "
            "for what it has learned and the operator console."
        ),
        "metrics": {"intel_cards": 0, "memos": 0, "learned_pairs": 0},
        "status": "offline",
        "position": node_position("basanos"),
        "color": BASANOS_COLOR,
        "url": basanos_public_url(),
        "links": basanos_links(),
    }


def basanos_topology_links() -> list[dict[str, str]]:
    """Directed edges: the Solidity trees it scans, and the advisory that comes back.

    ACEX appears twice on purpose — its contracts are an input, and the pack is an
    input to the human AgentAuditPool decision. Drawing only one of the two would
    read as either a scanner nobody consumes or a scorer of nothing.
    """
    return [
        {"source": "acex", "target": "basanos", "label": "Solidity tree"},
        {"source": "lottery", "target": "basanos", "label": "Solidity tree"},
        {"source": "evm_escrow", "target": "basanos", "label": "Solidity tree"},
        {"source": "basanos", "target": "acex", "label": "Assurance pack · advisory"},
    ]
