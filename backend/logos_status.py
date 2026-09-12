"""LOGOS status poller for the Alien Monitor.

The node card showed dashes where its numbers belong because this module polled
only /health — a payload of {status, service, version} that carries no counts at
all — and handed it straight to the card as `logos_live`. Nothing was broken; there
was simply nothing to render.

It now reads what LOGOS actually publishes: the federation snapshot (hubs,
capabilities, findings, per-source reachability with MEASURED latency), the open
anomaly count, and the spend digest. Every number below comes from the service.
Where LOGOS reports nothing, the field is absent rather than zero — a zero on a
dashboard is a measurement, and inventing one is worse than a dash.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from poll_cache import ttl_cached

DEFAULT_LOGOS_URL = "http://logos:5199"
LOGOS_URL = (
    os.environ.get("ALIEN_LOGOS_URL")
    or os.environ.get("LOGOS_URL")
    or DEFAULT_LOGOS_URL
)


def _base() -> str:
    return LOGOS_URL.rstrip("/")


def poll_url() -> str:
    return f"{_base()}/health"


def public_url() -> str:
    explicit = os.environ.get("ALIEN_PUBLIC_LOGOS_URL", "").strip()
    if explicit:
        return explicit
    base = os.environ.get("ECO_PUBLIC_BASE", "").strip()
    if base:
        return f"{base.rstrip('/')}:5199"
    return "https://logos.modelmarket.dev"


def links() -> dict[str, str]:
    return {
        "github": "https://github.com/alexar76/logos",
        "docs": "https://github.com/alexar76/logos#readme",
        "landing": "https://alexar76.github.io/logos/",
    }


def _get(client: httpx.Client, path: str) -> dict[str, Any]:
    """One read. A failure is an absent section, never a fabricated one."""
    try:
        r = client.get(f"{_base()}{path}")
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@ttl_cached(env_var="ALIEN_LOGOS_CACHE_TTL")
def fetch_logos_status_sync(timeout: float = 6.0) -> dict[str, Any]:
    """Health plus the analytics LOGOS publishes, cached by poll_cache. Never raises."""
    return _fetch_uncached(timeout)


def _fetch_uncached(timeout: float) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=timeout) as client:
            health = _get(client, "/health")
            if not health:
                return {}
            snapshot = _get(client, "/api/v1/snapshot")
            anomalies = _get(client, "/api/v1/anomalies?status=open")
            consumption = _get(client, "/api/v1/consumption")
    except Exception:
        return {}
    return {
        "health": health,
        "snapshot": snapshot,
        "open_anomalies": len(anomalies.get("anomalies") or []) if anomalies else None,
        "consumption": consumption,
    }


def _sources(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """The sources LOGOS polled, with their own status and measured round-trip.

    This is the part that makes the card worth opening: not "analytics exist" but
    which component answered, how fast, and what it reported.
    """
    out: list[dict[str, Any]] = []
    if snapshot.get("status"):
        out.append({
            "name": "hub",
            "status": snapshot.get("status"),
            "elapsed_ms": snapshot.get("_elapsed_ms"),
            "value": snapshot.get("total_capabilities"),
            "unit": "capabilities",
        })
    findings = snapshot.get("findings") or {}
    if findings.get("status"):
        out.append({
            "name": "momus",
            "status": findings.get("status"),
            "elapsed_ms": findings.get("_elapsed_ms"),
            "value": findings.get("total_findings"),
            "unit": "findings",
        })
    treasury = snapshot.get("treasury") or {}
    if treasury.get("status"):
        out.append({
            "name": "treasury",
            "status": treasury.get("status"),
            "elapsed_ms": treasury.get("_elapsed_ms"),
            "value": treasury.get("available_usd"),
            "unit": "usd",
        })
    return out


def _live_payload(status: dict[str, Any]) -> dict[str, Any]:
    snapshot = status.get("snapshot") or {}
    consumption = status.get("consumption") or {}
    findings = snapshot.get("findings") or {}

    payload: dict[str, Any] = {
        "version": (status.get("health") or {}).get("version"),
        "sources": _sources(snapshot),
    }

    healthy, total = snapshot.get("healthy_hubs"), snapshot.get("total_hubs")
    if total is not None:
        # The card reads one string, and "0/1" says more than either number alone.
        payload["hubs_online"] = f"{healthy if healthy is not None else '?'}/{total}"
    if snapshot.get("total_capabilities") is not None:
        payload["capabilities"] = snapshot["total_capabilities"]
    if snapshot.get("federated_capabilities") is not None:
        payload["federated_capabilities"] = snapshot["federated_capabilities"]
    if findings.get("total_findings") is not None:
        payload["findings"] = findings["total_findings"]
    if status.get("open_anomalies") is not None:
        payload["open_anomalies"] = status["open_anomalies"]
    if snapshot.get("generated_at"):
        payload["generated_at"] = snapshot["generated_at"]

    # Spend is published only from measured settlement volume; when LOGOS says it
    # has none, the card must say so rather than print $0.
    basis = consumption.get("spend_basis")
    if basis:
        payload["spend_basis"] = basis
        if consumption.get("estimated_monthly_spend_usd") is not None:
            payload["monthly_spend_usd"] = consumption["estimated_monthly_spend_usd"]
        if consumption.get("paid_capabilities") is not None:
            payload["paid_capabilities"] = consumption["paid_capabilities"]
    return payload


def apply_logos_to_nodes(nodes: list[dict], status: dict) -> None:
    """Stamp the live payload and real metrics onto the LOGOS node."""
    node = next((n for n in nodes if n.get("id") == "logos"), None)
    if node is None:
        return
    node["url"] = public_url()
    node["links"] = links()

    if not status:
        node["status"] = "offline"
        node.pop("logos_live", None)
        node["metrics"] = {}          # absent, not zeroed
        return

    payload = _live_payload(status)
    node["status"] = "active" if (status.get("health") or {}).get("status") == "ok" else "idle"
    node["logos_live"] = payload

    metrics: dict[str, Any] = {}
    if "hubs_online" in payload:
        metrics["hubs_online"] = payload["hubs_online"]
    if "capabilities" in payload:
        metrics["capabilities"] = payload["capabilities"]
    if "findings" in payload:
        metrics["findings"] = payload["findings"]
    if "open_anomalies" in payload:
        metrics["anomalies"] = payload["open_anomalies"]
    reachable = [s for s in payload["sources"] if s.get("status") == "ok"]
    if payload["sources"]:
        metrics["sources_ok"] = f"{len(reachable)}/{len(payload['sources'])}"
    node["metrics"] = metrics


def apply_logos_graph(nodes: list[dict], *, mode: str = "real") -> None:
    _ = mode
    apply_logos_to_nodes(nodes, fetch_logos_status_sync())
