"""
On-chain metrics for Alien Monitor LIVE (real) mode.

Reads RPC URLs and contract addresses from the same env vars as AI-Factory /
aimarket-hub (.env in repo root). Uses JSON-RPC via httpx — no hard dependency
on web3.py for LIVE polling.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any

import httpx

# Unified multi-chain registry + RPC failover. Vendored verbatim from
# aimarket-hub/aimarket_hub/chain_net.py (kept in sync by tests/test_chain_net_parity.py),
# because alien-monitor is a standalone service with no hard dep on aimarket_hub.
# Per-chain RPC env keys (BASE_RPC_URL, ETHEREUM_RPC_URL, …) are resolved inside chain_net.
import chain_net
from poll_cache import ttl_cached
# The bubble's chain id lives with the per-node on-chain refs that already use it, so the
# monitor states it in exactly one place.
from onchain_refs import UNI_CHAIN_ID


def _strip_addr(val: str) -> str:
    return (val or "").strip().strip('"').strip("'")


def _dedupe_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        k = (u or "").rstrip("/")
        if k and k not in seen:
            seen.add(k)
            out.append(u)
    return out


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
    # Default to the ecosystem-wide active EVM network (chain_net; default Base).
    active = chain_net.active_network()
    return active.id if active.is_evm else "base"


def _generic_evm_overrides() -> list[str]:
    """Chain-AGNOSTIC RPC overrides. These name an endpoint without saying which chain it is.

    In practice they are the bubble's own Anvil: that is what every monitor deployment puts
    there. So they are the right answer for the bubble and the wrong one for "the network in
    settings" — honouring them for a LIVE monitor is exactly how a panel headed "Base" ended
    up rendering chain 31337. Point a LIVE monitor at your own node with the chain-scoped env
    instead (BASE_RPC_URL / AIMARKET_RPC_BASE / …, resolved inside chain_net).
    """
    urls: list[str] = []
    for key in ("ALIEN_EVM_RPC", "EVM_RPC", "EVM_RPC_URL"):
        v = (os.environ.get(key) or "").strip()
        if v:
            urls.append(v)
    return urls


def _chain_scoped_overrides(chain: str) -> list[str]:
    """Overrides that name the chain they belong to, so they can never be mistaken for another."""
    urls: list[str] = []
    nft_chain = (os.environ.get("AIMARKET_NFT_CHAIN") or "").strip().lower()
    nft_rpc = (os.environ.get("AIMARKET_NFT_CHAIN_RPC") or "").strip()
    if nft_rpc and chain == nft_chain:
        urls.append(nft_rpc)
    return urls


def _monitor_evm_overrides(chain: str) -> list[str]:
    """alien-monitor-specific RPC overrides, used as the preferred default ahead of chain_net."""
    return _generic_evm_overrides() + _chain_scoped_overrides(chain)


def evm_rpc_urls_for_chain(chain: str) -> list[str]:
    """Priority-ordered EVM RPC URLs: monitor overrides → chain_net (operator env + presets)."""
    chain = chain.strip().lower()
    urls = _monitor_evm_overrides(chain)
    try:
        urls += list(chain_net.network(chain).rpc_urls)
    except chain_net.ChainNetError:
        pass
    return _dedupe_urls(urls)


def evm_rpc_for_chain(chain: str) -> str | None:
    """Back-compat single-URL accessor — the highest-priority endpoint, or None."""
    urls = evm_rpc_urls_for_chain(chain)
    return urls[0] if urls else None


def solana_rpc_urls() -> list[str]:
    """Priority-ordered Solana RPC URLs: monitor override → chain_net (operator env + presets)."""
    urls: list[str] = []
    v = (os.environ.get("ALIEN_SOLANA_RPC") or "").strip()
    if v:
        urls.append(v)
    try:
        urls += list(chain_net.network("solana").rpc_urls)
    except chain_net.ChainNetError:
        pass
    return _dedupe_urls(urls)


def solana_rpc_url() -> str:
    """Back-compat single-URL accessor — the highest-priority Solana endpoint."""
    urls = solana_rpc_urls()
    return urls[0] if urls else "https://api.mainnet-beta.solana.com"


def our_chain_addresses(net_id: str | None = None) -> dict[str, str]:
    """The address registry, but only where it describes THIS deployment.

    `chain_net` is a verbatim vendored copy of the canonical module, and it ships the
    registry for the chain deployment WE run on Base — our escrow, our lottery, our
    capability NFT. On a Monitor pointed at somebody else's hub those are not defaults, they
    are a claim about another operator's money: turn crypto on there and the map reads our
    escrow's balance and draws it as theirs. So the policy lives here, in the consumer the
    Monitor owns, rather than as a fork of the vendored file.
    """
    from deployment_profile import owns_builtin_shelf

    if not owns_builtin_shelf():
        return {}
    try:
        return dict(chain_net.network(net_id or primary_evm_chain()).addresses or {})
    except chain_net.ChainNetError:
        return {}


#: Anvil/Hardhat's published accounts (the "test test … junk" mnemonic). These are nobody's
#: wallet: the key is in every README on the internet.
_DEV_RECIPIENTS = {
    "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
    "0x70997970c51812dc3a010c7d01b50e0d17dc79c8",
    "0x3c44cdddb6a900fa2b585dd299e03d12fa4293bc",
    "0x90f79bf6eb2c4f870365e785982e1f101e93b906",
    "0x15d34aaf54267db7d7c367839aaf71a00a2c6a65",
    "0x9965507d1a55bcc2695c58ba16fb37d819b0a4dc",
    "0x976ea74026e726554db657fa54763abd0c3a0aa9",
}


def payment_recipient() -> str:
    """Where this deployment's payments land — the HUB's fact, not the monitor's.

    The monitor only draws it (address + balance on the settlement panel), so it has no business
    being the source of truth: `AIMARKET_PAYMENT_RECIPIENT` was hand-copied into this container
    and the LIVE monitor spent its life advertising Anvil account 0 as the recipient of real
    money. Order now:

      1. what the HUB declares in its public well-known (`payment.recipient`) — one owner;
      2. the env, for an operator who runs a monitor beside a hub that does not publish it;
      3. nothing. An unknown recipient is drawn as unknown.

    And a well-known dev-chain account is never shown as the recipient on a public chain — the
    hub itself refuses to run that way (`config.is_dev_chain_address`), so the map must not
    quietly claim otherwise. It is reported as a misconfiguration instead.
    """
    declared = _hub_declared_recipient()
    env = _strip_addr(os.environ.get("AIMARKET_PAYMENT_RECIPIENT") or "")
    addr = declared or env
    if not addr:
        return ""
    src = chain_source()
    if src.get("source") == "settings-network" and addr.lower() in _DEV_RECIPIENTS:
        return ""       # see recipient_warning(): stated, not silently displayed
    return addr


def recipient_warning() -> str:
    """Why the settlement panel shows no recipient, when the reason is a bad one."""
    env = _strip_addr(os.environ.get("AIMARKET_PAYMENT_RECIPIENT") or "")
    if not env or env.lower() not in _DEV_RECIPIENTS:
        return ""
    if chain_source().get("source") != "settings-network":
        return ""
    net = active_network_info().get("name") or "this network"
    return (f"AIMARKET_PAYMENT_RECIPIENT={env} is a published Anvil/Hardhat test account, and "
            f"this monitor is reading {net} — nobody would receive those payments, so it is not "
            "drawn as the recipient. Set the hub's real recipient (or let the hub declare it).")


def _hub_declared_recipient() -> str:
    """The recipient from the hub's own well-known, cached — empty on hubs that do not publish
    it yet, which is why the env stays a fallback rather than being deleted."""
    if (os.environ.get("ALIEN_HUB_RECIPIENT_LOOKUP", "1").strip().lower()
            in ("0", "false", "no", "off")):
        return ""
    try:
        return _fetch_hub_recipient()
    except Exception:  # noqa: BLE001 - a panel field may never break the panel
        return ""


@ttl_cached(ttl_s=300)
def _fetch_hub_recipient() -> str:
    """One short, cached read of the hub's public well-known.

    On the request path, so: 3s budget, 5 minutes of cache, and every failure is "the hub does
    not say", never an error — the recipient is a label on a panel, not a reason to fail a route.
    """
    base = (os.environ.get("HUB_URL") or "").strip().rstrip("/")
    if not base:
        return ""
    try:
        with httpx.Client(timeout=3.0) as client:
            r = client.get(f"{base}/.well-known/ai-market.json")
        if r.status_code != 200:
            return ""
        doc = r.json()
    except Exception:  # noqa: BLE001
        return ""
    pay = doc.get("payment") if isinstance(doc, dict) else None
    if not isinstance(pay, dict):
        return ""
    return _strip_addr(str(pay.get("recipient") or pay.get("payment_recipient") or ""))


def configured_contracts() -> dict[str, str | None]:
    # Demo defaults for the active EVM chain (chain_net; Base ships our live demo contracts),
    # so the monitor shows the real deployment out of the box. Env always wins, and off our
    # own map there are no defaults at all — see our_chain_addresses.
    demo = our_chain_addresses()
    escrow = _strip_addr(
        os.environ.get("AIMARKET_ESCROW_EVM_ADDRESS")
        or os.environ.get("AIFACTORY_AI_MARKET_CONTRACT")
        or ""
    ) or demo.get("AIMarketEscrow") or ""
    nft = _strip_addr(
        os.environ.get("AIMARKET_NFT_CONTRACT")
        or os.environ.get("AIMARKET_NFT_CONTRACT_ADDRESS")
        or ""
    ) or demo.get("AIMarketCapabilityNFT") or ""
    lottery = _strip_addr(
        os.environ.get("AIMARKET_LOTTERY_EVM_ADDRESS")
        or os.environ.get("AIMARKET_LOTTERY_CONTRACT")
        or ""
    ) or demo.get("AIAgentLottery") or ""
    # Solana escrow program exists in source but is not part of the live demo → no default.
    sol_program = _strip_addr(os.environ.get("AIMARKET_ESCROW_SOLANA_PROGRAM_ID") or "")
    recipient = payment_recipient()
    return {
        "escrow_evm": escrow or None,
        "nft_evm": nft or None,
        "lottery_evm": lottery or None,
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
        headers={"User-Agent": chain_net.user_agent(), "Accept": "application/json"},
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("error"):
        raise RuntimeError(payload["error"])
    return payload.get("result")


async def _json_rpc_failover(
    client: httpx.AsyncClient,
    urls: list[str],
    method: str,
    params: list[Any],
) -> tuple[str, Any]:
    """Try each url in priority order (preferred default first) until one answers; return
    (winning_url, result). Raises the last error if all fail. The winning url is then pinned
    for the remaining calls in a snapshot — so we don't split a read across nodes."""
    last_err: Exception | None = None
    for url in urls:
        try:
            return url, await _json_rpc(client, url, method, params)
        except Exception as exc:  # transport/RPC error → fail over to the next endpoint
            last_err = exc
            continue
    raise last_err or RuntimeError("no RPC endpoints configured")


#: ERC-20 decimals are immutable, so one read per token per process is enough.
_erc20_decimals_cache: dict[str, int] = {}


async def _erc20_decimals(client: httpx.AsyncClient, rpc_url: str, token: str) -> int:
    """``decimals()`` for an ERC-20, defaulting to 6 (USDC) when the call fails.

    Read rather than assumed: an operator who repoints the registry's USDC entry at an
    18-decimal token would otherwise see a TVL a trillion times too large.
    """
    key = token.lower()
    if key in _erc20_decimals_cache:
        return _erc20_decimals_cache[key]
    from onchain_reads import SEL_DECIMALS, call_data, decode_uint

    try:
        raw = await _json_rpc(
            client, rpc_url, "eth_call", [{"to": token, "data": call_data(SEL_DECIMALS)}, "latest"]
        )
        decimals = decode_uint(raw)
        if not 0 < decimals <= 36:
            decimals = 6
    except Exception:
        decimals = 6
    _erc20_decimals_cache[key] = decimals
    return decimals


async def fetch_evm_metrics(
    client: httpx.AsyncClient,
    *,
    chain: str,
    rpc_urls: list[str],
    contracts: dict[str, str | None],
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "chain": chain,
        "rpc": rpc_urls[0] if rpc_urls else "",
        "connected": False,
        "errors": [],
        "contracts": {},
    }
    if not rpc_urls:
        out["errors"].append(f"evm rpc ({chain}): no endpoints configured")
        return out
    try:
        # Find the highest-priority endpoint that answers, then pin it for the rest.
        rpc_url, chain_id_hex = await _json_rpc_failover(client, rpc_urls, "eth_chainId", [])
        block_hex = await _json_rpc(client, rpc_url, "eth_blockNumber", [])
        gas_hex = await _json_rpc(client, rpc_url, "eth_gasPrice", [])
        out["rpc"] = rpc_url
        out.update(
            {
                "connected": True,
                "block": _hex_to_int(block_hex),
                "gas_gwei": round(_hex_to_int(gas_hex) / 1e9, 4),
                "chain_id": _hex_to_int(chain_id_hex),
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

    # Escrow TVL — the settlement token actually held by the escrow, read on-chain.
    # Nothing populated `chain["escrow"]` before this: build_real_summary looked for it,
    # found nothing, and reported TVL $0.00 no matter what the contract held. The native
    # reads in onchain_reads.py existed but had no caller outside the tests.
    escrow_addr = contracts.get("escrow_evm") or ""
    token_addr = (our_chain_addresses().get("USDC") or "").strip()
    if (
        escrow_addr.startswith("0x")
        and len(escrow_addr) >= 42
        and token_addr.startswith("0x")
        and len(token_addr) >= 42
    ):
        try:
            from onchain_reads import SEL_BALANCE_OF, addr_arg, call_data, decode_uint

            decimals = await _erc20_decimals(client, rpc_url, token_addr)
            raw = await _json_rpc(
                client,
                rpc_url,
                "eth_call",
                [
                    {"to": token_addr, "data": call_data(SEL_BALANCE_OF, addr_arg(escrow_addr))},
                    "latest",
                ],
            )
            out["escrow_tvl_usd"] = round(decode_uint(raw) / (10 ** decimals), 6)
            out["escrow_tvl_token"] = "USDC"
            out["escrow_tvl_token_address"] = token_addr
        except Exception as exc:
            out["errors"].append(f"escrow TVL read failed: {exc}")

    return out


async def fetch_solana_metrics(
    client: httpx.AsyncClient,
    *,
    rpc_urls: list[str],
    program_id: str | None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "rpc": rpc_urls[0] if rpc_urls else "",
        "connected": False,
        "errors": [],
        "program": None,
    }
    if not rpc_urls:
        out["errors"].append("solana rpc: no endpoints configured")
        return out
    try:
        rpc_url, slot = await _json_rpc_failover(client, rpc_urls, "getSlot", [])
        height = await _json_rpc(client, rpc_url, "getBlockHeight", [])
        out["rpc"] = rpc_url
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


# --- Which chain does this monitor read? -------------------------------------------------
# The same policy as main.should_build_chain_context, in the one place both the scanner and
# the status panel resolve it: the bubble reads its own Anvil; a LIVE monitor reads a public
# chain ONLY when the ecosystem crypto switch is on, and shows the bubble's chain otherwise
# (an off switch is not a reason to show an empty explorer).
_CRYPTO_TRUTHY = {"1", "true", "yes", "on"}
#: The bubble's Anvil when nothing names it — the monitor starts one on this port itself.
UNI_DEFAULT_RPC = "http://127.0.0.1:8545"


def crypto_enabled() -> bool:
    """True only if the ecosystem crypto switch is explicitly on. Default OFF.

    Same env var and truthy rule as core/crypto_config (main.crypto_enabled delegates here).
    """
    return os.environ.get("AIFACTORY_CRYPTO_ENABLED", "0").strip().lower() in _CRYPTO_TRUTHY


def monitor_mode() -> str:
    return (os.environ.get("ALIEN_MODE") or "real").strip().lower()


def _chain_net_urls(chain: str) -> list[str]:
    try:
        return list(chain_net.network(chain).rpc_urls)
    except chain_net.ChainNetError:
        return []


def chain_source(mode: str | None = None, crypto_on: bool | None = None) -> dict[str, Any]:
    """The chain this monitor must read, its endpoints, and WHY that one.

    Returned `source` is what the panel shows the reader:
      * ``uni-bubble``       — the private Anvil (the bubble always; LIVE with crypto off);
      * ``settings-network`` — the EVM network configured for this deployment (Base today,
        whatever ``AIMARKET_PAYMENT_CHAIN``/chain_net says tomorrow).
    """
    mode = (mode or monitor_mode()).strip().lower()
    crypto_on = crypto_enabled() if crypto_on is None else crypto_on
    chain = primary_evm_chain()
    if mode == "universe" or not crypto_on:
        # Never fall through to a preset's public endpoints here: with crypto off, or inside
        # the bubble, "no local RPC configured" must stay local rather than quietly become
        # mainnet.
        urls = _generic_evm_overrides() or [UNI_DEFAULT_RPC]
        return {
            "source": "uni-bubble",
            "realm": "uni" if mode == "universe" else "live",
            "mode": mode,
            "crypto_enabled": crypto_on,
            "chain": "uni",
            "name": "UNI Anvil",
            "chain_id": _uni_chain_id(force=True),
            "urls": _dedupe_urls(urls),
        }
    net = active_network_info()
    return {
        "source": "settings-network",
        "realm": "live",
        "mode": mode,
        "crypto_enabled": True,
        "chain": net.get("id") or chain,
        "name": net.get("name") or chain.title(),
        "chain_id": net.get("chain_id"),
        "urls": _dedupe_urls(_chain_scoped_overrides(chain) + _chain_net_urls(chain)),
    }


def _uni_chain_id(force: bool = False) -> int | None:
    """The bubble's own chain id, when THIS monitor is the bubble (`force`: or is reading it).

    The hub makes the same swap through its realm seal (`chain_net.network` replaces the
    preset's chain id with `realm.uni_chain_id()`), but chain_net.py is vendored byte-identical
    into the monitor, where `aimarket_hub` does not exist — so the swap silently never happened
    here and the UNI panel advertised Base's 8453 over an Anvil answering 31337. The bubble
    deliberately keeps the network's NAME; only the id it claims has to be true.
    """
    if not force and monitor_mode() != "universe":
        return None
    raw = (os.environ.get("ALIEN_UNI_CHAIN_ID") or "").strip()
    return int(raw) if raw.isdigit() else UNI_CHAIN_ID


def active_network_info() -> dict[str, Any]:
    """The selected EVM network as surfaced to the UI (id, name, chainId, kind, testnet)."""
    chain = primary_evm_chain()
    try:
        net = chain_net.network(chain)
        info = {"id": net.id, "name": net.display_name, "chain_id": net.chain_id,
                "kind": net.kind, "testnet": net.testnet}
    except chain_net.ChainNetError:
        info = {"id": chain, "name": chain.title(), "chain_id": None, "kind": "evm",
                "testnet": False}
    uni = _uni_chain_id()
    if uni and info.get("kind") == "evm":
        info["chain_id"] = uni
        info["realm"] = "uni"
    return info


def declared_network_mismatch(observed_chain_id: Any,
                              source: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """The network this monitor SAYS it is on vs the one its RPC answers as.

    Both numbers were already in the payload and nothing compared them, so the LIVE monitor
    rendered a "Base" header over a local Anvil for as long as its RPC env pointed there —
    only the raw `evm.chain_id` field disagreed, and nobody reads a raw field. Say it out loud
    instead: this is exactly the class of drift the chain scanner was built to expose.
    """
    try:
        observed = int(observed_chain_id)
    except (TypeError, ValueError):
        return None
    if not observed:
        return None
    # Compare against the chain this monitor MEANT to read (chain_source), not against the
    # settings network unconditionally: a LIVE monitor with crypto off is showing the bubble
    # on purpose, and calling that a mismatch would train people to ignore the warning.
    net = source or active_network_info() or {}
    declared = net.get("chain_id")
    if not declared or int(declared) == observed:
        return None
    name = net.get("name") or net.get("id") or "the configured network"
    return {
        "declared_chain": net.get("chain") or net.get("id") or "",
        "declared_chain_id": int(declared),
        "observed_chain_id": observed,
        "message": (f"RPC answers as chainId {observed}, but this monitor is configured for "
                    f"{name} (chainId {declared}) — what you are looking at is NOT {name}"),
    }


async def fetch_onchain_snapshot(timeout: float = 8.0) -> dict[str, Any]:
    """Poll the configured EVM + Solana RPCs (with failover) and contract deployment status.

    ``timeout`` is a HARD TOTAL budget: per-call timeouts bound each request, and an outer
    wait_for bounds the whole snapshot, so even with every endpoint of every chain offline the
    call returns a degraded snapshot promptly instead of scaling with endpoint count.
    """
    try:
        return await asyncio.wait_for(_fetch_onchain_snapshot(timeout), timeout=timeout)
    except (asyncio.TimeoutError, TimeoutError):
        return {
            "primary_chain": primary_evm_chain(),
            "network": active_network_info(),
            "chain_source": {k: v for k, v in chain_source().items() if k != "urls"},
            "contracts": configured_contracts(),
            "evm": None,
            "solana": None,
            "errors": [f"on-chain snapshot exceeded total timeout ({timeout}s) — RPCs unreachable"],
        }


async def _read_lottery_snapshot(
    client: httpx.AsyncClient,
    rpc_urls: list[str],
    address: str,
    errors: list[str],
) -> dict[str, Any]:
    """Real lottery state from the deployed contract, or a read that says it failed.

    `read_ok` is what consumers gate on: the alternative to a real read is showing
    nothing, never a plausible-looking derivation (see lottery_layers).
    """
    from onchain_reads import make_caller, read_lottery, read_lottery_economy

    out: dict[str, Any] = {"address": address, "read_ok": False}
    try:
        call = make_caller(client, rpc_urls)
        usdc = (our_chain_addresses().get("USDC") or "").strip() or None
        lot = await read_lottery(call, address, usdc_addr=usdc)
        lot.update(
            await read_lottery_economy(
                call, address, round_id=int(lot.get("round") or 0),
                decimals=int(lot.get("decimals") or 6),
            )
        )
        out.update(lot)
        out["read_ok"] = True
    except Exception as exc:
        out["error"] = str(exc)
        errors.append(f"lottery read ({address}): {exc}")
    return out


async def _fetch_onchain_snapshot(timeout: float = 8.0) -> dict[str, Any]:
    chain = primary_evm_chain()
    # The scanner and this panel resolve the chain the same way, so they can never describe
    # two different chains to the same viewer.
    source = chain_source()
    evm_urls = source["urls"]
    contracts = configured_contracts()
    sol_urls = solana_rpc_urls()

    snapshot: dict[str, Any] = {
        "primary_chain": chain,
        "network": active_network_info(),
        "chain_source": {k: v for k, v in source.items() if k != "urls"},
        "contracts": contracts,
        "evm": None,
        "solana": None,
        "errors": [],
    }

    # Short per-call timeout so failing over across several dead endpoints stays bounded
    # (never hangs the snapshot when offline).
    per_call = min(timeout, 5.0)
    async with httpx.AsyncClient(timeout=per_call) as client:
        if evm_urls:
            snapshot["evm"] = await fetch_evm_metrics(
                client, chain=chain, rpc_urls=evm_urls, contracts=contracts
            )
            snapshot["errors"].extend(snapshot["evm"].get("errors") or [])
            mismatch = declared_network_mismatch((snapshot["evm"] or {}).get("chain_id"), source)
            if mismatch:
                snapshot["chain_mismatch"] = mismatch
                snapshot["errors"].append(mismatch["message"])
            # A recipient that was dropped for being a dev account must say so, or the panel
            # simply looks like it has no recipient configured.
            warn = recipient_warning()
            if warn:
                snapshot["errors"].append(warn)
            if "escrow_tvl_usd" in (snapshot["evm"] or {}):
                snapshot["escrow"] = {
                    "tvl_usd": snapshot["evm"]["escrow_tvl_usd"],
                    "token": snapshot["evm"].get("escrow_tvl_token") or "USDC",
                }
            lottery_addr = contracts.get("lottery_evm") or ""
            if (
                (snapshot["evm"] or {}).get("connected")
                and lottery_addr.startswith("0x")
                and len(lottery_addr) >= 42
            ):
                snapshot["lottery"] = await _read_lottery_snapshot(
                    client, evm_urls, lottery_addr, snapshot["errors"]
                )
        else:
            snapshot["errors"].append(
                f"No EVM RPC configured for chain {chain!r} "
                f"(set AIMARKET_RPC_{chain.upper()} or {chain.upper()}_RPC_URL or ALIEN_EVM_RPC)"
            )

        snapshot["solana"] = await fetch_solana_metrics(
            client,
            rpc_urls=sol_urls,
            program_id=contracts.get("escrow_solana"),
        )
        snapshot["errors"].extend(snapshot["solana"].get("errors") or [])

    return snapshot


# Human chain names by chainId — so the EVM node shows the chain it's ACTUALLY on
# (e.g. Base 8453), not a hardcoded "Ethereum".
_CHAIN_NAMES: dict[int, str] = {
    1: "Ethereum",
    8453: "Base",
    84532: "Base Sepolia",
    42161: "Arbitrum",
    10: "Optimism",
    137: "Polygon",
    11155111: "Sepolia",
}


def apply_chain_metrics_to_nodes(nodes: list[dict], chain: dict[str, Any]) -> None:
    """Merge on-chain snapshot into topology nodes (ethereum, escrows, nft)."""
    evm = chain.get("evm") or {}
    sol = chain.get("solana") or {}
    contracts_cfg = chain.get("contracts") or {}

    by_id = {n["id"]: n for n in nodes}

    if "ethereum" in by_id:
        if evm.get("connected"):
            by_id["ethereum"]["status"] = "active"
            cid = int(evm.get("chain_id", 0) or 0)
            # Relabel the node to the chain it is actually connected to (Base, not "Ethereum").
            by_id["ethereum"]["label"] = _CHAIN_NAMES.get(cid) or (evm.get("chain") or "EVM").title()
            by_id["ethereum"]["metrics"] = {
                "chain": evm.get("chain", ""),
                "chain_id": cid,
                "block": evm.get("block", 0),
                "gas": evm.get("gas_gwei", 0),
                "rpc": evm.get("rpc", ""),
            }
        else:
            # LIVE/UNI but this network isn't connected → show it explicitly offline
            # (greyed), not as a live participant.
            by_id["ethereum"]["status"] = "offline"
            by_id["ethereum"]["metrics"] = {"connected": 0}

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
                "tvl": float(evm.get("escrow_tvl_usd") or 0),
                "tvl_token": evm.get("escrow_tvl_token") or "USDC",
            }
            # active = contract code is on-chain; else fall back to chain reachability
            # (idle = chain up but escrow not deployed at that address; unknown = chain unreachable)
            by_id["evm_escrow"]["status"] = "active" if esc.get("deployed") else (
                "idle" if evm.get("connected") else "unknown"
            )
        elif evm.get("connected"):
            by_id["evm_escrow"]["status"] = "idle"
            by_id["evm_escrow"]["metrics"]["chain"] = evm.get("chain", "")
        else:
            # no escrow configured AND chain not connected → explicitly offline (greyed)
            by_id["evm_escrow"]["status"] = "offline"

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

    if "solana" in by_id:
        if sol.get("connected"):
            by_id["solana"]["status"] = "active"
            by_id["solana"]["metrics"] = {
                "slot": sol.get("slot", 0),
                "block_height": sol.get("block_height", 0),
                "tps": 0,
                "rpc": sol.get("rpc", ""),
            }
        else:
            # Solana not wired in this deployment (e.g. EVM-only UNI) → explicitly offline.
            by_id["solana"]["status"] = "offline"
            by_id["solana"]["metrics"] = {"connected": 0}

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
        else:
            # no Solana escrow program configured AND Solana not connected → explicitly offline
            by_id["solana_escrow"]["status"] = "offline"


def apply_onchain_native_to_nodes(nodes: list[dict], native: dict[str, Any]) -> None:
    """Overlay native-unit on-chain reads onto topology nodes (lottery, escrow, acex, nft)."""
    by_id = {n["id"]: n for n in nodes}
    lot = native.get("lottery")
    if isinstance(lot, dict) and "lottery" in by_id:
        m = by_id["lottery"].setdefault("metrics", {})
        m.pop("prize_pool_usd", None)
        m.pop("players", None)
        m["prize_pool_eth"] = float(lot.get("prize_pool") or 0)
        m["round"] = int(lot.get("round") or 0)
        m["tickets"] = int(lot.get("tickets") or 0)
        if "payouts_24h" not in m:
            m["payouts_24h"] = 0
    if "evm_escrow" in by_id:
        esc = by_id["evm_escrow"].setdefault("metrics", {})
        if "escrow_tvl" in native:
            esc["tvl"] = float(native["escrow_tvl"])
        if "escrow_channels" in native:
            esc["channels"] = int(native["escrow_channels"])
    if "acex" in by_id and "acex_tvl" in native:
        by_id["acex"].setdefault("metrics", {})["tvl"] = float(native["acex_tvl"])
    if "nft_contract" in by_id and "nft_minted" in native:
        by_id["nft_contract"].setdefault("metrics", {})["minted"] = int(native["nft_minted"])


def _summary_int(stats: dict[str, Any], *keys: str) -> int | None:
    """Read the first present integer field from a hub /stats/live summary dict."""
    for key in keys:
        if key not in stats:
            continue
        try:
            return int(stats[key])
        except (TypeError, ValueError):
            continue
    return None


def _summary_float(stats: dict[str, Any], *keys: str) -> float | None:
    """Read the first PRESENT numeric field from a hub /stats/live summary dict.

    Presence, not truthiness: a hub reporting ``volume_24h_usd: 0.0`` is stating that
    nothing was paid for in the window, and that answer must win over any fallback.
    """
    for key in keys:
        if key not in stats:
            continue
        try:
            return float(stats[key])
        except (TypeError, ValueError):
            continue
    return None


def _event_ts_epoch(ev: dict[str, Any]) -> float | None:
    """Epoch seconds for a hub event, or None when it carries no parseable time."""
    raw = str(ev.get("timestamp") or ev.get("ts") or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def hub_events_to_activity(hub_payload: dict[str, Any]) -> tuple[list[dict], dict[str, Any]]:
    """Map hub /stats/live JSON to monitor events + metric hints."""
    events_out: list[dict] = []
    hints: dict[str, Any] = {
        "invocations_24h": 0,
        "channels_open": 0,
        "volume_24h": 0,
        "volume_lifetime_usd": 0.0,
        "capabilities": 0,
        "peers": 0,
    }
    summary = hub_payload.get("summary") if isinstance(hub_payload, dict) else {}
    have_window_invocations = False
    have_window_volume = False
    if isinstance(summary, dict):
        # A 24h counter NEVER falls back to a lifetime one. Reading
        # `invocations_24h or total_invocations` meant a quiet day (0 is falsy) silently
        # promoted the hub's all-time count into a cell labelled "INVOCATIONS 24H" —
        # measured on the UNI map 2026-09-07: hub said invocations_24h=0, the panel
        # showed 215, every one of them from ten days earlier.
        inv_24h = _summary_int(summary, "invocations_24h")
        if inv_24h is not None:
            hints["invocations_24h"] = inv_24h
            have_window_invocations = True
        hints["channels_open"] = int(summary.get("open_channels") or summary.get("channels_open") or 0)
        caps = _summary_int(
            summary,
            "offerable_capabilities_count",
            "capabilities_count",
            "federated_capabilities_count",
            "capabilities",
        )
        if caps is not None:
            hints["capabilities"] = caps
        peer_n = _summary_int(summary, "peers_count", "peers")
        if peer_n is not None:
            hints["peers"] = peer_n
        # Volume inside the SAME window as the counter beside it. The channel figures
        # (`settled_volume_usd` / `closed_volume_usd`) carry no time window at all — they
        # are lifetime sums over the channel ledger — so they are kept, but as
        # `volume_lifetime_usd`, never as the 24h number.
        vol_24h = _summary_float(summary, "volume_24h_usd", "volume_24h", "volume_usd")
        if vol_24h is not None:
            hints["volume_24h"] = vol_24h
            have_window_volume = True
        hints["volume_lifetime_usd"] = _summary_float(
            summary,
            "volume_total_usd",
            "settled_volume_usd",
            "closed_volume_usd",
        ) or 0.0

    raw_events = hub_payload.get("events") if isinstance(hub_payload, dict) else []
    if not isinstance(raw_events, list):
        return events_out, hints

    window_start = datetime.now(timezone.utc).timestamp() - 86400
    window_volume = 0.0
    window_events = 0
    for i, ev in enumerate(raw_events[:20]):
        if not isinstance(ev, dict):
            continue
        amount = float(
            ev.get("amount_usd")
            or ev.get("price_usd")
            or ev.get("amount")
            or 0
        )
        ts_epoch = _event_ts_epoch(ev)
        if ts_epoch is not None and ts_epoch >= window_start:
            window_volume += amount
            window_events += 1
        # Prefer hub event time so the activity log scrolls when new invokes land.
        ts = ev.get("timestamp") or ev.get("ts") or datetime.now(timezone.utc).isoformat()
        events_out.append(
            {
                "id": str(ev.get("id") or f"hub_{i}"),
                "ts": ts,
                "agent": str(ev.get("consumer_hub") or ev.get("agent") or "hub-client"),
                "action": str(ev.get("action") or "invoke"),
                "target": str(ev.get("capability_id") or ev.get("target") or "hub"),
                "amount": amount,
                "token": str(ev.get("token") or "USDT"),
                "onchain": False,
            }
        )
    # Only for a hub too old to report a windowed figure: derive both from the events
    # page, and count ONLY events inside the window. The page is capped (50 rows), so this
    # can under-report — an honest floor beats a lifetime total under a 24h label.
    if not have_window_volume:
        hints["volume_24h"] = round(window_volume, 4)
    if not have_window_invocations:
        hints["invocations_24h"] = window_events
    return events_out, hints


def mesh_agent_count(mesh_stats: Any) -> int:
    """How many agents the service mesh reports, whatever it calls the field.

    The mesh answers `/v1/stats` with `agents_total` / `agents_verified`. The monitor read
    `agents` / `agents_online` — neither of which the mesh has ever emitted — so the LIVE
    dashboard showed AGENTS: 0 against a mesh holding three verified agents. Measured
    2026-09-05: `{"agents_total": 3, "agents_verified": 3, ...}` while the panel read zero.

    `agents_total` is what the counter is labelled: how many agents are in the mesh. The
    older names stay first so a mesh that does emit them still wins, and one function serves
    both readers so the next rename cannot fix one and miss the other.
    """
    if not isinstance(mesh_stats, dict):
        return 0
    for key in ("agents", "agents_online", "agents_total", "agents_verified"):
        value = mesh_stats.get(key)
        if value:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return 0


def _first_present_int(*values: Any) -> int | None:
    """The first value that is a real integer reading; None when nothing reported one."""
    for value in values:
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def build_real_summary(
    *,
    tick: int,
    hub_hints: dict[str, Any],
    mesh_stats: dict[str, Any] | None,
    chain: dict[str, Any],
    apps_online: int = 0,
) -> dict[str, Any]:
    evm = chain.get("evm") or {}
    sol = chain.get("solana") or {}
    agents = mesh_agent_count(mesh_stats)

    esc = (chain.get("escrow") or {}) if isinstance(chain, dict) else {}
    tvl = float(esc.get("tvl_usd") or esc.get("tvl") or hub_hints.get("tvl_usd") or 0)
    # No producer → None, so the panel can say "--". A confident 0 is a claim that
    # nothing happened on chain; LIVE has no transaction counter at all (the RPC reads
    # are block height and gas price), and reporting its absence as zero read as one.
    onchain_tx = _first_present_int(
        chain.get("tx_count"),
        evm.get("tx_count") if isinstance(evm, dict) else None,
        hub_hints.get("onchain_tx_count"),
    )

    return {
        "total_invocations_24h": hub_hints.get("invocations_24h", 0),
        "total_volume_usd": hub_hints.get("volume_24h", 0),
        # What window the two figures above describe, and the lifetime total that used
        # to be painted as the 24h one — kept so nothing is lost from the card.
        "volume_window": "24h",
        "volume_lifetime_usd": float(hub_hints.get("volume_lifetime_usd") or 0),
        "active_channels": hub_hints.get("channels_open", 0),
        "tvl_usd": tvl,
        "tvl_token": esc.get("token") or evm.get("escrow_tvl_token") or "USDC",
        "agents_online": agents,
        "apps_online": apps_online,
        "tps_solana": 0,
        "gas_gwei": evm.get("gas_gwei", 0),
        "gas_price_gwei": evm.get("gas_gwei", 0),
        "block_number": evm.get("block", 0),
        "onchain_tx_count": onchain_tx,
        "mode": "real",
        "tick": tick,
        "blockchain_ready": bool(evm.get("connected") or sol.get("connected")),
        "evm_chain": evm.get("chain") or chain.get("primary_chain"),
        "evm_rpc": evm.get("rpc"),
        "solana_rpc": sol.get("rpc"),
        "evm_chain_id": evm.get("chain_id"),
        "solana_slot": sol.get("slot"),
        # Selected network surfaced for the UI (so it shows e.g. "Base", not a guess).
        "network": chain.get("network") or {},
        "network_name": (chain.get("network") or {}).get("name")
        or (evm.get("chain") or chain.get("primary_chain") or "").title(),
    }
