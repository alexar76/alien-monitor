"""HEPHAESTUS — poll real pipeline runs and catalogue readiness for the monitor node.

The monitor could draw a topology of services that had, as far as anything observable
went, never traded with each other: the pipeline executor signs a bill of materials per
run and, until the read routes existed, nothing could fetch one back. So this node answers
the two questions the map could not:

  * what actually ran — cost, hops, and which hop is to blame when a run failed
  * what could run at all — how much of the catalogue is priced, composable and observed

The second is a diagnostic, not decoration. A capability that declares no input fields or
no output schema is discoverable and priced but cannot be wired into anything, and a list
of rows hides that where a readiness count does not.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from poll_cache import ttl_cached

DEFAULT_FACTORY_URL = "http://127.0.0.1:9080"
DEFAULT_HUB_URL = "http://127.0.0.1:9083"
DEFAULT_STUDIO_URL = "https://modelmarket.dev/studio"
DEFAULT_GITHUB_URL = "https://github.com/alexar76/aicom"

# Enough rows for the panel's feed; the route itself clamps at 200.
TRACE_LIMIT = 12


def hephaestus_factory_url() -> str:
    """Where the pipeline executor and its trace store live."""
    return (
        os.environ.get("ALIEN_HEPHAESTUS_FACTORY_URL")
        or os.environ.get("AIFACTORY_URL")
        or DEFAULT_FACTORY_URL
    ).rstrip("/")


def hephaestus_hub_url() -> str:
    """Where the signed capability manifest lives."""
    return (
        os.environ.get("ALIEN_HEPHAESTUS_HUB_URL")
        or os.environ.get("ALIEN_HUB_URL")
        or DEFAULT_HUB_URL
    ).rstrip("/")


def hephaestus_public_url() -> str:
    return (
        os.environ.get("ALIEN_PUBLIC_HEPHAESTUS_URL")
        or os.environ.get("HEPHAESTUS_PUBLIC_URL")
        or DEFAULT_STUDIO_URL
    ).rstrip("/")


def hephaestus_links() -> dict[str, str]:
    github = (
        os.environ.get("ALIEN_HEPHAESTUS_GITHUB_URL") or DEFAULT_GITHUB_URL
    ).rstrip("/")
    return {
        "studio": hephaestus_public_url(),
        "github": github,
        "docs": f"{github}/blob/main/docs/hephaestus-studio.md",
    }


def _catalogue_readiness(manifest: Any) -> dict[str, Any]:
    """Count what the catalogue can actually be built with.

    ``composable`` is the strict reading: an input schema that declares a ``properties``
    object (even an empty one — "takes nothing" is an answer) AND a non-empty output
    schema. A row failing either cannot be connected to a neighbour.
    """
    if not isinstance(manifest, dict):
        return {}
    tools = manifest.get("tools")
    if not isinstance(tools, list):
        return {}

    total = priced = composable = measured = 0
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        total += 1
        price = tool.get("price_per_call_usd")
        if isinstance(price, (int, float)) and price > 0:
            priced += 1
        input_schema = tool.get("input_schema")
        output_schema = tool.get("output_schema")
        if isinstance(input_schema, dict) and isinstance(input_schema.get("properties"), dict) \
                and isinstance(output_schema, dict) and output_schema:
            composable += 1
        # Trust the hub's own honesty marker rather than re-deriving it: a rate with no
        # observations behind it is a placeholder, and only the hub knows which is which.
        if tool.get("reputation_basis") == "measured":
            measured += 1

    by_hub = manifest.get("by_hub")
    return {
        "capabilities": total,
        "priced": priced,
        "composable": composable,
        "measured": measured,
        "hubs": len(by_hub) if isinstance(by_hub, dict) else 0,
        "generated_at": manifest.get("generated_at"),
        "signed": isinstance(manifest.get("signature"), dict),
    }


def _sanitize_traces(raw: Any) -> list[dict[str, Any]]:
    """Keep only the projection's fields, and only in the shapes the panel can render."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        steps = [s for s in (row.get("steps") or []) if isinstance(s, dict)]
        blame = row.get("blame") if isinstance(row.get("blame"), dict) else None
        out.append({
            "trace_id": str(row.get("trace_id") or ""),
            "completed_at": row.get("completed_at"),
            "duration_ms": row.get("duration_ms"),
            "total_usd": row.get("total_usd"),
            "hops": row.get("hops") or len(steps),
            "failed": bool(row.get("failed")),
            "signed": bool(row.get("signed")),
            "trace_path": row.get("trace_path"),
            "steps": [
                {
                    "id": s.get("id"),
                    "product_id": s.get("product_id"),
                    "capability_id": s.get("capability_id"),
                    "status_code": s.get("status_code"),
                    "success": bool(s.get("success")),
                    "price_usd": s.get("price_usd"),
                }
                for s in steps
            ],
            "blame": {
                "policy": blame.get("policy"),
                "at_fault": blame.get("at_fault") if isinstance(blame.get("at_fault"), dict) else {},
                "not_at_fault": list(blame.get("not_at_fault") or []),
                "not_executed": list(blame.get("not_executed") or []),
            } if blame else None,
        })
    return out


def _totals(traces: list[dict[str, Any]]) -> dict[str, Any]:
    spend_micros = 0
    hops = 0
    failed = 0
    for t in traces:
        value = t.get("total_usd")
        if isinstance(value, (int, float)):
            # Integer micro-dollars: the rows are $0.001–$0.02 apiece and a float sum of
            # those drifts in exactly the digits the total is made of.
            spend_micros += round(float(value) * 1_000_000)
        hops += int(t.get("hops") or 0)
        if t.get("failed"):
            failed += 1
    return {
        "runs": len(traces),
        "spend_usd": round(spend_micros / 1_000_000, 6),
        "hops": hops,
        "failed": failed,
    }


@ttl_cached(ttl_s=20.0, env_var="ALIEN_HEPHAESTUS_TTL_S")
def fetch_hephaestus_status_sync() -> dict[str, Any] | None:
    """Read the trace projection and the manifest. Partial reads are still useful."""
    factory = hephaestus_factory_url()
    hub = hephaestus_hub_url()
    traces: list[dict[str, Any]] = []
    catalogue: dict[str, Any] = {}
    reachable = False

    try:
        with httpx.Client(timeout=4.0) as client:
            try:
                resp = client.get(f"{factory}/ai-market/pipelines", params={"limit": TRACE_LIMIT})
                if resp.status_code == 200:
                    traces = _sanitize_traces(resp.json().get("traces"))
                    reachable = True
            except Exception:
                pass
            try:
                resp = client.get(f"{hub}/ai-market/v2/manifest")
                if resp.status_code == 200:
                    catalogue = _catalogue_readiness(resp.json())
                    reachable = reachable or bool(catalogue)
            except Exception:
                pass
    except Exception:
        return None

    if not reachable:
        return None
    return {"traces": traces, "catalogue": catalogue}


def apply_hephaestus_to_nodes(
    nodes: list[dict], status: dict[str, Any] | None, *, public_url: str | None = None
) -> None:
    node = next((n for n in nodes if n.get("id") == "hephaestus"), None)
    if not node:
        return
    node["url"] = public_url or hephaestus_public_url()
    node["links"] = hephaestus_links()

    if not status:
        node["status"] = "offline"
        node.pop("hephaestus_live", None)
        node["metrics"] = {"runs": 0, "spend_usd": 0, "capabilities": 0}
        return

    traces = status.get("traces") or []
    catalogue = status.get("catalogue") or {}
    totals = _totals(traces)
    # "active" means something has actually run. A reachable studio with an empty trace
    # store is idle, and saying so is the difference between this node and decoration.
    node["status"] = "active" if totals["runs"] else "idle"
    node["hephaestus_live"] = {
        "studio_url": public_url or hephaestus_public_url(),
        "traces": traces,
        "totals": totals,
        "catalogue": catalogue,
    }
    node["metrics"] = {
        "runs": totals["runs"],
        "spend_usd": totals["spend_usd"],
        "capabilities": catalogue.get("capabilities", 0),
    }


def apply_hephaestus_graph(nodes: list[dict], *, mode: str = "real") -> None:
    _ = mode
    apply_hephaestus_to_nodes(nodes, fetch_hephaestus_status_sync())
