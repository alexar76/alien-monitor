"""DOLOS node status for the Alien Monitor — the dynamic EVM red-team, next to BASANOS.

DOLOS is a CLI harness, not a daemon: it has no `/health` to poll. So this reader does NOT dial a
service — it reads the artifact DOLOS writes after a scan (`data/dolos/last_scan.json`, or
`DOLOS_LAST_SCAN_PATH`) and reports what the last run FOUND. With no artifact the node is `idle`
with its static identity, never a fake verdict — a red-team node that implies a result it never
produced is worse than one that says "not run yet".

Deliberately dependency-free (no web3, no foundry, no dolos package): the monitor backend imports
this cleanly, and the harness that produces the artifact runs elsewhere.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_GITHUB_URL = "https://github.com/alexar76/dolos"
DEFAULT_PAGES_URL = "https://alexar76.github.io/dolos/"

# The catalog as of writing — a static fallback for the node's "attacks" metric when no scan
# artifact exists yet. The artifact, when present, is authoritative.
_STATIC_CATALOG = ("unauthorized_token_mint", "escrow_channel_hijack", "lottery_operator_bypass")


def dolos_public_url() -> str:
    return (os.environ.get("ALIEN_PUBLIC_DOLOS_URL") or os.environ.get("DOLOS_PUBLIC_URL")
            or DEFAULT_PAGES_URL).rstrip("/")


def dolos_links() -> dict[str, str]:
    github = (os.environ.get("ALIEN_DOLOS_GITHUB_URL") or DEFAULT_GITHUB_URL).rstrip("/")
    return {"landing": dolos_public_url(), "github": github, "pages": DEFAULT_PAGES_URL}


def _last_scan_path() -> Path:
    override = (os.environ.get("DOLOS_LAST_SCAN_PATH") or "").strip()
    if override:
        return Path(override)
    for cand in ("/app/data/universe/dolos_last_scan.json",  # mounted in the UNI monitor container
                 "/app/data/dolos/last_scan.json",
                 str(Path(__file__).resolve().parents[2] / "data" / "dolos" / "last_scan.json"),
                 str(Path(__file__).resolve().parents[2] / "dolos" / "data" / "last_scan.json")):
        if Path(cand).is_file():
            return Path(cand)
    return Path("/app/data/dolos/last_scan.json")


def fetch_dolos_status_sync() -> dict[str, Any]:
    """The last scan's facts, or a static-identity stub when nothing has run."""
    path = _last_scan_path()
    try:
        doc = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        doc = {}
    if not doc:
        return {"ran": False, "attacks": len(_STATIC_CATALOG)}
    findings = doc.get("findings") or []
    # A real, non-by-design, non-advisory exploit is what turns the node red.
    real_exploits = [
        f for f in findings
        if f.get("outcome") == "finding"
        and "[BY DESIGN" not in str(f.get("detail") or "")
        and "[ADVISORY" not in str(f.get("detail") or "")
    ]
    return {
        "ran": True,
        "attacks": int(doc.get("ran") or len(_STATIC_CATALOG)),
        "exploited": int(doc.get("exploited") or 0),
        "held": int(doc.get("held") or 0),
        "inconclusive": int(doc.get("inconclusive") or 0),
        "real_exploits": len(real_exploits),
        "chain_id": doc.get("chain_id"),
        "sandbox": bool(doc.get("sandbox")),
        "fork_block": doc.get("fork_block"),
        "scanned_at": doc.get("scanned_at") or doc.get("created_at") or "",
    }


def apply_dolos_to_nodes(nodes: list[dict[str, Any]], status: dict[str, Any]) -> None:
    for node in nodes:
        if node.get("id") != "dolos":
            continue
        metrics = dict(node.get("metrics") or {})
        metrics["attacks"] = status.get("attacks", len(_STATIC_CATALOG))
        if status.get("ran"):
            metrics.update({
                "exploited": status.get("exploited", 0),
                "held": status.get("held", 0),
                "real_exploits": status.get("real_exploits", 0),
            })
        node["metrics"] = metrics
        node["dolos_live"] = bool(status.get("ran"))
        node["dolos_last_scan"] = status
        # Red only for a real, sandbox, non-by-design exploit; green when the contracts held;
        # amber idle before the first run.
        if not status.get("ran"):
            node["status"] = "idle"
        elif status.get("real_exploits", 0) > 0:
            node["status"] = "alert"
        else:
            node["status"] = "active"
        return


def apply_dolos_graph(nodes: list[dict[str, Any]], *, mode: str = "real") -> None:
    _ = mode
    apply_dolos_to_nodes(nodes, fetch_dolos_status_sync())
