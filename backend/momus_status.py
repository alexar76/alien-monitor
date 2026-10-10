"""Poll the MOMUS adversarial-audit satellite for the Alien Monitor ``momus`` node.

MOMUS is the ecosystem's autonomous **red team** — the offensive complement to ARGUS's defensive
WARDEN. It runs safe, read-only conformance/adversarial probes against the ecosystem's own
components and emits Ed25519-signed findings; a SEPARATE Treasury role (its own key) is the only
thing that can pay a bounty, and only on independent verification. This module is best-effort and
offline-safe: if MOMUS is unreachable the node shows ``offline`` and the rest of the monitor is
unaffected.

Three FREE reads build the node (no channel, no debit, read-only):

    GET  /health     → service/version, provider {kind, model, reachable}, posture, scanner_pubkey,
                       and (crucially) holds_treasury_key:false — the visible proof of separation
    GET  /findings   → recent signed findings (severity, target, probe, status)
    GET  /intel      → self-learning state: threat-intel cards + per-attack-class probe weights
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from poll_cache import ttl_cached

DEFAULT_MOMUS_URL = "https://momus.modelmarket.dev"
DEFAULT_PUBLIC_MOMUS_URL = "https://momus.modelmarket.dev"
DEFAULT_MOMUS_GITHUB_URL = "https://github.com/alexar76/momus"


def momus_poll_url() -> str:
    return (os.environ.get("ALIEN_MOMUS_URL") or os.environ.get("MOMUS_URL")
            or DEFAULT_MOMUS_URL).rstrip("/")


def momus_public_url() -> str:
    return (os.environ.get("ALIEN_PUBLIC_MOMUS_URL") or os.environ.get("MOMUS_PUBLIC_URL")
            or DEFAULT_PUBLIC_MOMUS_URL).rstrip("/")


def momus_links() -> dict[str, str]:
    github = (os.environ.get("ALIEN_MOMUS_GITHUB_URL") or os.environ.get("MOMUS_GITHUB_URL")
              or DEFAULT_MOMUS_GITHUB_URL).rstrip("/")
    return {"landing": momus_public_url(), "github": github, "docs": f"{github}#readme"}


_SEV_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


def _sanitize_findings(raw: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    for f in raw:
        if not isinstance(f, dict):
            continue
        ev = f.get("evidence") or {}
        out.append({
            "finding_id": f.get("finding_id"),
            "target": f.get("target"),
            "target_kind": f.get("target_kind"),
            "probe": f.get("probe"),
            "category": f.get("category"),
            "severity": f.get("severity"),
            "outcome": f.get("outcome"),
            "status": f.get("status"),
            "title": f.get("title"),
            "status_code": ev.get("status_code") if isinstance(ev, dict) else None,
            "signed": bool((f.get("signature") or {}).get("value")),
        })
    out.sort(key=lambda d: _SEV_RANK.get(str(d.get("severity")), 0), reverse=True)
    return out[:20]


@ttl_cached(env_var="ALIEN_MOMUS_CACHE_TTL")
def fetch_momus_status_sync(*, base_url: str | None = None, timeout: float = 4.0) -> dict[str, Any] | None:
    """Return ``{"health":..., "findings":[...], "intel":...}`` or ``None`` if MOMUS is down."""
    root = (base_url or momus_poll_url()).rstrip("/")
    try:
        with httpx.Client(timeout=timeout) as client:
            h = client.get(f"{root}/health")
            if h.status_code != 200:
                return None
            health = h.json()
            if not isinstance(health, dict):
                return None
            findings: list[dict[str, Any]] = []
            intel: dict[str, Any] = {}
            try:
                r = client.get(f"{root}/findings", params={"limit": 20})
                if r.status_code == 200 and isinstance(r.json(), dict):
                    findings = _sanitize_findings(r.json().get("findings"))
            except Exception:
                findings = []
            try:
                r = client.get(f"{root}/intel")
                if r.status_code == 200 and isinstance(r.json(), dict):
                    body = r.json()
                    intel = {
                        "cards_total": body.get("cards_total", 0),
                        "category_scores": body.get("category_scores", {}),
                        "learned_pairs": body.get("learned_pairs", 0),
                        "intel_enabled": body.get("intel_enabled", False),
                    }
            except Exception:
                intel = {}
            return {"health": health, "findings": findings, "intel": intel}
    except Exception:
        return None


def _live_payload(status: dict[str, Any]) -> dict[str, Any]:
    health = status.get("health") or {}
    findings = status.get("findings") or []
    provider = health.get("provider") or {}
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for f in findings:
        sev = str(f.get("severity"))
        if sev in counts and f.get("outcome") == "finding":
            counts[sev] += 1
    return {
        "version": health.get("version"),
        "service": health.get("service"),
        "provider": {"provider": provider.get("provider"), "model": provider.get("model"),
                     "reachable": provider.get("reachable")},
        "prod": health.get("prod"),
        "crypto_enabled": health.get("crypto_enabled"),
        "self_attack": health.get("self_attack"),
        "scanner_pubkey": (health.get("scanner_pubkey") or "")[:24],
        # The visible proof of the "someone else pays" property: MOMUS never holds the payout key.
        "holds_treasury_key": bool(health.get("holds_treasury_key")),
        "targets": health.get("targets") or [],
        "findings": findings,
        "finding_counts": counts,
        "intel": status.get("intel") or {},
        # Settlement tier: UNI simulation by default — the loop runs, no value moves. Real on-chain
        # payout needs its OWN opt-in beyond the crypto master switch, so the panel shows which.
        "settlement": health.get("settlement") or {},
        # MOMUS's persistent vulnerability corpus (SQLite/Postgres): totals + recurring bugs.
        "corpus": health.get("corpus") or {},
    }


def apply_momus_to_nodes(nodes: list[dict], status: dict[str, Any] | None, *,
                         public_url: str | None = None) -> None:
    node = next((n for n in nodes if n.get("id") == "momus"), None)
    if not node:
        return
    node["url"] = public_url or momus_public_url()
    node["links"] = momus_links()
    if not status:
        node["status"] = "offline"
        node.pop("momus_live", None)
        node["metrics"] = {"findings": 0, "targets": 0, "probes": 0}
        return
    payload = _live_payload(status)
    total_findings = sum(payload["finding_counts"].values())
    node["status"] = "active" if (status.get("health", {}).get("status") == "ok") else "idle"
    node["momus_live"] = payload
    node["metrics"] = {
        "findings": total_findings,
        "targets": len(payload["targets"]),
        "learned": payload["intel"].get("learned_pairs", 0),
    }


def apply_momus_graph(nodes: list[dict], *, mode: str = "real") -> None:
    _ = mode
    status = fetch_momus_status_sync()
    apply_momus_to_nodes(nodes, status, public_url=momus_public_url())
