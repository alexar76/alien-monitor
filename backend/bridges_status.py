"""Poll an ``aimarket-bridges`` telemetry endpoint for the Alien Monitor ``bridges`` node.

aimarket-bridges is the third PAID INVOKE CHANNEL, next to the hub and the mesh: it hands
AIMarket capabilities to LangChain/LangGraph, CrewAI and AutoGen agents as native tools, each
call returning a signed receipt and each toolbox carrying a hard ``budget_usd`` ceiling. So the
question a viewer brings to this node is "how much is billed through it".

**Today that question has no answer, and this module says so rather than inventing one.**

aimarket-bridges is a *client-side library* — a pip package that runs inside the buyer's own
agent process. It has no ASGI app, no console script, no container, no vhost; the monorepo
folder is a library and its tests (checked 2026-08-09). Its spend counter (``HubClient._spent``)
and its receipt verification live and die with that process, and no aggregate ever reaches us.
There is nothing to poll, so there is nothing to show.

That makes this module unusual on purpose, and it obeys three rules the rest of the monitor
also obeys:

* **offline is offline.** No endpoint → no network call, no figures, ``status: offline``.
* **zero and absent are different.** ``metrics`` is ``{}``, never ``{"paid_invokes": 0, ...}``.
  A zero would claim we asked and the answer was none; the truth is that nobody counts. This is
  the same defect class as calling an unreachable probe target a pass
  (``momus/docs/found-and-fixed.md``), and it is the reason the offline branch here deliberately
  does NOT copy the neighbouring pollers, which reset their metrics to zeros.
* **simulated is labelled.** Any money figure is rendered next to its settlement mode, and an
  undeclared settlement is treated as SIMULATED, because that is the direction in which a wrong
  guess is harmless.

The endpoint this module already speaks is the one the bridges package would need to grow — it
is wired first so that shipping the counter is a bridges-side change only:

    GET {telemetry}/health   -> {"status": "ok", "service": "aimarket-bridges", "version": ...}
    GET {telemetry}/metrics  -> every field OPTIONAL; an absent field is reported as UNMEASURED,
                                never as 0:
        tools_exported      int    tools actually handed to a framework (post schema filter)
        paid_invokes        int    calls that were billed
        receipts_issued     int    signed receipts returned
        receipts_verified   int    of those, verified against the ORIGIN key
        budget_rejections   int    calls refused by the budget_usd ceiling
        spend_usd           float  billed total — only rendered beside `settlement`
        settlement          obj    {"mode": "uni"|"base"|..., "moves_real_value": bool}
        window              str    what the counters cover ("since-process-start", "24h", ...)

Point the monitor at it with ``ALIEN_BRIDGES_URL`` (or ``BRIDGES_URL``). Unset — the state today
— means this module makes no request at all.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from poll_cache import ttl_cached

# There is no bridges service host, and none is guessed here. A default hostname would turn
# "this channel is not instrumented" into "this channel is down", which is a different and
# false statement — the panel would blame the network for an endpoint that was never written.
DEFAULT_BRIDGES_URL = ""

# The docs page for the package (same host as the public ecosystem landing) and its sources.
DEFAULT_PUBLIC_BRIDGES_URL = "https://modeldev.modelmarket.dev/bridges/"
DEFAULT_BRIDGES_GITHUB_URL = "https://github.com/alexar76/aimarket-bridges"
DEFAULT_BRIDGES_PYPI_URL = "https://pypi.org/project/aimarket-bridges/"

PACKAGE_NAME = "aimarket-bridges"

# The three adapters the package actually ships (aimarket_bridges/{langchain,crewai,autogen}.py).
# Descriptive, not measured — deliberately kept out of ``metrics`` so it can never be read as
# traffic.
FRAMEWORKS = ("LangChain / LangGraph", "CrewAI", "AutoGen")

# The counters that answer "how much is billed through it". Named once, so the parser and the
# "what is missing" list cannot drift apart — a followup that lists a field the reader never
# renders is how a gap gets quietly closed on paper only.
BILLED_COUNTERS = (
    "tools_exported",
    "paid_invokes",
    "receipts_issued",
    "receipts_verified",
    "budget_rejections",
)

# Reasons a node carries no figures. They are NOT interchangeable: "we never asked" and "we
# asked and got nothing back" are different facts about the world, and the panel prints which.
REASON_NO_ENDPOINT = "no-telemetry-endpoint"
REASON_UNREACHABLE = "unreachable"
REASON_NO_COUNTERS = "no-counters"


def bridges_poll_url() -> str:
    """Telemetry endpoint, or ``""`` when none is configured (the state today)."""
    return (
        os.environ.get("ALIEN_BRIDGES_URL")
        or os.environ.get("BRIDGES_URL")
        or DEFAULT_BRIDGES_URL
    ).rstrip("/")


def bridges_public_url() -> str:
    return (
        os.environ.get("ALIEN_PUBLIC_BRIDGES_URL")
        or os.environ.get("BRIDGES_PUBLIC_URL")
        or DEFAULT_PUBLIC_BRIDGES_URL
    ).rstrip("/")


def bridges_links() -> dict[str, str]:
    github = (
        os.environ.get("ALIEN_BRIDGES_GITHUB_URL")
        or os.environ.get("BRIDGES_GITHUB_URL")
        or DEFAULT_BRIDGES_GITHUB_URL
    ).rstrip("/")
    pypi = (
        os.environ.get("ALIEN_BRIDGES_PYPI_URL")
        or os.environ.get("BRIDGES_PYPI_URL")
        or DEFAULT_BRIDGES_PYPI_URL
    ).rstrip("/")
    return {
        "landing": bridges_public_url(),
        "github": github,
        "docs": f"{github}#readme",
        "pypi": pypi,
    }


# ── parsing ───────────────────────────────────────────────────────────────────


def _count(raw: Any) -> int | None:
    """A non-negative integer count, or ``None`` when the field is not a usable measurement.

    ``None`` propagates all the way to the panel as "unmeasured". Returning 0 for a missing or
    malformed field is the exact lie this module exists to avoid, so every rejection path here
    returns ``None``.
    """
    if raw is None or isinstance(raw, bool):  # bool is an int in Python; a flag is not a count
        return None
    if isinstance(raw, int):
        return raw if raw >= 0 else None
    if isinstance(raw, float):
        # Accept a float that is exactly an integer (JSON encoders emit 3.0 for 3).
        return int(raw) if raw >= 0 and float(raw).is_integer() else None
    return None


def _money(raw: Any) -> float | None:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
        return value if value >= 0 else None
    return None


def _settlement(raw: Any) -> dict[str, Any]:
    """Normalise the settlement declaration that must accompany any money figure.

    An undeclared settlement resolves to SIMULATED. UNI settlement moves no value, and a balance
    shown without that word invites somebody to believe money moved — so the default points at
    the harmless reading, and ``declared`` records that we are defaulting rather than reporting.
    """
    if not isinstance(raw, dict):
        return {"mode": None, "moves_real_value": False, "simulated": True, "declared": False}
    moves = bool(raw.get("moves_real_value"))
    mode = raw.get("mode")
    return {
        "mode": (str(mode).lower() if mode else None),
        "moves_real_value": moves,
        "simulated": not moves,
        "declared": True,
    }


def _split_counters(raw: Any) -> tuple[dict[str, int], list[str]]:
    """Return (measured counters, names of the ones the payload did not measure)."""
    body = raw if isinstance(raw, dict) else {}
    measured: dict[str, int] = {}
    unmeasured: list[str] = []
    for name in BILLED_COUNTERS:
        value = _count(body.get(name))
        if value is None:
            unmeasured.append(name)
        else:
            measured[name] = value
    return measured, unmeasured


@ttl_cached(env_var="ALIEN_BRIDGES_CACHE_TTL")
def fetch_bridges_status_sync(
    *, base_url: str | None = None, timeout: float = 4.0
) -> dict[str, Any] | None:
    """Return ``{"health": ..., "metrics": ...}``, or ``None`` when there is nothing to read.

    ``None`` covers both "no endpoint is configured" (no request is made — there is no host to
    fail against) and "configured but did not answer". ``apply_bridges_to_nodes`` tells the two
    apart from the configuration itself and labels the node accordingly.
    """
    root = (base_url if base_url is not None else bridges_poll_url()).rstrip("/")
    if not root:
        return None
    try:
        with httpx.Client(timeout=timeout) as client:
            h = client.get(f"{root}/health")
            if h.status_code != 200:
                return None
            health = h.json()
            if not isinstance(health, dict):
                return None
            metrics: dict[str, Any] = {}
            try:
                r = client.get(f"{root}/metrics")
                if r.status_code == 200 and isinstance(r.json(), dict):
                    metrics = r.json()
            except Exception:
                # Health alone proves the endpoint is up; it does not produce a single figure,
                # so the node lands in the `no-counters` state rather than inventing any.
                metrics = {}
            return {"health": health, "metrics": metrics}
    except Exception:
        return None


def _live_payload(status: dict[str, Any], *, telemetry_url: str) -> dict[str, Any]:
    health = status.get("health") or {}
    raw_metrics = status.get("metrics") or {}
    counters, unmeasured = _split_counters(raw_metrics)
    spend = _money(raw_metrics.get("spend_usd"))
    return {
        "instrumented": bool(counters),
        "reason": None if counters else REASON_NO_COUNTERS,
        "package": PACKAGE_NAME,
        "frameworks": list(FRAMEWORKS),
        "version": health.get("version"),
        "service": health.get("service"),
        "telemetry_url": telemetry_url or None,
        "counters": counters,
        "unmeasured": unmeasured,
        # Money is kept OUT of ``metrics``: the node's metric readout has nowhere to print the
        # settlement mode, and an amount without that word is the misreading this panel must not
        # produce. The detail panel renders the two together or neither.
        "spend_usd": spend,
        "settlement": _settlement(raw_metrics.get("settlement")),
        "window": (str(raw_metrics.get("window")) if raw_metrics.get("window") else None),
    }


def _uninstrumented_payload(reason: str, *, telemetry_url: str = "") -> dict[str, Any]:
    """The honest empty state: what we would show, and why we are not showing it."""
    return {
        "instrumented": False,
        "reason": reason,
        "package": PACKAGE_NAME,
        "frameworks": list(FRAMEWORKS),
        "version": None,
        "service": None,
        "telemetry_url": telemetry_url or None,
        "counters": {},
        "unmeasured": list(BILLED_COUNTERS),
        "spend_usd": None,
        "settlement": _settlement(None),
        "window": None,
    }


def apply_bridges_to_nodes(
    nodes: list[dict],
    status: dict[str, Any] | None,
    *,
    public_url: str | None = None,
    telemetry_url: str | None = None,
) -> None:
    """Merge a bridges telemetry read into the singleton ``bridges`` graph node.

    DECORATES ONLY. A missing node returns early and silently, exactly like its neighbours —
    which is why the node itself must be registered in ``build_topology()`` AND seeded in
    ``universe.py``; decorating a node that was never created is how MOMUS came to be invisible
    in one mode while looking wired in the diff.
    """
    node = next((n for n in nodes if n.get("id") == "bridges"), None)
    if not node:
        return

    poll = (telemetry_url if telemetry_url is not None else bridges_poll_url()).rstrip("/")
    node["url"] = public_url or bridges_public_url()
    node["links"] = bridges_links()

    if not status:
        node["status"] = "offline"
        # ``{}`` and not zeros. A billed channel reporting "paid_invokes: 0" would state that we
        # measured no traffic; what is true is that nothing measures it.
        node["metrics"] = {}
        node["bridges_live"] = _uninstrumented_payload(
            REASON_UNREACHABLE if poll else REASON_NO_ENDPOINT, telemetry_url=poll
        )
        return

    payload = _live_payload(status, telemetry_url=poll)
    node["bridges_live"] = payload
    node["metrics"] = dict(payload["counters"])
    # Reaching the endpoint proves something is running even when it counts nothing, so that
    # case is `idle` rather than `offline` — again, a distinction the viewer is entitled to.
    node["status"] = "active" if payload["counters"] else "idle"


def apply_bridges_graph(nodes: list[dict], *, mode: str = "real") -> None:
    """Read bridges telemetry for the active monitor mode (a no-op read when unconfigured)."""
    _ = mode
    status = fetch_bridges_status_sync()
    apply_bridges_to_nodes(nodes, status, public_url=bridges_public_url())


# ── TEST mode ─────────────────────────────────────────────────────────────────


def fill_bridges_sim_node(node: dict) -> None:
    """TEST mode: still no figures.

    Every other node fabricates plausible activity here, and this one refuses to. TEST is a
    simulation of a running ecosystem, not a licence to invent a turnover for a channel that has
    no counter anywhere in it — a screenshot showing "$412 billed through bridges" would be read
    as a measurement by everyone who ever saw it. There is nothing to simulate, so nothing is.
    """
    node["url"] = bridges_public_url()
    node["links"] = bridges_links()
    node["status"] = "offline"
    node["metrics"] = {}
    node["bridges_live"] = _uninstrumented_payload(REASON_NO_ENDPOINT)
