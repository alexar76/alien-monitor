"""DOLOS node — topology anchor + graph links for Alien Monitor.

Placed in the security tier beside BASANOS: BASANOS reads the Solidity statically, DOLOS attacks it
dynamically on a throwaway fork. The incoming edges are the contract trees it forks and attacks; the
outgoing edges are what it does with a result — a signed finding to the SKOPOS remediation
conductor, and a confirm/refute relationship with BASANOS's static flags (DOLOS is the layer that
proves which of them are real).
"""

from __future__ import annotations

from typing import Any

from dolos_status import dolos_links, dolos_public_url
from ecosystem_layout import node_position

DOLOS_COLOR = "#e5484d"  # crimson — the attacker, distinct from BASANOS's gold touchstone


def dolos_node_spec(*, mode: str = "real") -> dict[str, Any]:
    _ = mode
    return {
        "id": "dolos",
        "label": "DOLOS",
        "group": "security",
        "icon": "blade",
        "description": (
            "The exploit crafter (Δόλος, trickery) — a DYNAMIC EVM red team for the UNI bubble. It "
            "forks the bubble's Anvil and throws real exploit transactions at the deployed "
            "contracts, so it proves which flaws are real and which are static-analysis noise: on "
            "the live UNI contracts it refuted a BASANOS false positive by actually attempting the "
            "hijack and being reverted. On the sandbox chain it drives the full loop — attack, fix, "
            "forge-test, redeploy, re-attack — to a signed 'fixed'. It never touches a chain it "
            "cannot throw away; a finding from a real chain is advisory only. Complements BASANOS "
            "(static) and MOMUS (HTTP/federation). Click for the last scan and the console."
        ),
        "metrics": {"attacks": 3, "exploited": 0, "held": 0},
        "status": "idle",
        "position": node_position("dolos"),
        "color": DOLOS_COLOR,
        "url": dolos_public_url(),
        "links": dolos_links(),
    }


def dolos_topology_links() -> list[dict[str, str]]:
    """Directed edges: the contract trees it forks and attacks, and what it does with a finding."""
    return [
        {"source": "acex", "target": "dolos", "label": "fork & attack"},
        {"source": "lottery", "target": "dolos", "label": "fork & attack"},
        {"source": "evm_escrow", "target": "dolos", "label": "fork & attack"},
        # The dynamic layer confirms or refutes the static one.
        {"source": "dolos", "target": "basanos", "label": "confirm / refute"},
        # A confirmed sandbox finding feeds the self-healing loop.
        {"source": "dolos", "target": "skopos", "label": "signed finding"},
    ]
