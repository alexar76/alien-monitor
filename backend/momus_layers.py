"""MOMUS red-team node + Treasury payer node — topology anchors for Alien Monitor.

Two nodes on purpose. MOMUS finds and signs; the Treasury (its own key, its own container) is the
only thing that can pay. Drawing them as separate orbs with a "pays / separate key" edge is how
the graph makes the "someone else pays" property visible — the auditor and the purse are not the
same actor.
"""

from __future__ import annotations

from typing import Any

from ecosystem_layout import node_position
from momus_status import momus_links, momus_public_url
from treasury_status import treasury_links, treasury_public_url


def momus_node_spec(*, mode: str = "real") -> dict[str, Any]:
    _ = mode
    return {
        "id": "momus",
        "label": "MOMUS",
        "group": "security",
        "icon": "eye",
        "description": (
            "Autonomous red team — the offensive complement to ARGUS's defensive WARDEN. Runs "
            "SAFE, read-only conformance/adversarial probes against the ecosystem's OWN components "
            "(oracle free-tier ceilings, manifest/receipt signatures, settlement gates, "
            "prompt-injection surfaces) and emits Ed25519-signed findings. Self-learning: it "
            "ingests public security reports and its own + peers' confirmed findings, and probes "
            "the classes that pay off first. Momus demanded a window in the chest — MOMUS is that "
            "window. It finds and signs; it CANNOT pay itself — the Treasury (separate key) does."
        ),
        "metrics": {"findings": 0, "targets": 0, "learned": 0},
        "status": "offline",
        "position": node_position("momus"),
        "url": momus_public_url(),
        "links": momus_links(),
    }


def treasury_node_spec(*, mode: str = "real") -> dict[str, Any]:
    _ = mode
    return {
        "id": "treasury",
        "label": "Treasury",
        "group": "security",
        "icon": "vault",
        "description": (
            "The separate payer role for MOMUS red-team bounties. Holds the ONE key that can "
            "release a bounty — a key MOMUS never sees. It re-verifies every finding + verdict "
            "signature itself, requires an independent-verifier quorum (≥2 distinct keys for "
            "high/critical, one a registered external verifier like Metis), enforces a dedup "
            "replay-guard and an anti-griefing deposit, and fails closed when crypto is off. An "
            "optional DeepSeek-backed explainer narrates each decision — advisory only, never part "
            "of the authorization."
        ),
        "metrics": {"paid": 0, "held": 0, "refused": 0},
        "status": "offline",
        "position": node_position("treasury"),
        "url": treasury_public_url(),
        "links": treasury_links(),
    }


def momus_topology_links() -> list[dict[str, str]]:
    return [
        # Offense ↔ defense: the two halves of "auditable, not marketing".
        {"source": "momus", "target": "argus", "label": "Red team ↔ blue team"},
        # Metis is both MOMUS's independent verifier and (optionally) its cognition.
        {"source": "momus", "target": "metis", "label": "Independent verify + wisdom"},
        # MOMUS sells scans on the hub.
        {"source": "momus", "target": "hub", "label": "Sells red-team scans"},
        # The separation, drawn: MOMUS submits, the Treasury pays.
        {"source": "momus", "target": "treasury", "label": "Submits finding · cannot pay itself"},
        # The Treasury settles through escrow, never through MOMUS.
        {"source": "treasury", "target": "evm_escrow", "label": "Bounty settlement (separate key)"},
    ]
