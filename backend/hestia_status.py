"""HESTIA — poll the hearth for the monitor node.

The agent's write path is a paid ``POST /invoke`` (deploy / stop / status of one
slug), so this poller never touches it: a monitor that spends money to draw a
node would bill the operator for every tick. What is left is genuinely
observable —

  * ``/health``    — identity: version, runtime, ledger tenant count
  * ``/v1/hearth`` — public roster of tenants this hearth is actually running, with the
                     SHA-256 of each one's handler (``handler_sha256``)
  * ``/agents/catalog.json`` — the operator's published agent sources and their digests,
                     read every few minutes, so the card can say whose running code matches

None of these is a Hub listing. An empty roster means nothing is hosted here,
not that the market is empty. Isolation first; Hub stays the catalogue.
"""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

from poll_cache import ttl_cached

DEFAULT_HESTIA_URL = "https://hestia.modelmarket.dev"
DEFAULT_GITHUB_URL = "https://github.com/alexar76/hestia"
DEFAULT_PAGES_URL = "https://alexar76.github.io/hestia/"

ROSTER_LIMIT = 256  # the hearth's own cap (HESTIA_MAX_TENANTS on the reference hearth)
CATALOGUE_PATH = "/agents/"
_SHA256 = re.compile(r"[0-9a-f]{64}")


def hestia_url() -> str:
    """Where the hearth answers. Host-local first when the monitor runs beside it."""
    return (
        os.environ.get("ALIEN_HESTIA_URL")
        or os.environ.get("HESTIA_URL")
        or DEFAULT_HESTIA_URL
    ).rstrip("/")


def hestia_public_url() -> str:
    """What a browser should open — may differ from the polled address."""
    return (
        os.environ.get("ALIEN_PUBLIC_HESTIA_URL")
        or os.environ.get("HESTIA_PUBLIC_URL")
        or hestia_url()
    ).rstrip("/")


def hestia_links() -> dict[str, str]:
    github = (os.environ.get("ALIEN_HESTIA_GITHUB_URL") or DEFAULT_GITHUB_URL).rstrip("/")
    public = hestia_public_url()
    return {
        "console": f"{public}/ui/",
        "landing": public,
        # What the operator's agents are and the exact code they run (HESTIA serves it).
        "catalogue": f"{public}{CATALOGUE_PATH}",
        "github": github,
        "pages": DEFAULT_PAGES_URL,
    }


def _health_facts(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {
        "ok": bool(raw.get("ok")),
        "service": str(raw.get("service") or ""),
        "version": str(raw.get("version") or ""),
        "runtime": str(raw.get("runtime") or ""),
        "tenants": int(raw.get("tenants") or 0),
    }


def _owner_of(row: dict[str, Any]) -> dict[str, str]:
    """Whose agent a roster row is (HESTIA's /v1/hearth names it since 2026-10-04): the hearth
    operator's own, or an admitted owner's by the label the operator gave it. {} when unsaid."""
    owner = row.get("owner") if isinstance(row.get("owner"), dict) else {}
    kind = str(owner.get("kind") or "")
    if kind == "operator":
        return {"kind": "operator"}
    if kind == "owner":
        return {"kind": "owner", "label": str(owner.get("label") or "")[:80]}
    return {}


def _digest(value: Any) -> str:
    """A SHA-256 in lowercase hex, or "" — anything else from the roster is not carried."""
    return value if isinstance(value, str) and _SHA256.fullmatch(value) else ""


def _published_digests(raw: Any) -> dict[str, str]:
    """slug -> handler SHA-256 from the hearth's /agents/catalog.json; {} when unreadable."""
    agents = raw.get("agents") if isinstance(raw, dict) else None
    out: dict[str, str] = {}
    for agent in agents if isinstance(agents, list) else []:
        if isinstance(agent, dict) and isinstance(agent.get("slug"), str):
            digest = _digest(agent.get("handler_sha256"))
            if digest and len(out) < ROSTER_LIMIT:
                out[agent["slug"][:120]] = digest
    return out


def _code_state(row: dict[str, Any], published: dict[str, str] | None) -> str:
    """'published': the running handler is byte for byte the one in the catalogue;
    'differs': the catalogue has this agent but the hearth runs other code; '' otherwise
    (not in the catalogue, no digest on the roster, or the catalogue was not read)."""
    if not published:
        return ""
    slug, running = str(row.get("slug") or ""), _digest(row.get("handler_sha256"))
    if slug not in published or not running:
        return ""
    return "published" if published[slug] == running else "differs"


def _hearth_facts(raw: Any, published: dict[str, str] | None = None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    rows = raw.get("tenants")
    safe: list[dict[str, Any]] = []
    ours = third_party = 0
    matching = 0
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            owner = _owner_of(row)
            ours += owner.get("kind") == "operator"
            third_party += owner.get("kind") == "owner"
            code = _code_state(row, published)
            matching += code == "published"
            if len(safe) < ROSTER_LIMIT:
                item = {
                    "slug": str(row.get("slug") or ""),
                    "status": str(row.get("status") or ""),
                    "capability_id": str(row.get("capability_id") or ""),
                    "name": str(row.get("name") or ""),
                    "public_url": str(row.get("public_url") or ""),
                    "owner": owner,
                }
                digest = _digest(row.get("handler_sha256"))
                if digest:
                    item["handler_sha256"] = digest
                if code:
                    item["code"] = code
                safe.append(item)
    facts: dict[str, Any] = {
        "hearth": str(raw.get("hearth") or ""),
        "tenants": safe,
        # The roster lists RUNNING agents only; a stopped one (the hearth's /health counts it)
        # is not hosted. The old per-row "announced" flag is gone: it said "not a Hub listing"
        # for agents the hub lists — it indexes the hearth by crawling it, announced or not.
        "roster_size": len(rows) if isinstance(rows, list) else len(safe),
    }
    if ours or third_party:
        facts["ours"], facts["third_party"] = ours, third_party
    if published:
        # How many running agents run exactly the source the catalogue publishes.
        facts["published"], facts["published_matching"] = len(published), matching
    return facts


@ttl_cached(ttl_s=600.0, env_var="ALIEN_HESTIA_CATALOGUE_TTL_S")
def fetch_published_digests_sync() -> dict[str, str]:
    """The catalogue changes with a deploy, not with every tick: read it every ten minutes."""
    try:
        with httpx.Client(timeout=4.0) as client:
            resp = client.get(f"{hestia_url()}{CATALOGUE_PATH}catalog.json")
            if resp.status_code == 200:
                return _published_digests(resp.json())
    except Exception:
        pass
    return {}


@ttl_cached(ttl_s=25.0, env_var="ALIEN_HESTIA_TTL_S")
def fetch_hestia_status_sync() -> dict[str, Any] | None:
    """Read health and the public roster. A partial read is still worth drawing."""
    base = hestia_url()
    health: dict[str, Any] = {}
    hearth: dict[str, Any] = {}

    try:
        with httpx.Client(timeout=4.0) as client:
            try:
                resp = client.get(f"{base}/health")
                if resp.status_code == 200:
                    health = _health_facts(resp.json())
            except Exception:
                pass
            if not health:
                return None
            try:
                resp = client.get(f"{base}/v1/hearth")
                if resp.status_code == 200:
                    hearth = _hearth_facts(resp.json(), fetch_published_digests_sync())
            except Exception:
                pass
    except Exception:
        return None

    return {"health": health, "hearth": hearth}


def apply_hestia_to_nodes(
    nodes: list[dict[str, Any]], status: dict[str, Any] | None, *, public_url: str | None = None
) -> None:
    node = next((item for item in nodes if item.get("id") == "hestia"), None)
    if node is None:
        return
    # Deep-links outlive a failed poll — an offline node still has a console to open.
    node["url"] = public_url or hestia_public_url()
    node["links"] = hestia_links()

    if not status:
        node["status"] = "offline"
        node.pop("hestia_live", None)
        node["metrics"] = {"tenants": 0}
        return

    health = status.get("health") or {}
    hearth = status.get("hearth") or {}
    roster = hearth.get("tenants") if isinstance(hearth.get("tenants"), list) else []
    tenant_count = int(hearth.get("roster_size") or health.get("tenants") or 0)

    if not health.get("ok"):
        node["status"] = "error"
    elif tenant_count:
        # "active" means the hearth is actually hosting someone. A reachable
        # box with an empty roster is idle — empty roster ≠ empty market.
        node["status"] = "active"
    else:
        node["status"] = "idle"

    node["metrics"] = {"tenants": tenant_count}
    if "ours" in hearth:
        # Our own agents against other companies' (HESTIA owners): the split the hearth publishes.
        node["metrics"].update(ours=int(hearth["ours"]), third_party=int(hearth["third_party"]))
    node["hestia_live"] = {
        "console_url": hestia_links()["console"],
        "catalogue_url": hestia_links()["catalogue"],
        "version": health.get("version") or None,
        "runtime": health.get("runtime") or None,
        "service": health.get("service") or None,
        "hearth": hearth.get("hearth") or None,
        "not": ["Hub", "Factory", "THEMIS", "job board"],
        "tenants": roster,
    }
    if "published" in hearth:
        node["hestia_live"]["published"] = int(hearth["published"])
        node["hestia_live"]["published_matching"] = int(hearth["published_matching"])


def apply_hestia_graph(nodes: list[dict[str, Any]], *, mode: str = "real") -> None:
    _ = mode
    apply_hestia_to_nodes(nodes, fetch_hestia_status_sync())
