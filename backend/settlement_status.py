"""Settlement — what the escrow contract says was actually collected.

This node exists because money now moves and the monitor showed nothing about it. What it
draws is deliberately narrow, and the boundaries are the point:

**It never talks to the signer.** HORKOS holds the only key authorized in
``AIMarketEscrow.authorizedHubs`` and lives behind a reverse SSH tunnel reachable only from
the hub host, so that nothing else can dial it. Polling it from a public dashboard would
mean a second tunnel or a wider bind — weakening that boundary for a picture. Everything
here is read from chain instead.

**It publishes nothing that is not already public.** Every number below is a `getLogs` or an
`eth_call` any observer can make, and the signer's address and its transactions are on
Basescan the moment it signs. What is deliberately absent: the signer's spend caps and how
much of today's budget is left. Those are not public facts, and "the budget is nearly gone"
or "the signer is refusing" is an invitation — the first tells a griefer when to push, the
second when to time an attack. They belong behind an operator token, in the hub's admin
route, not on a canvas served with ALIEN_PUBLIC_READ=1.

**It does not invent the pending side.** An authorization the buyer signed is invisible on
chain until it is submitted, so "how much is signed but uncollected" cannot be derived here.
Rather than draw a plausible zero, the node says where that number lives.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

import chain_net
from onchain_reads import addr_arg, call_data, decode_uint, event_topic
from poll_cache import ttl_cached

# ChannelDebited(bytes32 indexed channelId, uint256 amount, bytes32 receiptId, uint256 remaining)
EV_CHANNEL_DEBITED = event_topic("ChannelDebited(bytes32,uint256,bytes32,uint256)")

USDC_DECIMALS = 6
# The "50 blocks" this file used to assert was ONE endpoint's limit generalised to all of
# them. Measured against every live public Base endpoint on 2026-09-11: six serve a
# 1000-block `eth_getLogs`, publicnode serves 10 000, and only 1rpc.io says
# "eth_getLogs is limited to 0 - 50 blocks range". So the window is walked in chunks at
# whatever width the endpoint we landed on accepts, narrowing when it objects.
#
# A week of Base history is ~300 000 blocks — 300 requests at 1000 a time, not the ~8 000
# the old comment feared, but still far too many for a monitor tick. So the lookback stays
# bounded (below), the node still reports the LIFETIME total as unavailable rather than
# inventing one, and what changed is that the live window is now hours instead of ~100
# seconds. An indexer is still what would supply real history.
DEFAULT_LOOKBACK_BLOCKS = 5_000          # ~2.8 h of Base at 2 s blocks
MAX_LOOKBACK_BLOCKS = 50_000             # ~28 h; 50 requests at the default chunk width
LOG_CHUNK_BLOCKS = 1_000                 # the width six of eleven endpoints serve
LOG_CHUNK_MIN = 50                       # 1rpc.io's ceiling — the narrowest we degrade to
#: Provider wording for "your window is too wide" — an instruction to ask for less, not a
#: transport fault and not a malformed request (several return -32602, which reads like one).
_RANGE_REFUSALS = (
    "limited to",
    "block range too large",
    "exceeds max results",
    "range too large",
    "too many blocks",
    "query returned more than",
    "response size exceeded",
    "413",
    "payload too large",
)
# Below this the float pays for only a few more debits, and an empty float presents to the hub
# as a string of indistinguishable refusals — worth showing before it happens.
GAS_LOW_WEI = 200_000_000_000_000   # 0.0002 ETH


def lookback_blocks() -> int:
    """Clamped to what a public endpoint will actually serve, so a bigger number in the
    environment degrades to a working probe instead of an endpoint-side refusal."""
    try:
        want = int(os.environ.get("ALIEN_SETTLEMENT_LOOKBACK_BLOCKS", "") or DEFAULT_LOOKBACK_BLOCKS)
    except ValueError:
        want = DEFAULT_LOOKBACK_BLOCKS
    return max(1, min(want, MAX_LOOKBACK_BLOCKS))


def _is_range_refusal(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(marker in msg for marker in _RANGE_REFUSALS)


def _scan_debit_logs(client: "httpx.Client", urls: list[str], escrow: str,
                     lo: int, hi: int) -> list[dict]:
    """ChannelDebited logs over [lo, hi], in chunks the endpoint will actually serve.

    Asking for the whole span in one request is what limited this probe to 50 blocks: the
    widest window ANY public endpoint refuses is the width the code had to assume. Walking
    it in LOG_CHUNK_BLOCKS steps — halving on a range refusal, down to LOG_CHUNK_MIN — lets
    the same code read hours of history from a generous endpoint and still work against
    1rpc.io. A chunk that fails for any OTHER reason is skipped rather than fatal: this is
    a probe, and a partial window beats blanking the node.
    """
    out: list[dict] = []
    step = LOG_CHUNK_BLOCKS
    cur = lo
    while cur <= hi:
        end = min(cur + step - 1, hi)
        try:
            got = _rpc(client, urls, "eth_getLogs", [{
                "address": escrow,
                "fromBlock": hex(cur),
                "toBlock": hex(end),
                "topics": [[EV_CHANNEL_DEBITED]],
            }]) or []
        except Exception as exc:
            if _is_range_refusal(exc) and step > LOG_CHUNK_MIN:
                step = max(LOG_CHUNK_MIN, step // 2)
                continue                   # same `cur`, narrower window
            # Any other failure: stop and return what the earlier chunks gave. If that is
            # nothing, `out` is already empty and the caller shows the node without a
            # window rather than blanking it.
            break
        out.extend(g for g in got if isinstance(g, dict))
        cur = end + 1
    return out


def signer_address() -> str:
    """The hub's on-chain identity — the address that signs and is paid at settle.

    Read from the same env the hub uses. Empty is a legitimate answer: a deployment that has
    not enabled the bridge has no such address, and the node then reports what the escrow
    holds without claiming a collector.
    """
    return (os.environ.get("AIMARKET_ESCROW_HUB_ADDRESS") or "").strip()


def escrow_address() -> str:
    addr = (os.environ.get("AIMARKET_ESCROW_CONTRACT")
            or os.environ.get("AIMARKET_ESCROW_EVM_ADDRESS") or "").strip()
    if addr:
        return addr
    return _chain_address("AIMarketEscrow")


def usdc_address() -> str:
    return _chain_address("USDC")


def _chain_address(name: str) -> str:
    """chain_net keys its map by CONTRACT NAME (`AIMarketEscrow`, `USDC`), not by role.

    Note `chain_net.network()` takes an id and `active_network()` returns a NetworkSpec, so
    passing one to the other raises — and an `except: return ""` around it turned that bug into
    a silently address-less node that reported "chain unreadable" forever. Resolve with no
    argument and let a genuine failure surface as an empty string, which the caller reports as
    "not configured" rather than as a zero.
    """
    try:
        from chain_metrics import our_chain_addresses

        # Our registry is ours: a foreign deployment gets no default contract address.
        return str(our_chain_addresses().get(name, ""))
    except Exception:
        return ""


def escrow_public_url() -> str:
    """Basescan link for the escrow. Uses chain_net's explorer template so a different
    network draws the right explorer rather than a hard-coded Basescan URL."""
    return _explorer_address(escrow_address())


def collector_public_url() -> str:
    return _explorer_address(signer_address())


def _explorer_address(address: str) -> str:
    if not address:
        return ""
    try:
        tx_template = chain_net.network().explorer_tx or ""
    except Exception:
        tx_template = ""
    base = tx_template.split("/tx/")[0] if "/tx/" in tx_template else "https://basescan.org"
    return f"{base}/address/{address}"


def _decode_debit(log: dict) -> dict[str, Any]:
    """amount and remaining from a ChannelDebited log. channelId is indexed, so it is a topic."""
    data = (log.get("data") or "0x")[2:]
    words = [data[i * 64:(i + 1) * 64] for i in range(len(data) // 64)]
    amount = int(words[0], 16) if words else 0
    topics = log.get("topics") or []
    return {
        "channel_id": topics[1] if len(topics) > 1 else "",
        "amount_units": amount,
        "amount_usd": round(amount / 10 ** USDC_DECIMALS, 6),
        "tx_hash": log.get("transactionHash") or "",
        "block": int(str(log.get("blockNumber") or "0x0"), 16),
    }


def _rpc(client: "httpx.Client", urls: list[str], method: str, params: list) -> Any:
    """One JSON-RPC call with failover, synchronously.

    Sync on purpose. The first version was async and the sync wrapper called `asyncio.run`,
    which RAISES inside a running loop — so in the server's async topology path the poller
    returned None on every tick and the node kept whatever it had read once at startup. The
    other satellite pollers in this backend are blocking for exactly this reason.
    """
    last: Exception | None = None
    for url in urls:
        try:
            resp = client.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method,
                                          "params": params},
                               headers={"content-type": "application/json"})
            body = resp.json()
            if isinstance(body, dict) and body.get("error"):
                last = RuntimeError(str(body["error"])[:160])
                continue
            return body.get("result") if isinstance(body, dict) else None
        except Exception as exc:  # try the next endpoint
            last = exc
    raise last or RuntimeError("no RPC endpoints configured")


def _erc20_balance_sync(client, urls: list[str], token: str, holder: str) -> float:
    raw = _rpc(client, urls, "eth_call",
               [{"to": token, "data": call_data("70a08231", addr_arg(holder))}, "latest"])
    return round(decode_uint(str(raw)) / 10 ** USDC_DECIMALS, 6)


def fetch_settlement_status(escrow: str = "", rpc_urls: list[str] | None = None,
                            collector: str | None = None, chain_label: str = ""
                            ) -> dict[str, Any] | None:
    """Collected-so-far, from the escrow's own state. None when chain is unreadable.

    None rather than zeros: "nothing has been collected" and "the RPC did not answer" look
    identical as a number and mean opposite things.

    ``escrow``/``rpc_urls`` are explicit so the UNI mode can point this at the universe's own
    chain. Mixing one world's address with another world's RPC reads a contract that is not
    there and reports 0 — which is what the first version did.
    """
    spec = chain_net.network()
    custom = bool(escrow or rpc_urls)
    escrow = escrow or escrow_address()
    urls = list(rpc_urls or spec.rpc_urls)
    if not escrow or not urls:
        return None
    # UNI has its own escrow on its own chain and NO policy signer, so there is no collector to
    # describe. Reading a Base address's balance on the universe chain returns 0, which then
    # looks exactly like "the collector is out of gas" — a false alarm on a node whose whole
    # job is to make the real one legible.
    signer = signer_address() if collector is None else collector
    label = chain_label or ("universe" if custom else spec.id)

    with httpx.Client(timeout=6.0) as client:
        try:
            head = int(str(_rpc(client, urls, "eth_blockNumber", [])), 16)
            logs = _scan_debit_logs(client, urls, escrow,
                                    max(0, head - lookback_blocks()), head)
        except Exception:
            # The window is a nice-to-have; the state reads below are the point. Losing the
            # probe must not blank the node.
            logs = []
            head = 0

        debits = [_decode_debit(lg) for lg in logs]
        debits.sort(key=lambda d: d["block"])
        recent_units = sum(d["amount_units"] for d in debits)

        held_usd = unswept_usd = None
        gas_wei = None
        usdc = usdc_address()
        try:
            if usdc:
                held_usd = _erc20_balance_sync(client, urls, usdc, escrow)
                if signer:
                    unswept_usd = _erc20_balance_sync(client, urls, usdc, signer)
            if signer:
                gas_wei = int(str(_rpc(client, urls, "eth_getBalance", [signer, "latest"])), 16)
        except Exception:
            pass

    if held_usd is None and gas_wei is None:
        # Nothing at all was readable: say so rather than draw an empty node as an idle one.
        return None

    return {
        "chain": label,
        "escrow": escrow,
        "collector": signer,
        "escrow_held_usd": held_usd,
        "collected_unswept_usd": unswept_usd,
        "collector_gas_wei": gas_wei,
        "collector_gas_eth": None if gas_wei is None else round(gas_wei / 10 ** 18, 9),
        "gas_low": None if gas_wei is None else gas_wei < GAS_LOW_WEI,
        "recent_window_blocks": lookback_blocks(),
        "recent_debits": len(debits),
        "recent_debits_usd": round(recent_units / 10 ** USDC_DECIMALS, 6),
        "last_debit": debits[-1] if debits else None,
        "historical_total_available": False,
        "historical_total_note": (
            "public RPCs cap eth_getLogs at 50 blocks; a lifetime total needs an indexer"
        ),
        "pending_visible_here": False,
        "pending_note": (
            "a buyer-signed authorization is invisible on chain until it is submitted; the "
            "queue lives in the hub's admin route and is not published here"
        ),
    }


@ttl_cached(ttl_s=30.0, env_var="ALIEN_SETTLEMENT_TTL_S")
def fetch_settlement_status_sync(escrow: str = "", rpc: str = "",
                                 collector: str | None = None) -> dict[str, Any] | None:
    """Cached entry point for the topology tick. Keyed on its arguments, so UNI and LIVE do
    not share one cache slot."""
    try:
        return fetch_settlement_status(escrow=escrow, rpc_urls=[rpc] if rpc else None,
                                       collector=collector)
    except Exception:
        return None


def apply_settlement_to_nodes(nodes: list[dict[str, Any]], status: dict[str, Any] | None) -> None:
    """Overlay onto the `settlement` node. Unknown stays unknown — never a zero."""
    node = next((n for n in nodes if n.get("id") == "settlement"), None)
    if node is None:
        return
    metrics = node.setdefault("metrics", {})
    if not status:
        node["status"] = "offline"
        node["detail_unavailable"] = "escrow state could not be read"
        return

    for key in ("escrow_held_usd", "collected_unswept_usd", "collector_gas_eth"):
        if status.get(key) is not None:
            metrics[key] = status[key]
    metrics["recent_debits"] = status["recent_debits"]
    node["settlement"] = status
    node.pop("detail_unavailable", None)

    # A collector with no gas cannot collect, and that reads as "quiet" unless it is said.
    if status.get("collector") and status.get("gas_low"):
        node["status"] = "degraded"
    elif status["recent_debits"] > 0:
        node["status"] = "active"
    elif status.get("collected_unswept_usd"):
        # Nothing in the window, but revenue is sitting on the collector: it worked recently.
        node["status"] = "online"
    else:
        node["status"] = "idle"


def apply_settlement_graph(nodes: list[dict[str, Any]], *, mode: str = "real",
                           escrow: str = "", rpc: str = "",
                           collector: str | None = None) -> None:
    """Overlay for either world. UNI passes its own escrow and RPC; LIVE passes neither and
    gets chain_net's active network."""
    _ = mode
    apply_settlement_to_nodes(
        nodes,
        fetch_settlement_status_sync(escrow=escrow, rpc=rpc,
                                     collector="" if (escrow or rpc) else collector))
