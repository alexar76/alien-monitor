"""One owner for "hydrate a universe graph with live satellite status".

Three call sites build the same universe graph — `GET /api/topology`, the warm-up snapshot
the WebSocket sends on connect, and `tick_universe` — and each applied a DIFFERENT subset of
the status layers. Measured on the running deployment:

    GET /api/topology   4 layers
    fast snapshot      12 layers
    tick_universe      16 layers

A satellite missing from a path renders at its node-spec defaults, which are `status:
"offline"` and zero metrics. So MOMUS showed "MOMUS недоступен, живых данных нет" on the
detail card while MOMUS itself was answering `/health`, `/findings` and `/intel` in under
300 ms from inside the monitor container, with three findings and forty-five intel cards.
ARGUS, ATLAS, GAIA, HELIOS, METIS, SKOPOS, DIOSCURI, HEPHAESTUS, LOGOS, Treasury and WARDEN
were all offline on at least one path for the same reason.

This is the same shape as `space_map`: several independent authors, and "has this been done"
was a question with no owner. The union lives here, once.

**The cache exists because correctness must not cost a page load.** Every layer polls its
satellite over the network with a 2-4 second timeout, sequentially. Seventeen of them, with a
few hosts down, is a minute of dead air on a REST call. So the overlay from the last full run
is remembered for `ALIEN_LAYER_CACHE_S` seconds and replayed — and since the broadcaster ticks
continuously, a REST caller almost always finds it warm. What is cached is the *diff* each
layer wrote, not the graph: node ids are stable, the volatile fields are exactly what the
layers touch, and replaying a diff onto a freshly built graph is the same result.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

#: Fields the layers own. Everything else about a node — id, group, position, children —
#: comes from the entity table and must never be replayed from a cache.
_CACHE: dict[str, Any] = {"at": 0.0, "overlay": {}}


def cache_ttl_s() -> float:
    try:
        return max(0.0, float(os.environ.get("ALIEN_LAYER_CACHE_S", "10")))
    except ValueError:
        return 10.0


def _snapshot(nodes: list[dict]) -> dict[str, dict]:
    return {str(n.get("id")): dict(n) for n in nodes if isinstance(n, dict) and n.get("id")}


def _diff(before: dict[str, dict], nodes: list[dict]) -> dict[str, dict]:
    overlay: dict[str, dict] = {}
    for node in nodes:
        if not isinstance(node, dict) or not node.get("id"):
            continue
        prior = before.get(str(node["id"]), {})
        changed = {k: v for k, v in node.items() if k not in prior or prior[k] != v}
        if changed:
            overlay[str(node["id"])] = changed
    return overlay


def _replay(overlay: dict[str, dict], nodes: list[dict]) -> int:
    applied = 0
    for node in nodes:
        if not isinstance(node, dict):
            continue
        patch = overlay.get(str(node.get("id")))
        if patch:
            node.update(patch)
            applied += 1
    return applied


def _apply_all(nodes: list[dict], *, tick: int, escrow: str, rpc: str,
               hub_payload: Any) -> None:
    """Every satellite status layer, in one place.

    Each is wrapped: a satellite that is down, slow or mid-deploy must leave the rest of the
    map alone. Before this existed a raising layer took out every layer after it in that
    call site's list, which is invisible — the nodes simply read offline.
    """
    from argus_status import apply_argus_graph
    from atlas_status import apply_atlas_graph
    from basanos_status import apply_basanos_graph
    from bridges_status import apply_bridges_graph
    from dioscuri_status import apply_dioscuri_graph
    from factory_agents import apply_factory_agents_graph
    from gaia_status import apply_gaia_graph
    from helios_status import apply_helios_graph
    from hephaestus_status import apply_hephaestus_graph
    from logos_status import apply_logos_to_nodes, fetch_logos_status_sync
    from metis_status import apply_metis_graph
    from momus_status import apply_momus_graph
    from settlement_status import apply_settlement_graph
    from skopos_status import apply_skopos_graph
    from themis_layers import apply_themis_graph
    from treasury_status import apply_treasury_graph
    from warden_status import apply_warden_graph

    steps: tuple[tuple[str, Any], ...] = (
        ("argus", lambda: apply_argus_graph(nodes, mode="universe")),
        ("gaia", lambda: apply_gaia_graph(nodes, mode="universe")),
        ("atlas", lambda: apply_atlas_graph(nodes, mode="universe")),
        ("dioscuri", lambda: apply_dioscuri_graph(nodes, mode="universe")),
        ("helios", lambda: apply_helios_graph(nodes, mode="universe")),
        ("metis", lambda: apply_metis_graph(nodes, mode="universe")),
        ("skopos", lambda: apply_skopos_graph(nodes, mode="universe")),
        ("hephaestus", lambda: apply_hephaestus_graph(nodes, mode="universe")),
        ("factory_agents", lambda: apply_factory_agents_graph(nodes, mode="universe")),
        ("momus", lambda: apply_momus_graph(nodes, mode="universe")),
        ("warden", lambda: apply_warden_graph(nodes, mode="universe")),
        ("treasury", lambda: apply_treasury_graph(nodes, mode="universe")),
        ("logos", lambda: apply_logos_to_nodes(nodes, fetch_logos_status_sync(timeout=2.0))),
        ("bridges", lambda: apply_bridges_graph(nodes, mode="universe")),
        ("themis", lambda: apply_themis_graph(
            nodes, mode="universe", tick=tick, hub_payload=hub_payload)),
        ("basanos", lambda: apply_basanos_graph(nodes, mode="universe")),
        # The universe has its own escrow on its own chain; pairing this world's address
        # with chain_net's RPC reads a contract that is not there and reports 0.
        ("settlement", lambda: apply_settlement_graph(
            nodes, mode="universe", escrow=escrow or "", rpc=rpc or "")),
    )
    for name, step in steps:
        try:
            step()
        except Exception as exc:  # noqa: BLE001
            logger.warning("universe layer %s failed: %s: %s", name, type(exc).__name__, exc)


def apply_live_layers(nodes: list[dict], *, tick: int = 0, escrow: str = "", rpc: str = "",
                      hub_payload: Any = None, allow_cache: bool = True) -> str:
    """Hydrate ``nodes`` in place. Returns "fresh" or "cached" for callers that log it.

    ``allow_cache=False`` forces a full poll — that is what the ticking broadcaster does, and
    it is what keeps the cache warm for everyone else.
    """
    ttl = cache_ttl_s()
    if allow_cache and ttl > 0 and _CACHE["overlay"]:
        age = time.time() - float(_CACHE["at"] or 0.0)
        if age <= ttl:
            _replay(_CACHE["overlay"], nodes)
            return "cached"

    before = _snapshot(nodes)
    _apply_all(nodes, tick=tick, escrow=escrow, rpc=rpc, hub_payload=hub_payload)
    _CACHE["overlay"] = _diff(before, nodes)
    _CACHE["at"] = time.time()
    return "fresh"


def reset_cache() -> None:
    _CACHE["at"] = 0.0
    _CACHE["overlay"] = {}
