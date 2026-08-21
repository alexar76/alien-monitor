"""Competing lab galaxy — second Hub VPS nodes for Alien Monitor.

Far-offset cluster (see ``COMPETING_GALAXY_ANCHOR`` in ecosystem_layout) so the
Monitor reads as two galaxies: primary at origin, competing lab ~30 units away.
"""

from __future__ import annotations

import math
import os
from typing import Any
from urllib.parse import urlparse

import httpx

from ecosystem_layout import node_position

_DEFAULT_LAB = "http://hunt.modelmarket.dev:9083"
_DEFAULT_HUNT = "https://hunt.modelmarket.dev"
_DEFAULT_USE = "https://use.modelmarket.dev"


def competing_hub_url() -> str:
    return (
        os.environ.get("ALIEN_COMPETING_HUB_URL", "").strip()
        or os.environ.get("ALIEN_LAB_HUB_URL", "").strip()
        or _DEFAULT_LAB
    )


def signal_hunt_url() -> str:
    return os.environ.get("ALIEN_SIGNAL_HUNT_URL", "").strip() or _DEFAULT_HUNT


def use_cases_url() -> str:
    return os.environ.get("ALIEN_USE_CASES_URL", "").strip() or _DEFAULT_USE


def competing_hub_node_spec() -> dict[str, Any]:
    return {
        "id": "competing_hub",
        "label": "Competing Lab Hub",
        "group": "network",
        "icon": "hub",
        "role": "hub",
        "color": "#ff8c42",
        "description": (
            "Second federation Hub (UNI-only) on the competing lab VPS — "
            "public peer for discovery/crawl alongside modelmarket.dev."
        ),
        "metrics": {"peers": 0, "capabilities": 0, "trust_score": 0.0},
        "status": "unknown",
        "position": node_position("competing_hub"),
        "url": competing_hub_url(),
        "galaxy": "competing",
    }


def signal_hunt_hub_node_spec() -> dict[str, Any]:
    """Federation Hub process served at hunt.modelmarket.dev — a real peer sun."""
    return {
        "id": "signal_hunt_hub",
        "label": "Signal Hunt Hub",
        "group": "network",
        "icon": "hub",
        "role": "hub",
        "color": "#d946ef",
        "description": (
            "Signal Hunt's own federation Hub (signal-hunt-hub) — peer of the mesh "
            "with local signal.* capabilities on hunt.modelmarket.dev."
        ),
        "metrics": {"peers": 0, "capabilities": 0, "trust_score": 0.0, "local_capabilities": 0},
        "status": "unknown",
        "position": node_position("signal_hunt_hub"),
        "url": signal_hunt_url(),
        "galaxy": "competing",
    }


def signal_hunt_node_spec() -> dict[str, Any]:
    """Signal Hunt game/app — separate ball from its Hub."""
    return {
        "id": "signal_hunt",
        "label": "Signal Hunt",
        "group": "client",
        "icon": "radar",
        "role": "app",
        "color": "#ff5ec8",
        "description": (
            "Signal Hunt UNI game — capability hunt UI on hunt.modelmarket.dev. "
            "Runs against Signal Hunt Hub (not a Hub sun itself)."
        ),
        "metrics": {"local_capabilities": 5},
        "status": "unknown",
        "position": node_position("signal_hunt"),
        "url": signal_hunt_url(),
        "galaxy": "competing",
    }


def use_cases_node_spec() -> dict[str, Any]:
    return {
        "id": "use_cases",
        "label": "Use Cases Portal",
        "group": "client",
        "icon": "widget",
        "description": "Public use-cases portal on the competing lab edge (use.modelmarket.dev).",
        "metrics": {},
        "status": "unknown",
        "position": node_position("use_cases"),
        "url": use_cases_url(),
        "galaxy": "competing",
    }


def competing_lab_topology_links() -> list[dict[str, str]]:
    """Edges: primary federation ↔ competing galaxy; hub hosts game; lab mesh."""
    return [
        {"source": "federation", "target": "competing_hub", "label": "Federated peer"},
        {"source": "federation", "target": "signal_hunt_hub", "label": "Federated peer"},
        {"source": "hub", "target": "competing_hub", "label": "Federation mesh"},
        {"source": "hub", "target": "signal_hunt_hub", "label": "Federation mesh"},
        {"source": "competing_hub", "target": "signal_hunt_hub", "label": "Lab peer"},
        {"source": "signal_hunt_hub", "target": "signal_hunt", "label": "Hosts game"},
        {"source": "competing_hub", "target": "use_cases", "label": "Public edge"},
    ]


def _host_key(url: str) -> str:
    try:
        p = urlparse(url if "://" in url else f"http://{url}")
        host = (p.hostname or "").lower()
        port = p.port
        if port and port not in (80, 443):
            return f"{host}:{port}"
        return host
    except Exception:
        return url.lower().strip()


def _match_peer(peers: list[dict], target_url: str) -> dict | None:
    want = _host_key(target_url)
    if not want:
        return None
    for p in peers:
        if not isinstance(p, dict):
            continue
        for key in (p.get("url"), p.get("well_known_url"), p.get("name")):
            if key and _host_key(str(key)) == want:
                return p
    return None


def _summary_int(stats: dict, *keys: str) -> int | None:
    """Read an int from stats/live (top-level or ``summary``) / well-known payloads."""
    bags = [stats]
    summary = stats.get("summary")
    if isinstance(summary, dict):
        bags.append(summary)
    for bag in bags:
        for key in keys:
            if key not in bag:
                continue
            try:
                return int(bag[key])
            except (TypeError, ValueError):
                continue
    return None


_HUNT_CARD_METRIC_KEYS = ("capabilities", "peers", "trust_score")


def _overlay_metrics(src: dict | None, dst: dict | None, keys: tuple[str, ...] = _HUNT_CARD_METRIC_KEYS) -> None:
    """Copy federation stats from Signal Hunt Hub onto the game ball.

    The sidebar card for ``signal_hunt`` reads capabilities / peers / trust_score.
    Those live on the Hub sun; without this copy the game panel shows dashes
    even when the Hub poll succeeded (and UNI sim already filled the Hub).
    """
    if not src or not dst:
        return
    sm = src.get("metrics")
    if not isinstance(sm, dict):
        return
    dm = dst.setdefault("metrics", {})
    for key in keys:
        if key in sm and sm[key] is not None:
            dm[key] = sm[key]


async def enrich_competing_lab_nodes(
    nodes: list[dict],
    *,
    primary_hub_url: str,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Poll lab hub health + primary federation trust_score onto competing nodes.

    Trust comes from the *primary* hub's view of the peer (age + bond + success + volume).
    Local hub always scores 1.0 for itself — we want the federation score of the lab.

    Peers / capabilities come from the lab's own ``/stats/live`` ``summary``
    (``peers_count``, ``offerable_capabilities_count``) — not the top-level
    keys (those do not exist on the live payload).
    """
    by_id = {n["id"]: n for n in nodes if isinstance(n, dict) and "id" in n}
    hub_node = by_id.get("competing_hub")
    hunt_hub_node = by_id.get("signal_hunt_hub")
    hunt_game = by_id.get("signal_hunt")
    use_node = by_id.get("use_cases")
    if not hub_node and not hunt_hub_node and not hunt_game and not use_node:
        return

    lab = competing_hub_url().rstrip("/")
    hunt = signal_hunt_url().rstrip("/")
    use = use_cases_url().rstrip("/")
    primary = primary_hub_url.rstrip("/")

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=6.0)
    assert client is not None
    try:
        peers: list[dict] = []
        try:
            r = await client.get(f"{primary}/ai-market/v2/federation/peers")
            if r.status_code == 200:
                data = r.json()
                peers = data.get("peers", []) if isinstance(data, dict) else []
        except Exception:
            peers = []

        if hub_node:
            peer = _match_peer(peers, lab)
            trust = None
            if peer is not None:
                try:
                    trust = float(peer.get("trust_score"))
                except (TypeError, ValueError):
                    trust = None
            metrics = hub_node.setdefault("metrics", {})
            try:
                hr = await client.get(f"{lab}/ai-market/v2/stats/live")
                if hr.status_code == 200:
                    raw = hr.json()
                    stats = raw if isinstance(raw, dict) else {}
                    # Prefer what the storefront shows (offerable), then total indexed.
                    caps = _summary_int(
                        stats,
                        "offerable_capabilities_count",
                        "capabilities_count",
                        "federated_capabilities_count",
                        "capabilities",
                        "tools",
                    )
                    peer_n = _summary_int(stats, "peers_count", "peers")
                    if caps is not None:
                        metrics["capabilities"] = caps
                    if peer_n is not None:
                        metrics["peers"] = peer_n
                    # Optional extras for the detail panel
                    offerable = _summary_int(stats, "offerable_capabilities_count")
                    federated = _summary_int(stats, "federated_capabilities_count")
                    if offerable is not None:
                        metrics["offerable"] = offerable
                    if federated is not None:
                        metrics["federated"] = federated
                    hub_node["status"] = "active"
                else:
                    if peer is not None:
                        hub_node["status"] = "idle"
            except Exception:
                if peer is not None:
                    hub_node["status"] = "idle"
            # Fallback: primary's crawl record (may lag / be 0 until re-crawl)
            if not metrics.get("capabilities") and peer is not None:
                try:
                    pc = int(peer.get("capabilities_count") or 0)
                    if pc:
                        metrics["capabilities"] = pc
                except (TypeError, ValueError):
                    pass
            if trust is not None:
                metrics["trust_score"] = round(max(0.0, min(1.0, trust)), 4)
            hub_node["role"] = "hub"
            hub_node["color"] = hub_node.get("color") or "#ff8c42"
            hub_node["galaxy"] = "competing"

        if hunt_hub_node:
            peer = _match_peer(peers, hunt) or _match_peer(peers, f"{hunt}/")
            trust = None
            if peer is not None:
                try:
                    trust = float(peer.get("trust_score"))
                except (TypeError, ValueError):
                    trust = None
            hm = hunt_hub_node.setdefault("metrics", {})
            try:
                hr = await client.get(f"{hunt}/ai-market/v2/stats/live", follow_redirects=True)
                if hr.status_code == 200:
                    raw = hr.json()
                    stats = raw if isinstance(raw, dict) else {}
                    caps = _summary_int(
                        stats,
                        "offerable_capabilities_count",
                        "capabilities_count",
                        "federated_capabilities_count",
                    )
                    peer_n = _summary_int(stats, "peers_count", "peers")
                    local_n = _summary_int(stats, "real_local_capabilities_count")
                    if caps is not None:
                        hm["capabilities"] = caps
                    if peer_n is not None:
                        hm["peers"] = peer_n
                    if local_n is not None:
                        hm["local_capabilities"] = local_n
                    else:
                        hm["local_capabilities"] = 5
                    hunt_hub_node["status"] = "active"
                else:
                    health = await client.get(f"{hunt}/health", follow_redirects=True)
                    hunt_hub_node["status"] = "active" if health.status_code < 500 else "error"
            except Exception:
                hunt_hub_node["status"] = "idle" if peer else "unknown"
            if trust is not None:
                hm["trust_score"] = round(max(0.0, min(1.0, trust)), 4)
            elif peer is not None:
                try:
                    hm["trust_score"] = round(float(peer.get("trust_score") or 0), 4)
                except (TypeError, ValueError):
                    pass
            if not hm.get("capabilities") and peer is not None:
                try:
                    hc = int(peer.get("capabilities_count") or 0)
                    if hc:
                        hm["capabilities"] = hc
                except (TypeError, ValueError):
                    pass
            hunt_hub_node["role"] = "hub"
            hunt_hub_node["icon"] = "hub"
            hunt_hub_node["galaxy"] = "competing"
            hunt_hub_node["color"] = hunt_hub_node.get("color") or "#d946ef"

        if hunt_game:
            gm = hunt_game.setdefault("metrics", {})
            gm["local_capabilities"] = gm.get("local_capabilities") or 5
            try:
                # Game UI shares the hunt origin — page up means the app is reachable.
                gr = await client.get(hunt, follow_redirects=True)
                hunt_game["status"] = "active" if gr.status_code < 500 else "error"
            except Exception:
                hunt_game["status"] = "unknown"
            hunt_game["role"] = "app"
            hunt_game["icon"] = hunt_game.get("icon") or "radar"
            hunt_game["group"] = hunt_game.get("group") or "client"
            hunt_game["galaxy"] = "competing"
            hunt_game["color"] = hunt_game.get("color") or "#ff5ec8"
            _overlay_metrics(hunt_hub_node, hunt_game)

        if use_node:
            try:
                ur = await client.get(use, follow_redirects=True)
                use_node["status"] = "active" if ur.status_code < 500 else "error"
            except Exception:
                use_node["status"] = "unknown"
            use_node["galaxy"] = "competing"
    finally:
        if owns_client:
            await client.aclose()


def apply_competing_lab_sim_metrics(nodes: list[dict], tick: int) -> None:
    """TEST-mode: give the lab hub a moving trust so size animation is visible."""
    hub = next((n for n in nodes if n.get("id") == "competing_hub"), None)
    if hub:
        # Oscillate 0.35..0.85 so operators see trust→fatness without LIVE peers.
        trust = 0.35 + 0.5 * (0.5 + 0.5 * math.sin(tick * 0.07))
        hub.setdefault("metrics", {})
        hub["metrics"]["trust_score"] = round(trust, 4)
        hub["metrics"]["peers"] = 2 + (tick % 3)
        hub["metrics"]["capabilities"] = 40 + (tick % 20)
        hub["status"] = "active"
        hub["role"] = "hub"
        hub["color"] = "#ff8c42"
        hub["galaxy"] = "competing"
    hunt_hub = next((n for n in nodes if n.get("id") == "signal_hunt_hub"), None)
    if hunt_hub:
        hunt_hub.setdefault("metrics", {})
        hunt_hub["metrics"]["trust_score"] = round(0.3 + 0.4 * (0.5 + 0.5 * math.sin(tick * 0.09)), 4)
        hunt_hub["metrics"]["peers"] = 2 + (tick % 2)
        hunt_hub["metrics"]["capabilities"] = 50 + (tick % 15)
        hunt_hub["metrics"]["local_capabilities"] = 5
        hunt_hub["status"] = "active"
        hunt_hub["role"] = "hub"
        hunt_hub["icon"] = "hub"
        hunt_hub["color"] = "#d946ef"
        hunt_hub["galaxy"] = "competing"
    hunt = next((n for n in nodes if n.get("id") == "signal_hunt"), None)
    if hunt:
        hunt.setdefault("metrics", {})
        hunt["metrics"]["local_capabilities"] = 5
        hunt["status"] = "active"
        hunt["role"] = "app"
        hunt["icon"] = "radar"
        hunt["group"] = "client"
        hunt["color"] = "#ff5ec8"
        hunt["galaxy"] = "competing"
        _overlay_metrics(hunt_hub, hunt)
    use = next((n for n in nodes if n.get("id") == "use_cases"), None)
    if use:
        use["status"] = "active"
        use["galaxy"] = "competing"
