"""THEMIS — publish admission node for Alien Monitor."""

from __future__ import annotations

from typing import Any

from ecosystem_layout import node_position

DEFAULT_GITHUB_URL = "https://github.com/alexar76/themis"
DEFAULT_LANDING_URL = "https://alexar76.github.io/themis/"
DEFAULT_TUTORIAL_URL = (
    "https://github.com/alexar76/create-aimarket-agent/blob/main/docs/tutorials/"
    "themis.en.md"
)


def themis_node_spec(*, mode: str = "real") -> dict[str, Any]:
    """Static fields shared by TEST, LIVE and UNI."""
    _ = mode
    return {
        "id": "themis",
        "label": "THEMIS",
        "group": "security",
        "icon": "shield",
        "description": (
            "Signed admission gate for AI-agent supply chains. It evaluates a capability's "
            "identity, permissions, evidence, cost and schemas before AIMarket Hub lists it. "
            "The deterministic decision returns immediately; Metis is an asynchronous advisory."
        ),
        "metrics": {
            "audits_total": 0,
            "approved": 0,
            "review": 0,
            "rejected": 0,
            "metis_pending": 0,
        },
        "status": "offline",
        "position": node_position("themis"),
        "color": "#66f7c5",
        "url": DEFAULT_LANDING_URL,
        "links": {
            "landing": DEFAULT_LANDING_URL,
            "github": DEFAULT_GITHUB_URL,
            "tutorial": DEFAULT_TUTORIAL_URL,
        },
    }


def themis_topology_links() -> list[dict[str, str]]:
    """The gate sits between a publisher, cognition and the Hub catalogue."""
    return [
        {"source": "factory", "target": "themis", "label": "Candidate dossier"},
        {"source": "themis", "target": "metis", "label": "Async advisory"},
        {"source": "themis", "target": "hub", "label": "Admission receipt"},
        {"source": "themis", "target": "momus", "label": "Manual review"},
    ]


def fill_themis_sim_node(node: dict[str, Any], tick: int) -> None:
    total = 18 + max(0, tick)
    review = 2 + (tick % 2)
    rejected = 3 + (tick // 9)
    approved = max(0, total - review - rejected)
    decisions = ("approve", "approve", "review", "reject")
    latest_decision = decisions[tick % len(decisions)]
    score = {"approve": 96, "review": 74, "reject": 41}[latest_decision]
    risk = {"approve": "low", "review": "medium", "reject": "critical"}[latest_decision]
    node["status"] = "active"
    node["metrics"] = {
        "audits_total": total,
        "approved": approved,
        "review": review,
        "rejected": rejected,
        "metis_pending": 1 if tick % 3 else 0,
    }
    node["themis_live"] = {
        "mode": "enforce",
        "configured": True,
        "simulated": True,
        "latest": {
            "decision": latest_decision,
            "score": score,
            "risk_tier": risk,
            "metis_status": "pending" if tick % 3 else "completed",
            "capability_id": "invoice.read@v1",
        },
        "recent": [
            {
                "audit_id": f"sim-{tick}",
                "capability_id": "invoice.read@v1",
                "publisher_id": "trusted-vendor",
                "decision": latest_decision,
                "score": score,
                "risk_tier": risk,
                "metis": {"status": "pending" if tick % 3 else "completed"},
            }
        ],
    }


def _attach_themis_links(node: dict[str, Any]) -> None:
    """Deep-links survive offline polls — same contract as apply_momus_to_nodes."""
    spec = themis_node_spec()
    node["url"] = spec["url"]
    node["links"] = dict(spec["links"])
    if spec.get("color"):
        node["color"] = spec["color"]


def apply_themis_to_nodes(
    nodes: list[dict[str, Any]], hub_payload: dict[str, Any] | None
) -> None:
    node = next((item for item in nodes if item.get("id") == "themis"), None)
    if node is None:
        return
    _attach_themis_links(node)
    if not isinstance(hub_payload, dict):
        node["status"] = "offline"
        node.pop("themis_live", None)
        return

    summary_root = hub_payload.get("summary")
    summary = (
        summary_root.get("supply_chain_admission")
        if isinstance(summary_root, dict)
        else None
    )
    if not isinstance(summary, dict):
        node["status"] = "offline"
        node.pop("themis_live", None)
        return

    mode = str(summary.get("mode") or "off")
    configured = bool(summary.get("configured"))
    if mode == "off":
        node["status"] = "disabled"
    elif not configured:
        node["status"] = "error"
    else:
        node["status"] = "active"

    node["metrics"] = {
        "audits_total": int(summary.get("total") or 0),
        "approved": int(summary.get("approved") or 0),
        "review": int(summary.get("review") or 0),
        "rejected": int(summary.get("rejected") or 0),
        "metis_pending": int(summary.get("metis_pending") or 0),
    }
    recent = hub_payload.get("supply_chain_audits")
    safe_recent = [item for item in recent[:10] if isinstance(item, dict)] if isinstance(recent, list) else []
    node["themis_live"] = {
        "mode": mode,
        "configured": configured,
        "simulated": False,
        "latest": summary.get("latest") if isinstance(summary.get("latest"), dict) else None,
        "recent": safe_recent,
        "capability_id": summary.get("capability_id"),
    }


def apply_themis_graph(
    nodes: list[dict[str, Any]],
    *,
    mode: str = "real",
    tick: int = 0,
    hub_payload: dict[str, Any] | None = None,
) -> None:
    """Decorate THEMIS: always links; live Hub when present; UNI SIM fallback."""
    apply_themis_to_nodes(nodes, hub_payload)
    node = next((item for item in nodes if item.get("id") == "themis"), None)
    if node is None:
        return
    if mode == "universe" and not node.get("themis_live"):
        fill_themis_sim_node(node, tick)
        _attach_themis_links(node)

