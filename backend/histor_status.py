"""HISTOR — poll the MCP transparency log for the monitor node.

Two public reads and nothing else: ``/health`` (identity, store, tree size, whether a crawl is
running and whether the last one failed) and ``/api/v1/stats`` (the last crawl, current counts,
changes per named window, the signed tree head). Both are free and read-only; the monitor never
calls ``/api/v1/check`` or the operator route.

Every figure keeps the window HISTOR publishes it under. A dashboard that shows "changes" without
saying "in 7 days" is how lifetime counters end up read as today's (dashboard-number honesty).
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from poll_cache import ttl_cached

DEFAULT_HISTOR_URL = "https://histor.modelmarket.dev"
DEFAULT_GITHUB_URL = "https://github.com/alexar76/histor"
DEFAULT_PAGES_URL = "https://alexar76.github.io/histor/"


def histor_url() -> str:
    """Where the log answers. Host-local first when the monitor runs beside it."""
    return (os.environ.get("ALIEN_HISTOR_URL") or os.environ.get("HISTOR_URL") or DEFAULT_HISTOR_URL).rstrip("/")


def histor_public_url() -> str:
    """What a browser should open — may differ from the polled address."""
    return (os.environ.get("ALIEN_PUBLIC_HISTOR_URL") or os.environ.get("HISTOR_PUBLIC_URL") or histor_url()).rstrip("/")


def histor_links() -> dict[str, str]:
    public = histor_public_url()
    return {
        "desk": public,
        "log": f"{public}/log",
        "changes": f"{public}/changes",
        "feed": f"{public}/feed.xml",
        "github": (os.environ.get("ALIEN_HISTOR_GITHUB_URL") or DEFAULT_GITHUB_URL).rstrip("/"),
        "pages": DEFAULT_PAGES_URL,
    }


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


@ttl_cached(ttl_s=30.0, env_var="ALIEN_HISTOR_TTL_S")
def fetch_histor_status_sync() -> dict[str, Any] | None:
    """Health plus stats. A reachable log with a failing stats read is still worth drawing."""
    base = histor_url()
    try:
        with httpx.Client(timeout=4.0) as client:
            try:
                resp = client.get(f"{base}/health")
                health = resp.json() if resp.status_code == 200 else None
            except Exception:
                health = None
            if not isinstance(health, dict):
                return None
            try:
                resp = client.get(f"{base}/api/v1/stats")
                stats = resp.json() if resp.status_code == 200 else {}
            except Exception:
                stats = {}
    except Exception:
        return None
    return {"health": health, "stats": stats if isinstance(stats, dict) else {}}


def apply_histor_to_nodes(nodes: list[dict[str, Any]], status: dict[str, Any] | None) -> None:
    node = next((item for item in nodes if item.get("id") == "histor"), None)
    if node is None:
        return
    node["url"] = histor_public_url()
    node["links"] = histor_links()

    if not status:
        node["status"] = "offline"
        node.pop("histor_live", None)
        node["metrics"] = {}  # absent, not zeroed: a zero would be a measurement
        return

    def as_dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    health = as_dict(status.get("health"))
    stats = as_dict(status.get("stats"))
    log = as_dict(stats.get("log"))
    targets = as_dict(stats.get("targets"))
    changes = as_dict(stats.get("changes"))
    run = as_dict(stats.get("lastRun"))

    crawl = stats.get("crawl") if isinstance(stats.get("crawl"), dict) else {}
    run_error = run.get("error") or crawl.get("lastError") or health.get("last_crawl_error")
    if not health.get("ok"):
        node["status"] = "error"
    elif health.get("crawl_running"):
        node["status"] = "active"
    elif run_error:
        # A failed or interrupted crawl is an error until one finishes cleanly, including after
        # HISTOR restarts — the runs table remembers it even when the process does not.
        node["status"] = "error"
    else:
        node["status"] = "idle" if not _int(log.get("treeSize")) else "active"

    metrics: dict[str, Any] = {}
    if _int(log.get("treeSize")) is not None:
        metrics["labels"] = _int(log.get("treeSize"))
    if _int(targets.get("pinned")) is not None:
        metrics["pinned"] = _int(targets.get("pinned"))
    if _int(changes.get("last7d")) is not None:
        metrics["changes_7d"] = _int(changes.get("last7d"))
    if _int(run.get("registryEndpoints")) is not None:
        metrics["endpoints"] = _int(run.get("registryEndpoints"))
    node["metrics"] = metrics

    statuses = run.get("statuses") if isinstance(run.get("statuses"), dict) else {}
    node["histor_live"] = {
        "version": health.get("version") or None,
        "store": health.get("store") or None,
        "crawl_running": bool(health.get("crawl_running")),
        "last_crawl_error": health.get("last_crawl_error") or None,
        "tree_size": _int(log.get("treeSize")),
        "root_hash": (log.get("rootHash") or "")[:16] or None,
        "sth_at": log.get("sthTimestamp") or None,
        "last_run_finished": run.get("finishedAt") or None,
        "last_run_error": run_error or None,
        "registry_servers": _int(run.get("registryServers")),
        "registry_endpoints": _int(run.get("registryEndpoints")),
        "attempted": _int(run.get("attempted")),
        "answered_ok": _int(statuses.get("ok")),
        # absent, not zeroed: a run that recorded no statuses measured nothing
        "auth_required": (sum(v for k, v in statuses.items() if k in ("http-401", "http-403") and isinstance(v, int))
                          if statuses else None),
        "pinned": _int(targets.get("pinned")),
        "block_tier": _int(targets.get("block_tier")),
        "changes": {k: _int(changes.get(k)) for k in ("last24h", "last7d", "last30d")},
        "not": ["a safety rating", "the code", "behaviour"],
    }


def apply_histor_graph(nodes: list[dict[str, Any]], *, mode: str = "real") -> None:
    _ = mode
    apply_histor_to_nodes(nodes, fetch_histor_status_sync())
