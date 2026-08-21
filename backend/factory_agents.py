"""
Agents the factory built, as participants in the economy.

The catalog already shows what the factory *produced*. This shows what those
products are *doing*: a product that ships as an autonomous agent keeps running
after release, invokes capabilities from the mesh, pays for them, and reports
counters. One ball on the map, click for the roster — the ARGUS pattern, sourced
from the factory's ``/api/agents`` registry rather than from local heartbeats.

Each roster row carries the SDK the agent integrated through, so the operator can
see at a glance which of our published clients are actually load-bearing.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from ecosystem_layout import node_position
from factory_products import factory_public_url
from poll_cache import ttl_cached

logger = logging.getLogger(__name__)

DEFAULT_APP_URL = "http://127.0.0.1:9081"
MAX_ROSTER_ROWS = 60


def factory_agents_poll_url() -> str:
    return (
        os.environ.get("ALIEN_FACTORY_APP_URL")
        or os.environ.get("ALIEN_FACTORY_URL")
        or DEFAULT_APP_URL
    ).rstrip("/")


def factory_agents_public_url() -> str:
    return f"{factory_public_url()}/agents"


@ttl_cached(env_var="ALIEN_FACTORY_AGENTS_CACHE_TTL")
def fetch_agents_sync(*, base_url: str | None = None, timeout: float = 6.0) -> dict[str, Any] | None:
    root = (base_url or factory_agents_poll_url()).rstrip("/")
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(f"{root}/api/agents")
            if r.status_code != 200:
                return None
            doc = r.json()
    except Exception as exc:  # network/JSON — treat as "no data", never crash the map
        logger.debug("factory_agents: poll failed: %s", exc)
        return None
    if not isinstance(doc, dict):
        return None
    return doc


def _row(agent: dict[str, Any]) -> dict[str, Any]:
    stats = agent.get("stats") if isinstance(agent.get("stats"), dict) else {}
    return {
        "agent_id": str(agent.get("agent_id") or ""),
        "name": str(agent.get("name") or agent.get("agent_id") or ""),
        "product_id": str(agent.get("product_id") or ""),
        "sdk": str(agent.get("sdk") or ""),
        "version": str(agent.get("version") or ""),
        "public_url": str(agent.get("public_url") or ""),
        "status": str(agent.get("status") or "offline"),
        "verified": bool(agent.get("verified")),
        "age_sec": float(agent.get("age_sec") or 0),
        "capabilities_used": list(agent.get("capabilities_used") or [])[:12],
        "invokes_total": int(float(stats.get("invokes_total") or 0)),
        "invokes_24h": int(float(stats.get("invokes_24h") or 0)),
        "spend_usd_total": round(float(stats.get("spend_usd_total") or 0), 4),
        "spend_usd_24h": round(float(stats.get("spend_usd_24h") or 0), 4),
        "errors_24h": int(float(stats.get("errors_24h") or 0)),
    }


def factory_agents_node_spec(*, mode: str = "real") -> dict[str, Any]:
    _ = mode
    return {
        "id": "factory_agents",
        "label": "Factory Agents",
        # Not "argus": App.tsx routes every argus-group node to the ARGUS run panel,
        # which would hide this roster behind a different product's UI.
        "group": "agent",
        "icon": "client",
        "description": (
            "Autonomous agents the factory built and shipped — the products that "
            "keep running after release. Each one invokes mesh capabilities, pays "
            "for them and reports counters. Click for the roster: SDK, capabilities, "
            "invokes and spend per participant."
        ),
        "metrics": {
            "agents_live": 0,
            "agents_total": 0,
            "invokes_total": 0,
            "spend_usd_total": 0,
        },
        "status": "offline",
        "position": node_position("factory_agents"),
        "url": factory_agents_public_url(),
    }


def factory_agents_topology_links() -> list[dict[str, str]]:
    return [
        {"source": "factory", "target": "factory_agents", "label": "Ships agent"},
        {"source": "factory_agents", "target": "hub", "label": "Capability invoke"},
        {"source": "factory_agents", "target": "atlas", "label": "Sensor reads"},
    ]


def apply_factory_agents_graph(nodes: list[dict[str, Any]], *, mode: str = "real") -> None:
    """Fill the ``factory_agents`` ball from the live registry."""
    node = next((n for n in nodes if n.get("id") == "factory_agents"), None)
    if node is None:
        return
    doc = fetch_agents_sync()
    if not doc:
        node["factory_agents_live"] = {"stale": True, "agents": [], "summary": {}}
        return

    agents = doc.get("agents") if isinstance(doc.get("agents"), list) else []
    summary = doc.get("summary") if isinstance(doc.get("summary"), dict) else {}
    rows = [_row(a) for a in agents if isinstance(a, dict)][:MAX_ROSTER_ROWS]
    live = sum(1 for r in rows if r["status"] == "live")

    node["label"] = f"Agents · {len(rows)}" if rows else "Factory Agents"
    node["metrics"] = {
        "agents_live": live,
        "agents_total": int(summary.get("agents_total") or len(rows)),
        "invokes_total": int(summary.get("invokes_total") or 0),
        "spend_usd_total": round(float(summary.get("spend_usd_total") or 0), 4),
    }
    node["status"] = "active" if live else ("idle" if rows else "offline")
    node["factory_agents_live"] = {
        "stale": False,
        "agents": rows,
        "summary": {
            "agents_total": int(summary.get("agents_total") or len(rows)),
            "agents_live": live,
            "invokes_total": int(summary.get("invokes_total") or 0),
            "spend_usd_total": round(float(summary.get("spend_usd_total") or 0), 4),
            "sdks": summary.get("sdks") if isinstance(summary.get("sdks"), dict) else {},
            "capabilities": (
                summary.get("capabilities")
                if isinstance(summary.get("capabilities"), dict)
                else {}
            ),
        },
    }
