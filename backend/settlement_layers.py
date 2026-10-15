"""Settlement node — topology anchor and edges for Alien Monitor.

Placed between the hub and the escrow, because that is literally where it sits: the hub
records what a buyer authorised, a signer turns one such authorisation into one
``debitChannel``, and the escrow is where the result becomes true.

The node is named for the *function*, not for the service that performs it. HORKOS, the
policy signer that holds the key, is deliberately not a node: it is unreachable from here by
design (a reverse tunnel from the hub host only), and drawing it would invite exactly the
poll this architecture exists to prevent. What the canvas shows is the effect it has on chain,
which is public anyway.
"""

from __future__ import annotations

from typing import Any

from ecosystem_layout import node_position
from settlement_status import collector_public_url, escrow_public_url

SETTLEMENT_COLOR = "#5ad1a8"


def settlement_node_spec(*, mode: str = "real") -> dict[str, Any]:
    """Static fields shared by TEST, LIVE and UNI."""
    _ = mode
    return {
        "id": "settlement",
        "label": "SETTLEMENT",
        "group": "crypto",
        "icon": "ledger",
        "description": (
            "Where an off-chain debit becomes an on-chain fact. The hub records what a buyer "
            "signed; one canonical debitChannel per authorisation turns it into escrow state; "
            "usedAmount is what the operator may withdraw at settle. Numbers here are read "
            "from the escrow itself — held, collected-and-unswept, and the collector's gas "
            "float. The signed-but-unsubmitted queue is NOT shown: it does not exist on chain, "
            "and publishing it would tell a griefer when the budget is thin."
        ),
        # Only the window count is seeded. The USD figures and the gas float are absent
        # until they are READ: seeding them with 0.0 made an unreadable chain look like a
        # settled one, which is the exact confusion this node exists to remove.
        "metrics": {"recent_debits": 0},
        "status": "offline",
        "position": node_position("settlement"),
        "color": SETTLEMENT_COLOR,
        "url": escrow_public_url(),
        "links": [
            {"label": "Escrow on Basescan", "url": escrow_public_url()},
            {"label": "Collector on Basescan", "url": collector_public_url()},
        ],
    }


def settlement_topology_links() -> list[dict[str, str]]:
    """Directed edges, in the order value actually moves.

    The hub→settlement edge is labelled `authorisation` rather than `payment`: the hub hands
    over a buyer-signed permission, never funds and never a key. The settlement→escrow edge is
    the only one that writes chain state, and the escrow→settlement edge is the read that
    makes this node honest (every number it shows comes back from the contract).
    """
    return [
        {"source": "hub", "target": "settlement", "label": "Signed authorisation"},
        {"source": "settlement", "target": "evm_escrow", "label": "debitChannel"},
        {"source": "evm_escrow", "target": "settlement", "label": "usedAmount · read"},
    ]
