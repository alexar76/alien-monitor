"""Agent Lottery node — topology anchor + live financial metrics for the monitor."""

from __future__ import annotations

import os
from typing import Any

DEFAULT_LOTTERY_URL = "https://lottery.modelmarket.dev"

#: Money keys that only ever come from a real source. When there is none they are
#: REMOVED from the node rather than shown as zeros: a card reading "$0 prize pool"
#: is a claim about the lottery, and one reading nothing is an admission about us.
_MONEY_KEYS = (
    "prize_pool_usd",
    "prize_pool",
    "payouts_24h",
    "opex_24h",
    "funding_24h",
    "funding_total",
    "prizes_paid",
    "opex_accrued",
    "ticket_revenue",
)


def lottery_url() -> str:
    return (os.environ.get("ALIEN_LOTTERY_URL") or DEFAULT_LOTTERY_URL).rstrip("/")


def lottery_node_spec() -> dict[str, Any]:
    """Static lottery node fields shared by TEST / LIVE / UNI topologies."""
    return {
        "id": "lottery",
        "label": "Agent Lottery",
        "group": "economy",
        "icon": "lottery",
        "description": (
            "AI-agent oracle lottery — unbiasable draws (Platon + Chronos VDF), "
            "LUMEN-weighted, Hub-sponsored. Economic actor: Hub tithe in, opex to oracles, prizes to agents."
        ),
        "metrics": {
            "round": 0,
            "players": 0,
        },
        "status": "unknown",
        "position": {"x": 5, "y": 3, "z": 3},
        "url": lottery_url(),
    }


def lottery_financial_links(*, oracle_ids: list[str] | None = None) -> list[dict[str, str]]:
    """Directed financial edges: Hub sponsor → lottery → oracles; mesh → lottery tickets."""
    links = [
        {"source": "hub", "target": "lottery", "label": "Sponsor tithe"},
        {"source": "mesh", "target": "lottery", "label": "Agent tickets"},
    ]
    targets = oracle_ids or ["federation"]
    for oid in targets:
        links.append({"source": "lottery", "target": oid, "label": "Oracle draw"})
    return links


def _metrics_from_chain(lot: dict[str, Any]) -> dict[str, float | int | str]:
    """The contract's own figures, under names that say which window they describe."""
    token = str(lot.get("prize_token") or "").strip() or "TOKEN"
    metrics: dict[str, float | int | str] = {
        "round": int(lot.get("round") or 0),
        "players": int(lot.get("players") or 0),
        "tickets": int(lot.get("tickets") or 0),
        "prize_token": token,
    }
    # A pool denominated in ETH is not a number of dollars, and this ecosystem has no
    # price oracle (same stance as payment verification). Only USDC gets the _usd name.
    pool = float(lot.get("prize_pool") or 0)
    metrics["prize_pool_usd" if token == "USDC" else "prize_pool"] = round(pool, 6)
    for key in ("funding_total", "prizes_paid", "opex_accrued", "ticket_revenue"):
        if key in lot:
            metrics[key] = round(float(lot[key] or 0), 6)
    return metrics


def _metrics_from_layers(
    hub_hints: dict[str, Any] | None,
    mesh_stats: dict[str, Any] | None,
    chain: dict[str, Any] | None = None,
) -> dict[str, float | int | str]:
    """Lottery figures from a real source only: the relayer push, or the contract.

    There used to be a third branch, and it was the one production actually took: the
    hub's channel volume times a constant — `prize_pool = volume * 0.05`,
    `payouts_24h = volume * 0.03`, `opex_24h = volume * 0.02`,
    `funding_24h = volume * 0.20`. On 2026-09-07 that painted a $0.17 prize pool, $0.10
    of payouts and a $0.66 hub tithe onto the LIVE card, derived from $3.32 of lifetime
    escrow volume, while the deployed contract had never opened a round and held nothing.
    """
    from live_lottery_feed import live_metrics_if_fresh

    live = live_metrics_if_fresh()
    if live:
        return live
    lot = (chain or {}).get("lottery") if isinstance(chain, dict) else None
    if isinstance(lot, dict) and lot.get("read_ok"):
        return _metrics_from_chain(lot)
    from chain_metrics import mesh_agent_count

    agents = mesh_agent_count(mesh_stats)
    # Agents in the mesh are eligible players, and that IS a real reading — but it is
    # the only one available, so it ships alone rather than as a seed for guesses.
    return {"players": agents} if agents else {}


def _lottery_is_live(
    hub_hints: dict[str, Any] | None,
    mesh_stats: dict[str, Any] | None,
    chain: dict[str, Any] | None = None,
) -> str:
    """Node status: active with a round running, idle when read but quiet, else unknown."""
    from live_lottery_feed import live_lottery_fresh

    if live_lottery_fresh():
        return "active"
    lot = (chain or {}).get("lottery") if isinstance(chain, dict) else None
    if isinstance(lot, dict) and lot.get("read_ok"):
        return "active" if int(lot.get("round") or 0) > 0 else "idle"
    return "unknown"


def _merge_metrics(current: dict[str, Any], fresh: dict[str, Any]) -> dict[str, Any]:
    """Overlay a real reading; drop the money keys no source vouched for."""
    merged = {**current, **fresh}
    for key in _MONEY_KEYS:
        if key not in fresh:
            merged.pop(key, None)
    return merged


def apply_lottery_metrics(
    nodes: list[dict],
    *,
    hub_hints: dict[str, Any] | None = None,
    mesh_stats: dict[str, Any] | None = None,
    chain: dict[str, Any] | None = None,
) -> None:
    """Fill lottery node metrics from a real source (relayer push or contract read)."""
    lot = next((n for n in nodes if n.get("id") == "lottery"), None)
    if lot is None:
        return
    lot.setdefault("url", lottery_url())
    lot["metrics"] = _merge_metrics(lot.get("metrics") or {}, _metrics_from_layers(hub_hints, mesh_stats, chain))
    lot["status"] = _lottery_is_live(hub_hints, mesh_stats, chain)


def apply_lottery_entity(
    entities: dict[str, Any],
    *,
    hub_hints: dict[str, Any] | None = None,
    mesh_stats: dict[str, Any] | None = None,
    chain: dict[str, Any] | None = None,
) -> None:
    """Update lottery EcosystemEntity in UNI runtime."""
    ent = entities.get("lottery")
    if ent is None:
        return
    ent.url = lottery_url()
    ent.metrics = _merge_metrics(ent.metrics or {}, _metrics_from_layers(hub_hints, mesh_stats, chain))
    ent.status = _lottery_is_live(hub_hints, mesh_stats, chain)
