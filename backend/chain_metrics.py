"""On-chain RPC polling and hub stats helpers for Alien Monitor LIVE mode."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx

EVM_RPC = (
    os.getenv("EVM_RPC_URL")
    or os.getenv("AIMARKET_NFT_CHAIN_RPC")
    or os.getenv("AIFACTORY_PAYMENT_RPC_BASE")
    or os.getenv("RPC_BASE")
    or ""
).strip()
SOLANA_RPC = (
    os.getenv("SOLANA_RPC_URL")
    or os.getenv("AIFACTORY_PAYMENT_RPC_SOLANA")
    or os.getenv("RPC_SOLANA")
    or ""
).strip()
EVM_ESCROW = os.getenv("AIMARKET_ESCROW_EVM_ADDRESS", "").strip()
SOLANA_ESCROW = os.getenv("AIMARKET_ESCROW_SOLANA_PROGRAM_ID", "").strip()
NFT_CONTRACT = os.getenv("AIMARKET_NFT_CONTRACT_ADDRESS", "").strip()


async def _evm_block_number(client: httpx.AsyncClient, rpc: str) -> tuple[int | None, str | None]:
    try:
        r = await client.post(
            rpc,
            json={"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []},
            timeout=8.0,
        )
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            return None, str(data["error"])
        hex_num = data.get("result", "0x0")
        return int(hex_num, 16), None
    except Exception as exc:
        return None, str(exc)


async def _evm_gas_gwei(client: httpx.AsyncClient, rpc: str) -> float | None:
    try:
        r = await client.post(
            rpc,
            json={"jsonrpc": "2.0", "id": 2, "method": "eth_gasPrice", "params": []},
            timeout=8.0,
        )
        r.raise_for_status()
        data = r.json()
        wei = int(data.get("result", "0x0"), 16)
        return round(wei / 1e9, 2)
    except Exception:
        return None


async def _solana_health(client: httpx.AsyncClient, rpc: str) -> tuple[bool, str | None]:
    try:
        r = await client.post(
            rpc,
            json={"jsonrpc": "2.0", "id": 1, "method": "getHealth"},
            timeout=8.0,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("result") == "ok":
            return True, None
        return False, str(data.get("error") or data.get("result"))
    except Exception as exc:
        return False, str(exc)


async def fetch_onchain_snapshot() -> dict[str, Any]:
    """Poll configured EVM/Solana RPCs; never raises."""
    snapshot: dict[str, Any] = {
        "evm_rpc": EVM_RPC or None,
        "solana_rpc": SOLANA_RPC or None,
        "evm_escrow": EVM_ESCROW or None,
        "solana_escrow": SOLANA_ESCROW or None,
        "nft_contract": NFT_CONTRACT or None,
        "block_number": None,
        "gas_gwei": None,
        "solana_ok": False,
        "onchain_tx_count": 0,
        "errors": [],
    }

    async with httpx.AsyncClient() as client:
        if EVM_RPC:
            block, err = await _evm_block_number(client, EVM_RPC)
            if err:
                snapshot["errors"].append(f"evm: {err}")
            else:
                snapshot["block_number"] = block
            gas = await _evm_gas_gwei(client, EVM_RPC)
            if gas is not None:
                snapshot["gas_gwei"] = gas
        else:
            snapshot["errors"].append("evm: EVM_RPC_URL not configured")

        if SOLANA_RPC:
            ok, err = await _solana_health(client, SOLANA_RPC)
            snapshot["solana_ok"] = ok
            if err:
                snapshot["errors"].append(f"solana: {err}")
        else:
            snapshot["errors"].append("solana: SOLANA_RPC_URL not configured")

    return snapshot


def hub_events_to_activity(hub_payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Map Hub /stats/live JSON to monitor events + hub metric hints."""
    events_out: list[dict[str, Any]] = []
    hints: dict[str, Any] = {}

    summary = hub_payload.get("summary") if isinstance(hub_payload, dict) else {}
    if isinstance(summary, dict):
        total = int(summary.get("total_invocations") or 0)
        hints["invocations_24h"] = total
        hints["channels_open"] = int(summary.get("open_channels") or summary.get("channels_open") or 0)

    raw_events = hub_payload.get("events") if isinstance(hub_payload, dict) else []
    if isinstance(raw_events, list):
        for ev in raw_events[:30]:
            if not isinstance(ev, dict):
                continue
            events_out.append(
                {
                    "type": "invocation",
                    "agent": ev.get("capability_id") or ev.get("agent_id") or "hub",
                    "detail": ev.get("consumer_hub") or ev.get("provider_hub") or "invoke",
                    "amount": ev.get("price_usd"),
                    "status": "ok" if ev.get("success", True) else "error",
                    "ts": ev.get("timestamp")
                    or datetime.now(timezone.utc).isoformat(),
                }
            )

    return events_out, hints


def apply_chain_metrics_to_nodes(nodes: list[dict[str, Any]], chain: dict[str, Any]) -> None:
    """Merge blockchain snapshot into topology nodes."""
    if not isinstance(chain, dict):
        return

    block = chain.get("block_number")
    gas = chain.get("gas_gwei")
    sol_ok = chain.get("solana_ok")

    for node in nodes:
        nid = node.get("id")
        if nid == "ethereum":
            if block is not None:
                node["metrics"]["block"] = block
                node["status"] = "active"
            if gas is not None:
                node["metrics"]["gas_gwei"] = gas
        elif nid == "solana":
            node["metrics"]["healthy"] = bool(sol_ok)
            if sol_ok:
                node["status"] = "active"
        elif nid == "evm_escrow":
            if EVM_ESCROW:
                node["metrics"]["address"] = EVM_ESCROW
                node["status"] = "active" if block is not None else node.get("status", "unknown")
        elif nid == "solana_escrow":
            if SOLANA_ESCROW:
                node["metrics"]["program_id"] = SOLANA_ESCROW
                node["status"] = "active" if sol_ok else node.get("status", "unknown")
        elif nid == "nft_contract" and NFT_CONTRACT:
            node["metrics"]["address"] = NFT_CONTRACT
            node["status"] = "active"


def build_real_summary(
    *,
    tick: int,
    hub_hints: dict[str, Any],
    mesh_stats: dict[str, Any] | None,
    chain: dict[str, Any],
) -> dict[str, Any]:
    """Aggregate header metrics for LIVE mode."""
    invocations = int(hub_hints.get("invocations_24h") or 0)
    channels = int(hub_hints.get("channels_open") or 0)
    agents = 0
    if isinstance(mesh_stats, dict):
        agents = int(mesh_stats.get("agents") or mesh_stats.get("agents_online") or 0)

    volume = 0.0
    if isinstance(mesh_stats, dict):
        volume = float(mesh_stats.get("volume_24h_usd") or mesh_stats.get("volume") or 0)

    return {
        "total_invocations_24h": invocations,
        "total_volume_usd": volume,
        "active_channels": channels,
        "tvl_usd": 0,
        "agents_online": agents,
        "apps_online": 0,
        "tps_solana": 0,
        "gas_gwei": chain.get("gas_gwei") or 0,
        "block_number": chain.get("block_number"),
        "onchain_tx_count": int(chain.get("onchain_tx_count") or 0),
        "mode": "real",
        "tick": tick,
        "blockchain_ready": bool(chain.get("block_number")) or bool(chain.get("solana_ok")),
        "evm_rpc": chain.get("evm_rpc"),
        "solana_rpc": chain.get("solana_rpc"),
    }
