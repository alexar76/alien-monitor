"""BASANOS — poll the Solidity touchstone for the monitor node.

The agent's only write path is a paid ``POST /invoke`` that runs a scan, so this
poller never touches it: a monitor that spends money to draw a node would bill the
operator for every 1.5 s tick. What is left is genuinely observable —

  * ``/health``  — identity: version, capability id, provider pubkey, whether
    allowlisted intel ingestion is enabled at all
  * ``/memos``   — what the memo store learned: memos, hits, distilled lessons and
    the exploration weight that steers detector order
  * ``/intel``   — allowlisted OSV/GHSA advisory cards and the learned pairs

None of these carry a verdict, and the node must not imply one. A verdict exists
only per scan, belongs to the signed pack of that scan, and nothing here has run a
scan — so the node reports what the touchstone *knows*, not what it *decided*.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from poll_cache import ttl_cached

DEFAULT_BASANOS_URL = "https://basanos.modelmarket.dev"
DEFAULT_GITHUB_URL = "https://github.com/alexar76/basanos"
DEFAULT_PAGES_URL = "https://alexar76.github.io/basanos/"

# The store returns its own top-N; this is the panel's own ceiling on top of it.
CARD_LIMIT = 8
LESSON_LIMIT = 6


def basanos_url() -> str:
    """Where the agent answers. Host-local first when the monitor runs beside it."""
    return (
        os.environ.get("ALIEN_BASANOS_URL")
        or os.environ.get("BASANOS_URL")
        or DEFAULT_BASANOS_URL
    ).rstrip("/")


def basanos_public_url() -> str:
    """What a browser should open — may differ from the polled address."""
    return (
        os.environ.get("ALIEN_PUBLIC_BASANOS_URL")
        or os.environ.get("BASANOS_PUBLIC_URL")
        or basanos_url()
    ).rstrip("/")


def basanos_links() -> dict[str, str]:
    github = (os.environ.get("ALIEN_BASANOS_GITHUB_URL") or DEFAULT_GITHUB_URL).rstrip("/")
    public = basanos_public_url()
    return {
        "console": f"{public}/ui/",
        "landing": public,
        "github": github,
        "pages": DEFAULT_PAGES_URL,
    }


def _health_facts(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {
        "ok": bool(raw.get("ok")),
        "version": str(raw.get("version") or ""),
        "capability_id": str(raw.get("capability_id") or ""),
        "provider_pubkey": str(raw.get("provider_pubkey") or ""),
        "intel_enabled": bool(raw.get("intel_enabled")),
        "role": str(raw.get("role") or ""),
        # The agent publishes what it is NOT; the map has confused it with
        # AgentAuditPool and HEPHAESTUS before, so carry the disclaimer through.
        "not": [str(item) for item in (raw.get("not") or []) if isinstance(item, str)][:8],
    }


def _memo_facts(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    lessons = raw.get("lessons")
    return {
        "total": int(raw.get("memos_total") or 0),
        "hits": int(raw.get("hits") or 0),
        "exploration": raw.get("exploration") if isinstance(raw.get("exploration"), (int, float)) else None,
        "lessons": [str(item) for item in lessons if isinstance(item, str)][:LESSON_LIMIT]
        if isinstance(lessons, list)
        else [],
    }


def _intel_facts(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    scores = raw.get("category_scores")
    cards = raw.get("recent_cards")
    safe_cards: list[dict[str, Any]] = []
    if isinstance(cards, list):
        for card in cards[:CARD_LIMIT]:
            if not isinstance(card, dict):
                continue
            safe_cards.append({
                "id": str(card.get("id") or ""),
                "category": str(card.get("category") or ""),
                "source": str(card.get("source") or ""),
                "severity": card.get("severity"),
                "ingested_at": card.get("ingested_at"),
            })
    return {
        "enabled": bool(raw.get("intel_enabled")),
        "cards": int(raw.get("cards_total") or 0),
        "learned_pairs": int(raw.get("learned_pairs") or 0),
        "category_scores": {
            str(k): v for k, v in scores.items() if isinstance(v, (int, float))
        } if isinstance(scores, dict) else {},
        "recent_cards": safe_cards,
    }


@ttl_cached(ttl_s=25.0, env_var="ALIEN_BASANOS_TTL_S")
def fetch_basanos_status_sync() -> dict[str, Any] | None:
    """Read health, memos and intel. A partial read is still worth drawing."""
    base = basanos_url()
    health: dict[str, Any] = {}
    memos: dict[str, Any] = {}
    intel: dict[str, Any] = {}

    try:
        with httpx.Client(timeout=4.0) as client:
            try:
                resp = client.get(f"{base}/health")
                if resp.status_code == 200:
                    health = _health_facts(resp.json())
            except Exception:
                pass
            # Without /health there is no agent to describe; the two learning
            # endpoints alone cannot tell a live touchstone from a stray 200.
            if not health:
                return None
            try:
                resp = client.get(f"{base}/memos")
                if resp.status_code == 200:
                    memos = _memo_facts(resp.json())
            except Exception:
                pass
            try:
                resp = client.get(f"{base}/intel")
                if resp.status_code == 200:
                    intel = _intel_facts(resp.json())
            except Exception:
                pass
    except Exception:
        return None

    return {"health": health, "memos": memos, "intel": intel}


def apply_basanos_to_nodes(
    nodes: list[dict[str, Any]], status: dict[str, Any] | None, *, public_url: str | None = None
) -> None:
    node = next((item for item in nodes if item.get("id") == "basanos"), None)
    if node is None:
        return
    # Deep-links outlive a failed poll — an offline node still has a console to open.
    node["url"] = public_url or basanos_public_url()
    node["links"] = basanos_links()

    if not status:
        node["status"] = "offline"
        node.pop("basanos_live", None)
        node["metrics"] = {"intel_cards": 0, "memos": 0, "learned_pairs": 0}
        return

    health = status.get("health") or {}
    memos = status.get("memos") or {}
    intel = status.get("intel") or {}

    if not health.get("ok"):
        node["status"] = "error"
    elif memos.get("total") or intel.get("cards"):
        # "active" means the touchstone has actually learned something. A reachable
        # agent with an empty memo and intel store is idle, and saying so is the
        # difference between this node and decoration.
        node["status"] = "active"
    else:
        node["status"] = "idle"

    node["metrics"] = {
        "intel_cards": int(intel.get("cards") or 0),
        "memos": int(memos.get("total") or 0),
        "learned_pairs": int(intel.get("learned_pairs") or 0),
    }
    node["basanos_live"] = {
        "console_url": basanos_links()["console"],
        "version": health.get("version") or None,
        "capability_id": health.get("capability_id") or None,
        "provider_pubkey": health.get("provider_pubkey") or None,
        "role": health.get("role") or None,
        "not": health.get("not") or [],
        "intel_enabled": bool(health.get("intel_enabled")),
        "memos": memos,
        "intel": intel,
    }


def apply_basanos_graph(nodes: list[dict[str, Any]], *, mode: str = "real") -> None:
    _ = mode
    apply_basanos_to_nodes(nodes, fetch_basanos_status_sync())
