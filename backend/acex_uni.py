"""ACEX CapShare markets on UNI (embedded Anvil): deploy, seed pools, periodic trades."""

from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from eth_account import Account
from web3 import Web3

if TYPE_CHECKING:
    from universe import VirtualUniverse

# Standard Foundry dev mnemonic — accounts 0–4 (local UNI only).
_MNEMONIC = "test test test test test test test test test test test junk"


def _anvil_key(index: int) -> str:
    from eth_account import Account

    Account.enable_unaudited_hdwallet_features()
    acct = Account.from_mnemonic(_MNEMONIC, account_path=f"m/44'/60'/0'/0/{index}")
    key = acct.key.hex()
    return key if key.startswith("0x") else f"0x{key}"


def _anvil_addr(index: int) -> str:
    return Account.from_key(_anvil_key(index)).address

# PulseAMM MIN_INITIAL_USDC = 1_000e6; seed well above that for a stable demo price.
POOL_USDC = int(os.environ.get("ALIEN_ACEX_POOL_USDC", str(50_000 * 10**6)))
POOL_SHARES = int(os.environ.get("ALIEN_ACEX_POOL_SHARES", str(500_000 * 10**18)))
TRADE_USDC = int(os.environ.get("ALIEN_ACEX_TRADE_USDC", str(250 * 10**6)))  # $250/swap

DEMO_LISTINGS: tuple[dict[str, str | int], ...] = (
    {"slug": "sentinel", "name": "Sentinel CapShare", "symbol": "SNTL"},
    {"slug": "atlas", "name": "Atlas CapShare", "symbol": "ATLS"},
    {"slug": "gaia", "name": "Gaia CapShare", "symbol": "GAIA"},
)

ERC20_ABI = [
    {"name": "approve", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],
     "outputs": [{"type": "bool"}]},
    {"name": "transfer", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}],
     "outputs": [{"type": "bool"}]},
    {"name": "balanceOf", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "account", "type": "address"}], "outputs": [{"type": "uint256"}]},
]

REGISTRY_ABI = [
    {"name": "setAuditor", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "auditor", "type": "address"}, {"name": "allowed", "type": "bool"}],
     "outputs": []},
    {"name": "applyForListing", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "listingId", "type": "bytes32"}, {"name": "metadataHash", "type": "bytes32"}],
     "outputs": []},
    {"name": "recordAudit", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "listingId", "type": "bytes32"}, {"name": "auditScoreBps", "type": "uint256"}],
     "outputs": []},
    {"name": "approveListing", "type": "function", "stateMutability": "nonpayable",
     "inputs": [
         {"name": "listingId", "type": "bytes32"},
         {"name": "name", "type": "string"},
         {"name": "symbol", "type": "string"},
         {"name": "maxSupply", "type": "uint256"},
     ],
     "outputs": [{"name": "shareToken", "type": "address"}]},
    {"name": "getListing", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "listingId", "type": "bytes32"}],
     "outputs": [{
         "components": [
             {"name": "listingId", "type": "bytes32"},
             {"name": "agentWallet", "type": "address"},
             {"name": "metadataHash", "type": "bytes32"},
             {"name": "auditScoreBps", "type": "uint256"},
             {"name": "shareToken", "type": "address"},
             {"name": "maxSupply", "type": "uint256"},
             {"name": "status", "type": "uint8"},
             {"name": "listedAt", "type": "uint64"},
         ],
         "type": "tuple",
     }]},
]

AMM_ABI = [
    {"name": "setMarketMaker", "type": "function", "stateMutability": "nonpayable",
     "inputs": [{"name": "mm", "type": "address"}, {"name": "allowed", "type": "bool"}],
     "outputs": []},
    {"name": "createPool", "type": "function", "stateMutability": "nonpayable",
     "inputs": [
         {"name": "shareToken", "type": "address"},
         {"name": "usdc", "type": "address"},
         {"name": "initialShares", "type": "uint256"},
         {"name": "initialUsdc", "type": "uint256"},
     ],
     "outputs": []},
    {"name": "swapUsdcForShare", "type": "function", "stateMutability": "nonpayable",
     "inputs": [
         {"name": "shareToken", "type": "address"},
         {"name": "usdcIn", "type": "uint256"},
         {"name": "minShareOut", "type": "uint256"},
     ],
     "outputs": [{"name": "shareOut", "type": "uint256"}]},
    {"name": "swapShareForUsdc", "type": "function", "stateMutability": "nonpayable",
     "inputs": [
         {"name": "shareToken", "type": "address"},
         {"name": "shareIn", "type": "uint256"},
         {"name": "minUsdcOut", "type": "uint256"},
     ],
     "outputs": [{"name": "usdcOut", "type": "uint256"}]},
    {"name": "pools", "type": "function", "stateMutability": "view",
     "inputs": [{"name": "shareToken", "type": "address"}],
     "outputs": [
         {"name": "shareToken", "type": "address"},
         {"name": "usdc", "type": "address"},
         {"name": "reserveShare", "type": "uint256"},
         {"name": "reserveUsdc", "type": "uint256"},
         {"name": "active", "type": "bool"},
     ]},
]


def acex_uni_enabled() -> bool:
    return os.environ.get("ALIEN_UNI_ACEX_ENABLE", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def _state_path(u: VirtualUniverse) -> Path:
    return u.data_dir / "acex_uni_state.json"


def load_acex_state(u: VirtualUniverse) -> dict[str, Any]:
    path = _state_path(u)
    if not path.is_file():
        return {"pools": [], "volume_usdc": 0.0, "trades": 0}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"pools": [], "volume_usdc": 0.0, "trades": 0}


def save_acex_state(u: VirtualUniverse, state: dict[str, Any]) -> None:
    _state_path(u).write_text(json.dumps(state, indent=2), encoding="utf-8")


def _send(w3: Web3, key: str, fn, *, value: int = 0, gas: int = 2_500_000) -> dict:
    acct = Account.from_key(key)
    tx = fn.build_transaction({
        "from": acct.address,
        "nonce": w3.eth.get_transaction_count(acct.address),
        "gas": gas,
        "chainId": w3.eth.chain_id,
        "value": value,
    })
    signed = acct.sign_transaction(tx)
    receipt = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction), timeout=120)
    if receipt.get("status") != 1:
        raise RuntimeError(f"tx reverted: {receipt.get('transactionHash', b'').hex()}")
    return receipt


def _listing_id(slug: str) -> bytes:
    return Web3.keccak(text=f"uni-acex-{slug}")


def seed_acex_markets(u: VirtualUniverse) -> bool:
    """List CapShares on the registry and open PulseAMM pools (idempotent)."""
    if not acex_uni_enabled():
        return False
    if not u._w3 or not u._w3.is_connected():
        return False
    if not (u.evm_acex_amm_address and u.evm_acex_registry_address and u.evm_usdt_address):
        return False

    state = load_acex_state(u)
    existing = {p.get("share") for p in (state.get("pools") or []) if p.get("share")}
    if state.get("pools") and len(existing) >= len(DEMO_LISTINGS):
        return True

    w3 = u._w3
    deployer_key = _anvil_key(0)
    deployer = Account.from_key(deployer_key).address
    registry = w3.eth.contract(
        address=w3.to_checksum_address(u.evm_acex_registry_address),
        abi=REGISTRY_ABI,
    )
    amm = w3.eth.contract(
        address=w3.to_checksum_address(u.evm_acex_amm_address),
        abi=AMM_ABI,
    )
    usdc = w3.eth.contract(
        address=w3.to_checksum_address(u.evm_usdt_address),
        abi=ERC20_ABI,
    )
    amm_addr = w3.to_checksum_address(u.evm_acex_amm_address)
    usdc_addr = w3.to_checksum_address(u.evm_usdt_address)

    _send(w3, deployer_key, registry.functions.setAuditor(deployer, True))
    _send(w3, deployer_key, amm.functions.setMarketMaker(deployer, True))

    pools: list[dict[str, str]] = []
    max_supply = int(os.environ.get("ALIEN_ACEX_MAX_SUPPLY", str(1_000_000 * 10**18)))

    for i, spec in enumerate(DEMO_LISTINGS):
        agent_key = _anvil_key(i + 1)
        agent = Account.from_key(agent_key).address
        lid = _listing_id(str(spec["slug"]))
        listing = registry.functions.getListing(lid).call()
        status = int(listing[6])
        agent_wallet = Web3.to_checksum_address(listing[1])
        empty = "0x0000000000000000000000000000000000000000"

        if agent_wallet == empty:
            _send(w3, agent_key, registry.functions.applyForListing(lid, Web3.keccak(text=str(spec["slug"]))))
            _send(w3, deployer_key, registry.functions.recordAudit(lid, 8500))
        elif status == 1 and int(listing[3]) < 7000:
            _send(w3, deployer_key, registry.functions.recordAudit(lid, 8500))

        listing = registry.functions.getListing(lid).call()
        if int(listing[6]) != 2:
            _send(
                w3,
                deployer_key,
                registry.functions.approveListing(lid, str(spec["name"]), str(spec["symbol"]), max_supply),
            )

        listing = registry.functions.getListing(lid).call()
        share_addr = Web3.to_checksum_address(listing[4])
        if share_addr == "0x0000000000000000000000000000000000000000":
            print(f"[ACEX-UNI] could not resolve share token for {spec['slug']}")
            continue

        pool = amm.functions.pools(share_addr).call()
        if not pool[4]:
            share = w3.eth.contract(address=share_addr, abi=ERC20_ABI)
            if share.functions.balanceOf(deployer).call() < POOL_SHARES:
                _send(w3, agent_key, share.functions.transfer(deployer, POOL_SHARES))
            _send(w3, deployer_key, usdc.functions.approve(amm_addr, POOL_USDC))
            _send(w3, deployer_key, share.functions.approve(amm_addr, POOL_SHARES))
            _send(
                w3,
                deployer_key,
                amm.functions.createPool(share_addr, usdc_addr, POOL_SHARES, POOL_USDC),
            )
        pools.append({"slug": spec["slug"], "share": share_addr, "symbol": spec["symbol"]})
        print(f"[ACEX-UNI] pool live: {spec['symbol']} @ {share_addr}")

        state["pools"] = pools
        state["seeded_at"] = time.time()
        save_acex_state(u, state)
        for i in range(1, 4):
            trader = _anvil_addr(i)
            if usdc.functions.balanceOf(trader).call() < TRADE_USDC * 20:
                _send(w3, deployer_key, usdc.functions.transfer(trader, 200_000 * 10**6))
        u._bootstrap_notes.append(f"acex: {len(pools)} CapShare pools seeded")
    return bool(pools)


def tick_acex_trades(u: VirtualUniverse) -> None:
    """Periodic on-chain CapShare/USDC swaps to keep UNI ACEX metrics live."""
    if not acex_uni_enabled():
        return
    every = max(1, int(os.environ.get("ALIEN_ACEX_TRADE_TICKS", "30") or 30))
    if u.tick % every != 0:
        return
    if not u._w3 or not u._w3.is_connected() or not u.evm_acex_amm_address:
        return

    state = load_acex_state(u)
    pools = state.get("pools") or []
    if not pools:
        return

    w3 = u._w3
    pool = random.choice(pools)
    share_addr = w3.to_checksum_address(pool["share"])
    trader_key = _anvil_key(random.randint(1, 3))
    trader = Account.from_key(trader_key).address

    amm = w3.eth.contract(address=w3.to_checksum_address(u.evm_acex_amm_address), abi=AMM_ABI)
    usdc = w3.eth.contract(address=w3.to_checksum_address(u.evm_usdt_address), abi=ERC20_ABI)
    share = w3.eth.contract(address=share_addr, abi=ERC20_ABI)

    try:
        if random.random() < 0.55:
            _send(w3, trader_key, usdc.functions.approve(w3.to_checksum_address(u.evm_acex_amm_address), TRADE_USDC))
            _send(w3, trader_key, amm.functions.swapUsdcForShare(share_addr, TRADE_USDC, 0))
            vol = TRADE_USDC / 1e6
        else:
            bal = share.functions.balanceOf(trader).call()
            amt = min(bal // 4, POOL_SHARES // 100)
            if amt < 1000:
                return
            _send(w3, trader_key, share.functions.approve(w3.to_checksum_address(u.evm_acex_amm_address), amt))
            _send(w3, trader_key, amm.functions.swapShareForUsdc(share_addr, amt, 0))
            vol = TRADE_USDC / 1e6 * 0.9
        state["volume_usdc"] = float(state.get("volume_usdc") or 0) + vol
        state["trades"] = int(state.get("trades") or 0) + 1
        save_acex_state(u, state)
        u.transactions.append({
            "id": f"acex_{state['trades']:04d}",
            "hash": "",
            "from": trader[:12],
            "to": share_addr[:12],
            "action": "acex_swap",
            "target": "acex",
            "amount": round(vol, 2),
            "token": "USDC",
            "block": 0,
            "gas_used": 0,
            "status": "confirmed",
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
            "onchain": True,
        })
        if len(u.transactions) > 100:
            u.transactions = u.transactions[-100:]
    except Exception as exc:
        print(f"[ACEX-UNI] trade tick failed: {exc}")


def acex_metrics_for_monitor(u: VirtualUniverse) -> dict[str, Any]:
    state = load_acex_state(u)
    pools = state.get("pools") or []
    return {
        "volume_24h": round(float(state.get("volume_usdc") or 0), 2),
        "listings": len(pools),
        "pools_active": len(pools),
        "trades": int(state.get("trades") or 0),
    }
