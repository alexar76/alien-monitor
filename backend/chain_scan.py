"""A block scanner for the realm's own chain.

WHY THIS EXISTS
---------------
The monitor could tell you a chain was there — `eth_chainId`, `eth_blockNumber`,
`eth_gasPrice`, a balance — but never what happened on it. The ACTIVITY STREAM panel that
looks like transactions is hub invocations; nothing in the monitor had ever read a block.

That is fine for a chain you only cite. It is not fine for the UNI bubble, which exists to be
an economy of its own on its own Anvil: a parallel chain whose whole point is that things
happen on it. You cannot run a market you cannot look at.

WHAT IT DECODES, AND WHAT IT REFUSES TO GUESS
---------------------------------------------
Addresses are named from the realm's own deployment file (`config/deployments/*.json`), so a
transfer reads as "USDC" and an escrow call as "AIMarketEscrow" rather than as hex. Anything
not in that file stays hex — an explorer that guesses at identity is worse than one that
admits it does not know, because the guess is what gets quoted later.

Method names come from a 4-byte selector table built from the same source. An unknown
selector is reported as the raw four bytes, never as a plausible-looking name.

FAILURE DIRECTION
-----------------
Every failure returns an empty scan with a reason. A block explorer that can 500 takes the
dashboard with it, and the dashboard is the thing people actually need up.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

#: How many blocks back a single scan may walk. Anvil blocks are cheap to fetch, but a scan
#: is on a request path: past this the answer stops being "recent activity" and starts being
#: an archive query, which is a different feature with different costs.
MAX_BLOCK_SPAN = int(os.getenv("ALIEN_CHAIN_SCAN_SPAN", "60") or 60)

#: How far back to walk on a PUBLIC chain. A bubble block holds a handful of our own
#: transactions; a Base block holds hundreds of strangers' and arrives over somebody else's
#: free endpoint, so sixty of them is megabytes of JSON per panel open. The operator's
#: explicit ALIEN_CHAIN_SCAN_SPAN still wins — this is only the unconfigured default.
PUBLIC_BLOCK_SPAN = int(os.getenv("ALIEN_CHAIN_SCAN_SPAN_PUBLIC", "12") or 12)


def _block_span(source: dict[str, Any] | None) -> int:
    if os.getenv("ALIEN_CHAIN_SCAN_SPAN"):
        return MAX_BLOCK_SPAN
    return MAX_BLOCK_SPAN if (source or {}).get("source") != "settings-network" else PUBLIC_BLOCK_SPAN

#: Selector -> signature. A STATIC table on purpose: computing these needs keccak, and adding
#: a crypto dependency to a read-only panel buys nothing a precomputed dict does not already
#: give. Every escrow entry below was derived from the real ABI at
#: `contracts/evm/out/AIMarketEscrow.sol/AIMarketEscrow.json`, not from memory — a wrong name
#: on a money movement is worse than showing the raw four bytes, which is what an unknown
#: selector still gets.
SELECTORS: dict[str, str] = {
    # ERC-20
    "0xa9059cbb": "transfer",
    "0x23b872dd": "transferFrom",
    "0x095ea7b3": "approve",
    "0x40c10f19": "mint",
    "0x42966c68": "burn",
    # AIMarketEscrow — the calls a bubble economy actually makes
    "0xba999563": "openChannel",
    "0xf7becd80": "debitChannel",
    "0xfd3d3199": "settleChannel",
    "0x04020c10": "refundChannel",
    "0x42161b74": "expireChannel",
    "0xdd5967c3": "batchRefund",
    "0xe3e5af47": "setHubAuthorization",
    "0xc9bcc97e": "setTokenWhitelist",
    "0x4160df5a": "computeDebitDigest",
    "0x831c2b82": "getChannel",
    "0x093c4ee6": "getChannelBalance",
    "0x5788680f": "isChannelOpen",
    "0xf2fde38b": "transferOwnership",
    "0x79ba5097": "acceptOwnership",
    # AIAgentLottery — the UNI bubble's periodic raffle economy (relayer-driven)
    "0xe562dfd9": "openRound",
    "0x8627df46": "buyTickets",
    "0x54a75ed5": "buyTicketsWithVoucher",
    "0xc1f7522b": "closeEntries",
    "0xc39ec144": "fulfillDraw",
    "0xd7098154": "claimPrize",
    "0xa65e2cfd": "fund",
    "0xd3c0f231": "withdrawOpex",
    "0x278ecde1": "refund",
    "0x7e07ab09": "cancelRound",
    # ACEX PulseAMM — CapShare markets
    "0xa5ebc6cd": "swapUsdcForShare",
    "0xe07f6afd": "swapShareForUsdc",
}


#: topic0 -> event name. Same discipline as SELECTORS: a STATIC table of the two ERC-20 events
#: every token emits, whose keccak topic0 values are fixed constants of the standard. An
#: unknown topic0 is shown as its raw 32 bytes, never as a guessed event name.
EVENTS: dict[str, str] = {
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef": "Transfer",
    "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925": "Approval",
}


def _deployment_names(realm: str) -> dict[str, str]:
    """address -> contract name, from the deployment file for this realm.

    Reads every `config/deployments/*.json` and keeps the entries whose `realm` matches, so a
    bubble address is never labelled with a mainnet contract's name and vice versa.
    """
    out: dict[str, str] = {}
    # Several candidate roots, and no exception on any of them. This file is read from a
    # container (/app), from the repo, and from a scratch copy during testing; a scanner that
    # raises because a directory it merely HOPED for is absent is a scanner that takes the
    # dashboard down over cosmetics. Missing names cost hex labels, nothing more.
    here = Path(__file__).resolve()
    # NOT `Path(os.getenv(...) or "")`: an unset variable makes `Path("")`, which is `Path(".")`,
    # which IS a directory — so the current working directory won every lookup and the labels
    # came back empty while every path in the list was correct.
    override = (os.getenv("ALIEN_DEPLOYMENTS_DIR") or "").strip()
    roots = [
        *([Path(override)] if override else []),
        # The monitor ships its OWN copy and that one wins: it is what the running image
        # actually contains, and the repo's `config/deployments` is not copied into it.
        here.parent / "deployments",
        Path("/app/backend/deployments"),
        Path("/app/config/deployments"),
        *[p / "config" / "deployments" for p in list(here.parents)[:4]],
    ]
    root = next((r for r in roots if str(r) and r.is_dir()), None)
    if root is None:
        return out
    # The universe keeps its OWN address book, and in the bubble it is the only one that
    # matters: nine live contracts (USDT, escrow, NFT, lottery, and the five ACEX pieces)
    # whose addresses appear in no deployment file. Without this the bubble's own scanner
    # shows its own economy as hex.
    for cfg in (Path("/app/data/universe/universe_config.json"),
                here.parents[1] / "data" / "universe" / "universe_config.json"):
        if not cfg.is_file():
            continue
        try:
            doc = json.loads(cfg.read_text(encoding="utf-8"))
        except Exception:
            continue
        for key, addr in doc.items():
            if isinstance(addr, str) and addr.startswith("0x") and len(addr) == 42:
                label = key.replace("evm_", "").replace("_", " ").upper()
                out.setdefault(addr.lower(), label)
        break

    for path in sorted(root.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if realm and str(doc.get("realm") or "") not in ("", realm):
            continue
        for name, addr in (doc.get("contracts") or {}).items():
            if isinstance(addr, str) and addr.startswith("0x"):
                out[addr.lower()] = str(name)
        for key in ("owner_wallet", "hub_wallet", "buyer_wallet"):
            addr = doc.get(key)
            if isinstance(addr, str) and addr.startswith("0x"):
                out.setdefault(addr.lower(), key.replace("_wallet", "").upper())
    return out


async def _rpc(client: httpx.AsyncClient, url: str, method: str, params: list[Any]) -> Any:
    resp = await client.post(url, json={"jsonrpc": "2.0", "id": 1,
                                        "method": method, "params": params})
    resp.raise_for_status()
    body = resp.json()
    if isinstance(body, dict) and body.get("error"):
        raise RuntimeError(str(body["error"])[:120])
    return (body or {}).get("result")


def _hex_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value), 16) if str(value).startswith("0x") else int(value)
    except (TypeError, ValueError):
        return default


def _tx_row(tx: dict[str, Any], block_number: int, timestamp: int,
            names: dict[str, str]) -> dict[str, Any]:
    """One transaction as the scanner shows it. Shared by the list, the address page and the
    tx page so a transaction reads identically wherever it appears."""
    data = str(tx.get("input") or "0x")
    selector = data[:10] if len(data) >= 10 else ""
    to_addr = (tx.get("to") or "").lower()
    from_addr = str(tx.get("from") or "").lower()
    return {
        "hash": tx.get("hash"),
        "block": block_number,
        "timestamp": timestamp,
        "from": tx.get("from"),
        "from_label": names.get(from_addr, ""),
        "to": tx.get("to"),
        # "" and not a guess: an explorer that invents an identity is the thing people quote.
        "to_label": names.get(to_addr, "") if to_addr else "contract creation",
        "value_wei": str(_hex_int(tx.get("value"))),
        # A deploy has no selector; a plain send has no input at all.
        "method": (SELECTORS.get(selector)
                   or ("deploy" if not to_addr else (selector or "send"))),
        "input_bytes": max(0, (len(data) - 2) // 2),
    }


async def scan_tx(rpc_url: str, tx_hash: str, *, realm: str = "",
                  timeout: float = 8.0,
                  network: dict[str, Any] | None = None) -> dict[str, Any]:
    """One transaction with its receipt: status, gas, and decoded log topics.

    The receipt is where an explorer earns its keep — a call can be mined and still have
    REVERTED, and only the receipt's status tells them apart. Same fail-soft contract as
    scan_chain: any failure returns a row carrying only a note.
    """
    source = network if network is not None else chain_source_info()
    empty = {"found": False, "note": "", "network": source}
    if not rpc_url:
        return {**empty, "note": "no RPC configured for this realm"}
    if not (isinstance(tx_hash, str) and tx_hash.startswith("0x") and len(tx_hash) == 66):
        return {**empty, "note": "not a transaction hash"}
    names = _deployment_names(realm)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            tx = await _rpc(client, rpc_url, "eth_getTransactionByHash", [tx_hash])
            if not tx:
                return {**empty, "note": "no such transaction on this chain"}
            block_number = _hex_int(tx.get("blockNumber"))
            block = await _rpc(client, rpc_url, "eth_getBlockByNumber",
                               [hex(block_number), False]) or {}
            receipt = await _rpc(client, rpc_url,
                                 "eth_getTransactionReceipt", [tx_hash]) or {}
            row = _tx_row(tx, block_number, _hex_int(block.get("timestamp")), names)
            logs = []
            for lg in (receipt.get("logs") or []):
                topics = lg.get("topics") or []
                topic0 = (topics[0] if topics else "") or ""
                addr = str(lg.get("address") or "").lower()
                logs.append({
                    "address": lg.get("address"),
                    "address_label": names.get(addr, ""),
                    "event": EVENTS.get(topic0.lower(), topic0[:10] if topic0 else "log"),
                    "topics": len(topics),
                    "data_bytes": max(0, (len(str(lg.get("data") or "0x")) - 2) // 2),
                })
            status_hex = receipt.get("status")
            row.update({
                "found": True,
                "network": empty["network"],
                "nonce": _hex_int(tx.get("nonce")),
                # status is 0x1 success / 0x0 revert; absent on a pre-Byzantium chain (never here).
                "status": (None if status_hex is None else _hex_int(status_hex)),
                "gas_used": _hex_int(receipt.get("gasUsed")),
                "gas_limit": _hex_int(tx.get("gas")),
                "effective_gas_price_wei": str(_hex_int(
                    receipt.get("effectiveGasPrice") or tx.get("gasPrice"))),
                "contract_deployed": receipt.get("contractAddress"),
                "logs": logs,
                "input": str(tx.get("input") or "0x")[:522],  # 4-byte selector + up to 8 args
                "note": "",
            })
            return row
    except Exception as exc:  # noqa: BLE001
        return {**empty, "note": f"{type(exc).__name__}: {str(exc)[:120]}"}


async def scan_address(rpc_url: str, address: str, *, realm: str = "", limit: int = 25,
                       timeout: float = 8.0,
                       network: dict[str, Any] | None = None) -> dict[str, Any]:
    """An address page: balance, nonce, whether it holds code, and its recent transactions.

    The recent-tx list is built the only way a node without an index allows — walk the last
    MAX_BLOCK_SPAN blocks and keep the ones that touch this address. So it is 'recent activity',
    bounded like scan_chain, not an account's full history.
    """
    source = network if network is not None else chain_source_info()
    empty = {"found": False, "address": address, "txs": [], "note": "", "network": source}
    if not rpc_url:
        return {**empty, "note": "no RPC configured for this realm"}
    if not (isinstance(address, str) and address.startswith("0x") and len(address) == 42):
        return {**empty, "note": "not an address"}
    target = address.lower()
    names = _deployment_names(realm)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            balance = _hex_int(await _rpc(client, rpc_url,
                                          "eth_getBalance", [address, "latest"]))
            nonce = _hex_int(await _rpc(client, rpc_url,
                                        "eth_getTransactionCount", [address, "latest"]))
            code = str(await _rpc(client, rpc_url, "eth_getCode", [address, "latest"]) or "0x")
            head = _hex_int(await _rpc(client, rpc_url, "eth_blockNumber", []))
            txs: list[dict[str, Any]] = []
            span = _block_span(source)
            for number in range(head, max(-1, head - span), -1):
                if len(txs) >= limit:
                    break
                block = await _rpc(client, rpc_url, "eth_getBlockByNumber",
                                   [hex(number), True]) or {}
                ts = _hex_int(block.get("timestamp"))
                for tx in reversed(block.get("transactions") or []):
                    if len(txs) >= limit:
                        break
                    if target in ((str(tx.get("from") or "").lower()),
                                  (str(tx.get("to") or "").lower())):
                        row = _tx_row(tx, number, ts, names)
                        row["direction"] = ("out" if str(tx.get("from") or "").lower() == target
                                            else "in")
                        txs.append(row)
            return {
                "found": True,
                "network": empty["network"],
                "address": address,
                "label": names.get(target, ""),
                "balance_wei": str(balance),
                "nonce": nonce,
                "is_contract": len(code) > 2,
                "code_size": max(0, (len(code) - 2) // 2),
                "txs": txs,
                "note": "",
            }
    except Exception as exc:  # noqa: BLE001
        return {**empty, "note": f"{type(exc).__name__}: {str(exc)[:120]}"}


def chain_source_info() -> dict[str, Any]:
    """WHICH chain this scan is reading, and why — the label the panel puts on every row.

    Delegated to chain_metrics so the scanner and the status panel cannot disagree, and
    imported lazily and defensively: the scanner runs from a container, from the repo and
    from a bare test copy, and a missing sibling must cost a label, not the scan.
    """
    try:
        from chain_metrics import chain_source

        return {k: v for k, v in chain_source().items() if k != "urls"}
    except Exception:  # noqa: BLE001
        return {}


def _declared_mismatch(chain_id: int | None,
                       source: dict[str, Any] | None) -> dict[str, Any] | None:
    try:
        from chain_metrics import declared_network_mismatch
    except Exception:  # noqa: BLE001
        return None
    try:
        return declared_network_mismatch(chain_id, source or None)
    except Exception:  # noqa: BLE001
        return None


async def scan_chain(rpc_url: str, *, realm: str = "", limit: int = 25,
                     timeout: float = 8.0,
                     network: dict[str, Any] | None = None) -> dict[str, Any]:
    """Recent transactions on `rpc_url`, newest first.

    `limit` bounds the transactions returned; MAX_BLOCK_SPAN bounds how far back we look for
    them. A quiet chain therefore returns fewer than `limit` rather than walking to genesis.
    """
    source = network if network is not None else chain_source_info()
    empty = {"chain_id": None, "head": None, "txs": [], "scanned_blocks": 0, "note": "",
             "chain_mismatch": None, "network": source}
    if not rpc_url:
        return {**empty, "note": "no RPC configured for this realm"}

    names = _deployment_names(realm)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            chain_id = _hex_int(await _rpc(client, rpc_url, "eth_chainId", []))
            head = _hex_int(await _rpc(client, rpc_url, "eth_blockNumber", []))
            txs: list[dict[str, Any]] = []
            scanned = 0
            span = _block_span(source)
            for number in range(head, max(-1, head - span), -1):
                if len(txs) >= limit:
                    break
                scanned += 1
                block = await _rpc(client, rpc_url, "eth_getBlockByNumber",
                                   [hex(number), True]) or {}
                for tx in reversed(block.get("transactions") or []):
                    if len(txs) >= limit:
                        break
                    txs.append(_tx_row(tx, number, _hex_int(block.get("timestamp")), names))
            # The scan is the one place that reads the chain's OWN answer, so it is also the
            # place that can catch a monitor pointed at a different chain than it advertises.
            return {"chain_id": chain_id, "head": head, "txs": txs,
                    "scanned_blocks": scanned, "note": "", "network": source,
                    "chain_mismatch": _declared_mismatch(chain_id, source)}
    except Exception as exc:  # noqa: BLE001 - a scanner may never take the dashboard down
        return {**empty, "note": f"{type(exc).__name__}: {str(exc)[:120]}"}
