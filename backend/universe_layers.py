"""
Poll live ecosystem layers for UNI mode — Hub, Mesh, Factory, Prometheus, local chain.

No simulated metrics: if a service is down, nodes stay idle/unknown with zero values.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx

from chain_metrics import (
    apply_chain_metrics_to_nodes,
    build_real_summary,
    fetch_onchain_snapshot,
    hub_events_to_activity,
    mesh_agent_count,
)

# Default URLs for the locally deployed aicom stack (docker-compose).
DEFAULT_HUB_URL = "http://127.0.0.1:9083"
DEFAULT_MESH_URL = "http://127.0.0.1:8090"
DEFAULT_APP_URL = "http://127.0.0.1:9081"
DEFAULT_PROM_URL = "http://127.0.0.1:9090/prometheus"


def layer_urls() -> dict[str, str]:
    """Where UNI polls. The bubble hub is not the live hub on :9083.

    ``ALIEN_UNIVERSE_HUB_URL`` is the explicit override. Otherwise the public
    UNI edge (``ALIEN_UNI_HUB_URL``) — the same hostname the card shows. Only
    if neither is set do we fall back to ``HUB_URL``, which on a shared host is
    the live federation and would paint live invokes as universe activity.

    The same argument applies to every OTHER layer, and used to be made for the hub
    alone: mesh / factory / prometheus fall through to ``MESH_URL`` / ``AICOM_API_URL`` /
    ``PROMETHEUS_URL``, so a bubble monitor sharing a host with the live stack reads the
    LIVE mesh and the LIVE factory and draws them inside the realm. Measured 2026-09-07:
    both maps reported ``AGENTS 3`` — the same three live agents, presented on the UNI map
    as the bubble's own.

    Blanking those layers instead was the first fix and it was the wrong one twice over: it
    would have hidden real services from a single-stack dev deploy, and it keyed off
    ``ALIEN_UNI_HUB_URL``, which the actual production bubble does not set (it points plain
    ``HUB_URL`` at the bubble's own port). So the fallback stays and stops being silent:
    ``layer_sources()`` says, per layer, whether the address was declared FOR this realm
    (``ALIEN_UNIVERSE_*``) or inherited from the shared environment — and every node built
    from an inherited layer carries that address and a shared marker onto its card.
    """
    hub = (os.environ.get("ALIEN_UNIVERSE_HUB_URL") or "").strip().rstrip("/")
    if not hub:
        hub = (os.environ.get("ALIEN_UNI_HUB_URL") or "").strip().rstrip("/")
    if not hub:
        hub = (os.environ.get("HUB_URL") or DEFAULT_HUB_URL).rstrip("/")

    return {
        "hub": hub,
        "mesh": _layer_url("mesh"),
        "app": _layer_url("app"),
        "prom": _layer_url("prom"),
    }


#: Per layer: the env var that declares it FOR the UNI realm, the shared one it otherwise
#: inherits, and the single-stack default. One table, so the URL and its provenance can
#: never be computed from two different rules.
_LAYER_ENV: dict[str, tuple[str, str, str]] = {
    "mesh": ("ALIEN_UNIVERSE_MESH_URL", "MESH_URL", DEFAULT_MESH_URL),
    "app": ("ALIEN_UNIVERSE_APP_URL", "AICOM_API_URL", DEFAULT_APP_URL),
    "prom": ("ALIEN_UNIVERSE_PROM_URL", "PROMETHEUS_URL", DEFAULT_PROM_URL),
}


def _layer_url(layer: str) -> str:
    explicit, shared, default = _LAYER_ENV[layer]
    value = (os.environ.get(explicit) or "").strip().rstrip("/")
    if value:
        return value
    return (os.environ.get(shared) or default).rstrip("/")


def layer_sources() -> dict[str, str]:
    """Per layer: ``"realm"`` when declared for UNI, ``"shared"`` when inherited.

    "shared" is not an error — on a one-host demo the live stack IS what the realm has to
    look at. It is a fact the map has to state, because the alternative is a bubble
    reporting another realm's agents as its own with nothing on screen to say so.
    """
    out: dict[str, str] = {}
    for layer, (explicit, _shared, _default) in _LAYER_ENV.items():
        out[layer] = "realm" if (os.environ.get(explicit) or "").strip() else "shared"
    return out


def _get(client: httpx.Client, url: str) -> tuple[Any | None, str | None]:
    try:
        r = client.get(url)
        if r.status_code == 200:
            return r.json(), None
        return None, f"{url} -> HTTP {r.status_code}"
    except Exception as exc:
        return None, f"{url} unreachable: {exc}"


def fetch_layers_sync(
    *,
    evm_rpc: str,
    contracts: dict[str, str | None],
    chain_label: str = "EVM",
    timeout: float = 6.0,
) -> dict[str, Any]:
    """Synchronous poll of all UNI ecosystem layers + local chain RPC."""
    urls = layer_urls()
    out: dict[str, Any] = {
        "urls": urls,
        # Per layer: declared for this realm, or inherited from the shared environment.
        "layer_sources": layer_sources(),
        "errors": [],
        "hub": None,
        "mesh": None,
        "factory": None,
        "prometheus": None,
        "plugins": None,
        "agents": [],
        "events": [],
        "hub_hints": {},
        "chain": None,
    }

    with httpx.Client(timeout=timeout) as client:
        hub_data, err = _get(client, f"{urls['hub']}/ai-market/v2/stats/live")
        if err:
            out["errors"].append(err)
        else:
            out["hub"] = hub_data
            events, hints = hub_events_to_activity(hub_data if isinstance(hub_data, dict) else {})
            out["events"] = events
            out["hub_hints"] = hints

        mesh_data, err = _get(client, f"{urls['mesh']}/v1/stats")
        if err:
            out["errors"].append(err)
        else:
            out["mesh"] = mesh_data

        agents_data, err = _get(client, f"{urls['mesh']}/v1/agents")
        if err:
            out["errors"].append(err)
        elif isinstance(agents_data, list):
            out["agents"] = agents_data

        factory_data, err = _get(client, f"{urls['app']}/api/health")
        if err:
            out["errors"].append(err)
        else:
            out["factory"] = factory_data

        try:
            r = client.get(f"{urls['prom']}/api/v1/query", params={"query": "pipeline_tasks_total"})
            if r.status_code == 200:
                out["prometheus"] = r.json()
            else:
                out["errors"].append(f"prometheus -> HTTP {r.status_code}")
        except Exception as exc:
            out["errors"].append(f"prometheus unreachable: {exc}")

        plugins_data, err = _get(client, f"{urls['hub']}/ai-market/v2/plugins")
        if err:
            out["errors"].append(err)
        else:
            out["plugins"] = plugins_data

    # Local chain — force universe RPC + deployed contract addresses.
    #
    # Every one of these is restored afterwards. The RPC and chain label already were;
    # the contract addresses were not, so one universe tick left the bubble's escrow and
    # NFT addresses in `os.environ` for the rest of the process's life. The realm seal
    # keeps a LIVE process from ticking universe at all, which is the only reason that
    # never surfaced — it should not be the only reason.
    overrides = {
        "ALIEN_EVM_RPC": evm_rpc,
        "ALIEN_EVM_CHAIN": chain_label,
        "AIMARKET_ESCROW_EVM_ADDRESS": contracts.get("escrow_evm"),
        "AIMARKET_NFT_CONTRACT": contracts.get("nft_evm"),
        # The bubble's lottery, read from the bubble's chain — so the UNI card carries the
        # contract's own figures instead of waiting on a relayer push.
        "AIMARKET_LOTTERY_EVM_ADDRESS": contracts.get("lottery_evm"),
        "AIMARKET_PAYMENT_RECIPIENT": contracts.get("payment_recipient"),
    }
    previous = {name: os.environ.get(name) for name in overrides}
    for name, value in overrides.items():
        if value:
            os.environ[name] = value

    import asyncio

    try:
        out["chain"] = asyncio.run(fetch_onchain_snapshot(timeout=timeout))
        out["errors"].extend(out["chain"].get("errors") or [])
    except Exception as exc:
        out["errors"].append(f"chain poll: {exc}")
        out["chain"] = {"errors": [str(exc)], "evm": None, "solana": None}
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    return out


def _pipeline_task_counts(prom: dict | None) -> tuple[int, int]:
    """Return (pending-ish, done-ish) from prometheus pipeline_tasks_total if present."""
    if not isinstance(prom, dict):
        return 0, 0
    try:
        results = prom.get("data", {}).get("result", [])
        done = 0
        for row in results:
            val = row.get("value", [None, "0"])
            done += int(float(val[1]))
        return 0, done
    except (TypeError, ValueError, IndexError):
        return 0, 0


def apply_layers_to_entities(entities: dict, layers: dict[str, Any]) -> None:
    """Update ecosystem entity metrics/status from polled layer data."""
    hub = entities.get("hub")
    if hub and (layers.get("hub") or layers.get("hub_hints")):
        hub.status = "active"
        hints = layers.get("hub_hints") or {}
        hub.metrics["invocations_24h"] = int(hints.get("invocations_24h") or 0)
        hub.metrics["channels_open"] = int(hints.get("channels_open") or 0)
        hub.metrics["capabilities"] = int(hints.get("capabilities") or hub.metrics.get("capabilities") or 0)
        hub.metrics["peers"] = int(hints.get("peers") or hub.metrics.get("peers") or 0)
    elif hub:
        hub.status = "idle"

    # Which address each layer's numbers came from, and whether that address belongs to
    # this realm or is the host's shared one. A visible fact on the card, rather than
    # something you work out from the deploy environment — which is how the UNI map came
    # to report the LIVE mesh's three agents as its own.
    urls = layers.get("urls") if isinstance(layers.get("urls"), dict) else {}
    sources = layers.get("layer_sources") if isinstance(layers.get("layer_sources"), dict) else {}
    for entity_id, layer_key in (("mesh", "mesh"), ("factory", "app")):
        entity = entities.get(entity_id)
        if entity is None or not urls.get(layer_key):
            continue
        entity.source_url = str(urls[layer_key])
        entity.source_shared = sources.get(layer_key) == "shared"

    mesh_ent = entities.get("mesh")
    mesh = layers.get("mesh")
    if mesh_ent and isinstance(mesh, dict):
        mesh_ent.status = "active"
        # Third reader of the same counter — the one `mesh_agent_count`'s docstring warns
        # about. It read only `agents` / `agents_online`, neither of which the mesh emits.
        mesh_ent.metrics["agents"] = mesh_agent_count(mesh) or len(layers.get("agents") or [])
        mesh_ent.metrics["tasks"] = int(mesh.get("tasks") or mesh.get("tasks_total") or 0)
        mesh_ent.metrics["activity"] = int(mesh.get("activity") or mesh.get("events_total") or 0)
    elif mesh_ent:
        mesh_ent.status = "idle"

    factory = entities.get("factory")
    if factory and layers.get("factory"):
        factory.status = "active"
        _, tasks_done = _pipeline_task_counts(layers.get("prometheus"))
        factory.metrics["tasks_done"] = tasks_done
        factory.metrics["tasks_pending"] = int(factory.metrics.get("tasks_pending") or 0)
        factory.metrics["products"] = len([e for e in entities.values() if e.group == "product"])
    elif factory:
        factory.status = "idle"

    plugins = entities.get("plugins")
    pdata = layers.get("plugins")
    if plugins and isinstance(pdata, dict):
        plist = pdata.get("plugins") or []
        if isinstance(plist, list):
            plugins.status = "active"
            plugins.metrics["loaded"] = len(plist)
            plugins.metrics["total"] = len(plist)

    acex = entities.get("acex")
    if acex:
        # The realm's 24h invoke volume, from the hub. `acex_uni.acex_metrics_for_monitor`
        # adds this node's OWN cumulative counters afterwards under their own names
        # (`volume_total_usd`, `trades_total`) — it used to publish them as `volume_24h`
        # and overwrite this line, putting lifetime turnover under a 24h label.
        vol = float((layers.get("hub_hints") or {}).get("volume_24h") or 0)
        acex.metrics["volume_24h"] = vol
        acex.status = "active" if vol > 0 else "idle"

    chain = layers.get("chain") or {}
    evm = chain.get("evm") or {}
    if entities.get("ethereum") and evm.get("connected"):
        entities["ethereum"].status = "active"
        entities["ethereum"].metrics = {
            "chain_id": evm.get("chain_id", 0),
            "block": evm.get("block", 0),
            "gas": evm.get("gas_gwei", 0),
            "tx_count": evm.get("tx_count", 0) if "tx_count" in evm else 0,
            "rpc": evm.get("rpc", ""),
        }

    sol = chain.get("solana") or {}
    if entities.get("solana") and sol.get("connected"):
        entities["solana"].status = "active"
        entities["solana"].metrics = {
            "slot": sol.get("slot", 0),
            "block_height": sol.get("block_height", 0),
            "tps": 0,
            "rpc": sol.get("rpc", ""),
        }

    # Contract nodes via chain_metrics helper on node list
    node_list = [e.to_node() for e in entities.values()]
    apply_chain_metrics_to_nodes(node_list, chain)
    by_id = {n["id"]: n for n in node_list}
    for eid, ent in entities.items():
        if eid in by_id:
            ent.metrics.update(by_id[eid].get("metrics") or {})
            ent.status = by_id[eid].get("status", ent.status)


def sync_agent_entities(entities: dict, agents: list[dict], agents_registry: list[dict]) -> None:
    """Replace placeholder agents with agents registered in AI Service Mesh."""
    from ecosystem_layout import mesh_agent_position
    from universe import EcosystemEntity

    for key in list(entities.keys()):
        if key.startswith("agent_"):
            del entities[key]
    agents_registry.clear()
    mesh_ent = entities.get("mesh")
    mesh_pos = dict(mesh_ent.position) if mesh_ent is not None else None
    for i, ag in enumerate(agents[:24]):
        if not isinstance(ag, dict):
            continue
        aid = str(ag.get("id") or ag.get("agent_id") or f"agent_{i}")
        name = str(ag.get("name") or ag.get("display_name") or aid)
        ent = EcosystemEntity(f"agent_{aid}", name, "agent", "agent", icon="planet")
        ent.metrics = {
            "invocations": int(ag.get("invocations") or ag.get("tasks_completed") or 0),
            "channels_open": int(ag.get("channels_open") or 0),
            "balance_eth": 0,
            "verified": 1 if ag.get("verified") else 0,
        }
        ent.status = "active" if ag.get("verified", True) else "idle"
        ent.parent_id = "mesh"
        ent.position = mesh_agent_position(i, mesh_pos=mesh_pos)
        entities[ent.id] = ent
        agents_registry.append({"id": ent.id, "name": name, "balance": 0})


def build_universe_summary(
    *,
    tick: int,
    layers: dict[str, Any],
    agents_count: int,
    products_count: int,
    onchain_tx_count: int,
) -> dict[str, Any]:
    chain = layers.get("chain") or {}
    summary = build_real_summary(
        tick=tick,
        hub_hints=layers.get("hub_hints") or {},
        mesh_stats=layers.get("mesh") if isinstance(layers.get("mesh"), dict) else None,
        chain=chain,
    )
    summary["mode"] = "universe"
    summary["agents_online"] = agents_count
    summary["products_created"] = products_count
    summary["onchain_tx_count"] = onchain_tx_count
    summary["blockchain_ready"] = bool((chain.get("evm") or {}).get("connected"))
    summary["tvl_usd"] = 0
    # APPS = the products this realm actually has. It used to be
    # `min(9, tasks_done // 10)` — a number with no referent, capped at nine, that moved
    # when the pipeline ran and had nothing to do with how many apps existed.
    summary["apps_online"] = int(products_count or 0)
    return summary


def apply_buyer_health(summary: dict[str, Any], scenario_output: dict[str, Any] | None) -> None:
    """Put a stalled realm economy in the summary, where the header can say so.

    The buyer failing is not a detail of the scenario: it is the realm having no economy.
    It was visible only as a 400 per round in the container log.
    """
    buyer = (scenario_output or {}).get("buyer")
    if not isinstance(buyer, dict):
        return
    summary["buyer_rounds"] = int(buyer.get("rounds") or 0)
    summary["buyer_purchases_total"] = int(buyer.get("purchases_total") or 0)
    halted = str(buyer.get("halted") or "").strip()
    blocked = str(buyer.get("last_open_error") or "").strip()
    if halted:
        summary["economy_stalled"] = halted
    elif blocked and int(buyer.get("open_failures") or 0) > 0:
        summary["economy_stalled"] = (
            f"channel/open refused by {buyer.get('hub_url')} — {blocked}"
        )
