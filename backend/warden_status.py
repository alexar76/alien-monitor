"""Poll the WARDEN threat-feed surface for the Alien Monitor ``warden`` node.

WARDEN is a LIBRARY, not a service: `@aimarket/warden` runs in-process inside whatever MCP host
loads it, so unlike every other node on this map it has no host of its own to poll, no port and no
``/health``. Drawing it anyway is the point — it is the invoke-time gate the whole security story
rests on, and leaving it off the map is what made the assistant answer "where is WARDEN?" with
"inside ARGUS", as though the firewall were a feature of one agent.

So the node is a LAYER, and its telemetry is the two ends of the layer that DO have addresses:

* **MOMUS** publishes the signed threat feed WARDEN consumes — ``GET /warden/threat-feed`` and
  ``/warden/threat-feed/summary`` on the MOMUS host. That gives the record count, what the publisher
  refused to publish and why, the pinned Ed25519 key, and the signed timestamp whose age decides
  whether a consuming WARDEN accepts the document at all.
* **ARGUS** is the reference host, so enforcement shows up as ARGUS telemetry (the ``warden`` beats
  in the verifiable-run feed).

What this module must NOT do is claim more than it checked. It reports that the document carries a
signature; it does not verify it — verification happens inside the consuming host, over RFC 8785
canonical bytes, against a key the operator pinned in advance. Saying "signature valid" here would
be exactly the phantom-oracle mistake WARDEN itself had removed from its gate chain.

Best-effort and offline-safe: if MOMUS is unreachable the node reports the built-in floor and says
the feed is unavailable, which is what a WARDEN install does in the same situation.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
from poll_cache import ttl_cached

DEFAULT_WARDEN_GITHUB_URL = "https://github.com/alexar76/warden"
DEFAULT_WARDEN_LANDING_URL = "https://warden.modelmarket.dev"
DEFAULT_WARDEN_NPM_URL = "https://www.npmjs.com/package/@aimarket/warden"

#: WARDEN refuses a signed feed whose timestamp is older than this. Mirrors
#: DEFAULT_FEED_MAX_AGE_MS in the package — a feed nobody would accept must not be
#: drawn here as if it were in force.
FEED_MAX_AGE_MS = 24 * 60 * 60 * 1000

#: Records WARDEN enforces with no feed at all (the BUILTIN table in the package).
#: Stated as the floor, never as "what is live": the floor is what remains when
#: every remote read fails.
BUILTIN_FLOOR = 11

#: Ruleset the static scanner runs.
#:
#: A MIRROR of STATIC_SCAN_RULESET_VERSION in @aimarket/warden — the monitor cannot import
#: TypeScript, so this constant is the price of showing the version at all. It went stale within
#: hours the first time (the package shipped v4 while this still said v3), so
#: tests/test_warden_ruleset_mirror.py reads the package source in the monorepo and fails when the
#: two disagree. Bump both together.
RULESET_VERSION = "4"


def warden_feed_base() -> str:
    """The host that publishes the feed. MOMUS today; an env var, not a hard-coded truth."""
    from momus_status import momus_poll_url

    return (os.environ.get("ALIEN_WARDEN_FEED_URL") or momus_poll_url()).rstrip("/")


def warden_public_url() -> str:
    """The WARDEN landing — the card CTA. npm stays a secondary link, not the exit."""
    return (os.environ.get("ALIEN_WARDEN_LANDING_URL") or DEFAULT_WARDEN_LANDING_URL).rstrip("/")


def warden_links() -> dict[str, str]:
    github = (os.environ.get("ALIEN_WARDEN_GITHUB_URL") or DEFAULT_WARDEN_GITHUB_URL).rstrip("/")
    landing = warden_public_url()
    return {
        "landing": landing,
        "github": github,
        "npm": DEFAULT_WARDEN_NPM_URL,
        "docs": f"{github}/blob/main/docs/gates.md",
    }


def _short_key(spki_hex: Any) -> str | None:
    if not isinstance(spki_hex, str) or len(spki_hex) < 16:
        return None
    return f"{spki_hex[:8]}…{spki_hex[-8:]}"


@ttl_cached(env_var="ALIEN_WARDEN_CACHE_TTL")
def fetch_warden_status_sync(*, base_url: str | None = None, timeout: float = 4.0) -> dict[str, Any] | None:
    """Return the feed-side facts, or ``None`` when the publisher is unreachable."""
    root = (base_url or warden_feed_base()).rstrip("/")
    try:
        with httpx.Client(timeout=timeout) as client:
            doc = client.get(f"{root}/warden/threat-feed")
            if doc.status_code != 200:
                return None
            body = doc.json()
            if not isinstance(body, dict):
                return None
            summary: dict[str, Any] = {}
            try:
                s = client.get(f"{root}/warden/threat-feed/summary")
                if s.status_code == 200 and isinstance(s.json(), dict):
                    summary = s.json()
            except Exception:
                summary = {}
    except Exception:
        return None

    records = body.get("records")
    timestamp = body.get("timestamp")
    signed = isinstance(body.get("signature"), str) and len(str(body.get("signature"))) >= 64
    age_ms: int | None = None
    if isinstance(timestamp, (int, float)):
        age_ms = max(0, int(time.time() * 1000) - int(timestamp))

    refusals = summary.get("refusals")
    first_refusal = None
    if isinstance(refusals, list) and refusals:
        first = refusals[0]
        if isinstance(first, str):
            first_refusal = first[:240]

    return {
        "feed_url": f"{root}/warden/threat-feed",
        "records": len(records) if isinstance(records, list) else 0,
        "refused": int(summary.get("refused") or 0),
        "first_refusal": first_refusal,
        "signed": signed,
        "age_ms": age_ms,
        # A consuming WARDEN would reject the document past the window, so the map
        # must not draw a stale feed as if it were in force.
        "accepted_by_freshness": bool(age_ms is not None and age_ms <= FEED_MAX_AGE_MS),
        "publisher_key": _short_key(summary.get("feed_public_key_spki_hex")),
        "builtin_floor": BUILTIN_FLOOR,
        "ruleset_version": RULESET_VERSION,
        # Named so a reader knows verification is the HOST's job, not ours.
        "verified_by": "the consuming host, over RFC 8785 bytes against a pre-pinned key",
    }


def apply_warden_to_nodes(nodes: list[dict], status: dict[str, Any] | None) -> None:
    node = next((n for n in nodes if n.get("id") == "warden"), None)
    if not node:
        return
    node["links"] = warden_links()
    node["url"] = warden_public_url()
    if not status:
        # The floor is the honest number when the publisher cannot be reached: a
        # WARDEN install in the same position keeps enforcing exactly these.
        node["status"] = "idle"
        node["warden_live"] = {
            "feed": "unreachable",
            "builtin_floor": BUILTIN_FLOOR,
            "ruleset_version": RULESET_VERSION,
        }
        node["metrics"] = {"feed_records": 0, "builtin_floor": BUILTIN_FLOOR, "gates": 4}
        return
    node["status"] = "active" if status.get("accepted_by_freshness") else "idle"
    node["warden_live"] = status
    node["metrics"] = {
        "feed_records": int(status.get("records") or 0),
        "builtin_floor": BUILTIN_FLOOR,
        "gates": 4,
    }


def apply_warden_graph(nodes: list[dict], *, mode: str = "real") -> None:
    _ = mode
    apply_warden_to_nodes(nodes, fetch_warden_status_sync())
