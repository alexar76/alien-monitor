"""
On-chain metrics for Alien Monitor LIVE (real) mode.

Reads RPC URLs and contract addresses from the same env vars as AI-Factory /
aimarket-hub (.env in repo root). Uses JSON-RPC via httpx — no hard dependency
on web3.py for LIVE polling.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx

# Per-chain RPC env keys (aligned with aicom/.env.example)
_CHAIN_RPC_KEYS: dict[str, str] = {
    "base": "BASE_RPC_URL",
    "ethereum": "ETHEREUM_RPC_URL",
    "eth": "ETHEREUM_RPC_URL",
    "arbitrum": "ARBITRUM_RPC_URL",
    "optimism": "OPTIMISM_RPC_URL",
    "polygon": "POLYGON_RPC_URL",
    "solana": "SOLANA_RPC_URL",
}


def _strip_addr(val: str) -> str:
    return (val or "").strip().strip('"').strip("'")


def primary_evm_chain() -> str:
    for key in (
        "ALIEN_EVM_CHAIN",
        "AIMARKET_PAYMENT_CHAIN",
        "AIFACTORY_AI_MARKET_CHAIN",
        "AIMARKET_NFT_CHAIN",
    ):
        raw = (os.environ.get(key) or "").strip().lower()
        if raw and raw != "solana":
            return raw
    return "base"


def evm_rpc_for_chain(chain: str) -> str | None:
    chain = chain.strip().lower()
    override = (
        os.environ.get("ALIEN_EVM_RPC")
        or os.environ.get("EVM_RPC")
        or os.environ.get("EVM_RPC_URL")
        or ""
    ).strip()
    if override:
        return override
    nft_chain = (os.environ.get("AIMARKET_NFT_CHAIN") or "").strip().lower()
    nft_rpc = (os.environ.get("AIMARKET_NFT_CHAIN_RPC") or "").strip()
    if nft_rpc and chain == nft_chain:
        return nft_rpc
    env_key = _CHAIN_RPC_KEYS.get(chain)
    if env_key:
        url = (os.environ.get(env_key) or "").strip()
        if url:
            return url
    if chain == "base":
        for key in ("AIFACTORY_PAYMENT_RPC_BASE", "RPC_BASE"):
            url = (os.environ.get(key) or "").strip()
            if url:
                return url
    return None


def solana_rpc_url() -> str:
    return (
        os.environ.get("ALIEN_SOLANA_RPC")
        or os.environ.get("SOLANA_RPC_URL")
        or os.environ.get("AIFACTORY_PAYMENT_RPC_SOLANA")
        or os.environ.get("RPC_SOLANA")
        or "https://api.mainnet-beta.solana.com"
    ).strip()


def configured_contracts() -> dict[str, str | None]:
    escrow = _strip_addr(
        os.environ.get("AIMARKET_ESCROW_EVM_ADDRESS")
        or os.environ.get("AIFACTORY_AI_MARKET_CONTRACT")
        or ""
    )
    nft = _strip_addr(
        os.environ.get("AIMARKET_NFT_CONTRACT")
        or os.environ.get("AIMARKET_NFT_CONTRACT_ADDRESS")
        or ""
    )
    sol_program = _strip_addr(os.environ.get("AIMARKET_ESCROW_SOLANA_PROGRAM_ID") or "")
    recipient = _strip_addr(os.environ.get("AIMARKET_PAYMENT_RECIPIENT") or "")
    return {
        "escrow_evm": escrow or None,
        "nft_evm": nft or None,
        "escrow_solana": sol_program or None,
        "payment_recipient": recipient or None,
    }


def _hex_to_int(val: Any) -> int:
    if val is None:
        return 0
    if isinstance(val, int):
        return val
    s = str(val).strip()
    if s.startswith("0x"):
        return int(s, 16)
    return int(s)


async def _json_rpc(
    client: httpx.AsyncClient,
    url: str,
    method: str,
    params: list[Any],
) -> Any:
    resp = await client.post(
        url,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("error"):
        raise RuntimeError(payload["error"])
    return payload.get("result")


async def fetch_evm_metrics(
    client: httpx.AsyncClient,
    *,
    chain: str,
    rpc_url: str,
    contracts: dict[str, str | None],
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "chain": chain,
        "rpc": rpc_url,
        "connected": False,
        "errors": [],
        "contracts": {},
    }
    try:
        block_hex = await _json_rpc(client, rpc_url, "eth_blockNumber", [])
        gas_hex = await _json_rpc(client, rpc_url, "eth_gasPrice", [])
        chain_id_hex = await _json_rpc(client, rpc_url, "eth_chainId", [])
        block = _hex_to_int(block_hex)
        gas_wei = _hex_to_int(gas_hex)
        chain_id = _hex_to_int(chain_id_hex)
        out.update(
            {
                "connected": True,
                "block": block,
                "gas_gwei": round(gas_wei / 1e9, 4),
                "chain_id": chain_id,
            }
        )
    except Exception as exc:
        out["errors"].append(f"evm rpc ({chain}): {exc}")
        return out

    for label, addr in (
        ("escrow", contracts.get("escrow_evm")),
        ("nft", contracts.get("nft_evm")),
        ("recipient", contracts.get("payment_recipient")),
    ):
        if not addr or not addr.startswith("0x") or len(addr) < 42:
            continue
        info: dict[str, Any] = {"address": addr, "deployed": False, "balance_eth": 0.0}
        try:
            code = await _json_rpc(client, rpc_url, "eth_getCode", [addr, "latest"])
            info["deployed"] = bool(code and code not in ("0x", "0x0"))
            bal_hex = await _json_rpc(client, rpc_url, "eth_getBalance", [addr, "latest"])
            info["balance_eth"] = round(_hex_to_int(bal_hex) / 1e18, 6)
        except Exception as exc:
            info["error"] = str(exc)
        out["contracts"][label] = info

    return out


async def fetch_solana_metrics(
    client: httpx.AsyncClient,
    *,
    rpc_url: str,
    program_id: str | None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "rpc": rpc_url,
        "connected": False,
        "errors": [],
        "program": None,
    }
    try:
        slot = await _json_rpc(client, rpc_url, "getSlot", [])
        height = await _json_rpc(client, rpc_url, "getBlockHeight", [])
        out.update(
            {
                "connected": True,
                "slot": int(slot),
                "block_height": int(height),
            }
        )
    except Exception as exc:
        out["errors"].append(f"solana rpc: {exc}")
        return out

    if program_id:
        prog: dict[str, Any] = {"address": program_id, "deployed": False}
        try:
            result = await _json_rpc(
                client,
                rpc_url,
                "getAccountInfo",
                [program_id, {"encoding": "base64"}],
            )
            value = (result or {}).get("value")
            prog["deployed"] = bool(value and value.get("executable"))
            prog["lamports"] = (value or {}).get("lamports", 0)
        except Exception as exc:
            prog["error"] = str(exc)
        out["program"] = prog

    return out


async def fetch_onchain_snapshot(timeout: float = 8.0) -> dict[str, Any]:
    """Poll configured EVM + Solana RPCs and contract deployment status."""
    chain = primary_evm_chain()
    evm_rpc = evm_rpc_for_chain(chain)
    contracts = configured_contracts()
    sol_rpc = solana_rpc_url()

    snapshot: dict[str, Any] = {
        "primary_chain": chain,
        "contracts": contracts,
        "evm": None,
        "solana": None,
        "errors": [],
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        if evm_rpc:
            snapshot["evm"] = await fetch_evm_metrics(
                client, chain=chain, rpc_url=evm_rpc, contracts=contracts
            )
            snapshot["errors"].extend(snapshot["evm"].get("errors") or [])
        else:
            snapshot["errors"].append(
                f"No EVM RPC configured for chain {chain!r} "
                f"(set {chain.upper()}_RPC_URL or ALIEN_EVM_RPC)"
            )

        snapshot["solana"] = await fetch_solana_metrics(
            client,
            rpc_url=sol_rpc,
            program_id=contracts.get("escrow_solana"),
        )
        snapshot["errors"].extend(snapshot["solana"].get("errors") or [])

    return snapshot


def apply_chain_metrics_to_nodes(nodes: list[dict], chain: dict[str, Any]) -> None:
    """Merge on-chain snapshot into topology nodes (ethereum, escrows, nft)."""
    evm = chain.get("evm") or {}
    sol = chain.get("solana") or {}
    contracts_cfg = chain.get("contracts") or {}

    by_id = {n["id"]: n for n in nodes}

    if "ethereum" in by_id and evm.get("connected"):
        by_id["ethereum"]["status"] = "active"
        by_id["ethereum"]["metrics"] = {
            "chain": evm.get("chain", ""),
            "chain_id": evm.get("chain_id", 0),
            "block": evm.get("block", 0),
            "gas": evm.get("gas_gwei", 0),
            "rpc": evm.get("rpc", ""),
        }

    evm_contracts = evm.get("contracts") or {}

    if "evm_escrow" in by_id:
        esc = evm_contracts.get("escrow") or {}
        addr = esc.get("address") or contracts_cfg.get("escrow_evm")
        if addr:
            by_id["evm_escrow"]["metrics"] = {
                "address": addr,
                "chain": evm.get("chain", chain.get("primary_chain", "")),
                "deployed": 1 if esc.get("deployed") else 0,
                "balance_eth": esc.get("balance_eth", 0),
                "channels": 0,
                "tvl": 0,
            }
            by_id["evm_escrow"]["status"] = "active" if esc.get("deployed") else (
                "idle" if evm.get("connected") else "unknown"
            )
        elif evm.get("connected"):
            by_id["evm_escrow"]["status"] = "idle"
            by_id["evm_escrow"]["metrics"]["chain"] = evm.get("chain", "")

    if "nft_contract" in by_id:
        nft = evm_contracts.get("nft") or {}
        addr = nft.get("address") or contracts_cfg.get("nft_evm")
        if addr:
            by_id["nft_contract"]["metrics"] = {
                "address": addr,
                "chain": evm.get("chain", ""),
                "deployed": 1 if nft.get("deployed") else 0,
                "balance_eth": nft.get("balance_eth", 0),
                "minted": 0,
                "holders": 0,
            }
            by_id["nft_contract"]["status"] = "active" if nft.get("deployed") else (
                "idle" if evm.get("connected") else "unknown"
            )

    if "solana" in by_id and sol.get("connected"):
        by_id["solana"]["status"] = "active"
        by_id["solana"]["metrics"] = {
            "slot": sol.get("slot", 0),
            "block_height": sol.get("block_height", 0),
            "tps": 0,
            "rpc": sol.get("rpc", ""),
        }

    if "solana_escrow" in by_id:
        prog = sol.get("program") or {}
        addr = prog.get("address") or contracts_cfg.get("escrow_solana")
        if addr:
            by_id["solana_escrow"]["metrics"] = {
                "program_id": addr,
                "deployed": 1 if prog.get("deployed") else 0,
                "lamports": prog.get("lamports", 0),
                "channels": 0,
                "tvl": 0,
            }
            by_id["solana_escrow"]["status"] = "active" if prog.get("deployed") else (
                "idle" if sol.get("connected") else "unknown"
            )
        elif sol.get("connected"):
            by_id["solana_escrow"]["status"] = "idle"


def hub_events_to_activity(hub_payload: dict[str, Any]) -> tuple[list[dict], dict[str, Any]]:
    """Map hub /stats/live JSON to monitor events + metric hints."""
    events_out: list[dict] = []
    hints: dict[str, Any] = {
        "invocations_24h": 0,
        "channels_open": 0,
        "volume_24h": 0,
    }
    summary = hub_payload.get("summary") if isinstance(hub_payload, dict) else {}
    if isinstance(summary, dict):
        hints["invocations_24h"] = int(summary.get("total_invocations") or summary.get("invocations_24h") or 0)
        hints["channels_open"] = int(summary.get("open_channels") or summary.get("channels_open") or 0)
        hints["volume_24h"] = float(summary.get("volume_usd") or summary.get("volume_24h") or 0)

    raw_events = hub_payload.get("events") if isinstance(hub_payload, dict) else []
    if not isinstance(raw_events, list):
        return events_out, hints

    for i, ev in enumerate(raw_events[:20]):
        if not isinstance(ev, dict):
            continue
        events_out.append(
            {
                "id": str(ev.get("id") or f"hub_{i}"),
                "ts": ev.get("ts") or datetime.now(timezone.utc).isoformat(),
                "agent": str(ev.get("consumer_hub") or ev.get("agent") or "hub-client"),
                "action": str(ev.get("action") or "invoke"),
                "target": str(ev.get("capability_id") or ev.get("target") or "hub"),
                "amount": float(ev.get("amount_usd") or ev.get("amount") or 0),
                "token": str(ev.get("token") or "USDT"),
                "onchain": False,
            }
        )
    return events_out, hints


def build_real_summary(
    *,
    tick: int,
    hub_hints: dict[str, Any],
    mesh_stats: dict[str, Any] | None,
    chain: dict[str, Any],
) -> dict[str, Any]:
    evm = chain.get("evm") or {}
    sol = chain.get("solana") or {}
    agents = 0
    if isinstance(mesh_stats, dict):
        agents = int(mesh_stats.get("agents") or mesh_stats.get("agents_online") or 0)

    return {
        "total_invocations_24h": hub_hints.get("invocations_24h", 0),
        "total_volume_usd": hub_hints.get("volume_24h", 0),
        "active_channels": hub_hints.get("channels_open", 0),
        "tvl_usd": 0,
        "agents_online": agents,
        "apps_online": 0,
        "tps_solana": 0,
        "gas_gwei": evm.get("gas_gwei", 0),
        "block_number": evm.get("block", 0),
        "onchain_tx_count": 0,
        "mode": "real",
        "tick": tick,
        "blockchain_ready": bool(evm.get("connected") or sol.get("connected")),
        "evm_chain": evm.get("chain") or chain.get("primary_chain"),
        "evm_rpc": evm.get("rpc"),
        "solana_rpc": sol.get("rpc"),
        "evm_chain_id": evm.get("chain_id"),
        "solana_slot": sol.get("slot"),
    }
