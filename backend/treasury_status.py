"""Poll the MOMUS Treasury service for the Alien Monitor ``treasury`` node.

The Treasury is the separate payer. This poller reads its public, read-only surface to show the
payout ledger tail and — importantly — its treasury public key, which a viewer can confirm is
NOT the MOMUS scanner key. Best-effort and offline-safe.

It also reads the **balance across every settlement tier**, because a treasury without a balance
is the least interesting treasury there is. Three tiers, three different sources, three different
truths — and each one degrades on its own:

    UNI     the simulated vault, read from the Treasury's ``/vault`` over **loopback**. That route
            is deliberately NOT in the public read-only proxy allow-list (the one process that can
            release money gets no open endpoint); the monitor runs ``network_mode: host`` on the
            same machine, so it reads 127.0.0.1 directly and never re-exposes it. Every figure is
            labelled SIMULATED: the loop runs, no value moves.
    BASE    the deployed ``BountySplitter`` on Base mainnet, read with the monitor's own chain
            helpers (chain_net RPC failover + onchain_reads encode/decode). Today it is 0 ETH /
            0 USDC, and that is the CORRECT state: on-chain bounty payout needs a second opt-in
            beyond enabling crypto (``MOMUS_BOUNTY_ONCHAIN=1`` **plus** a splitter address). The
            zero is measured, so it is shown — together with the reason it is zero.
    SOLANA  optional, not deployed. Reported as **not connected**, never as ``0``: zero would
            claim we looked at an account and found it empty. We never looked, because there is
            nothing to look at. (Configure an account and it becomes a real, measured read.)

The rule the whole block obeys: a figure appears only when something measured it. An unreachable
source says so and shows nothing — no last-known value, no placeholder, no zero standing in for
"we never asked". One dead source must never blank the other tiers.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx

import chain_net
import onchain_reads as oc
from poll_cache import ttl_cached

# The Treasury is NOT a separate public host: only its read-only audit surface is exposed, under
# the MOMUS domain at /treasury (see the nginx vhost). The payout path stays on loopback, because
# the one service that can release money should not have an open endpoint. So the poller reads
# https://momus.modelmarket.dev/treasury/{health,ledger}.
DEFAULT_TREASURY_URL = "https://momus.modelmarket.dev/treasury"
DEFAULT_PUBLIC_TREASURY_URL = "https://momus.modelmarket.dev/#treasury"
DEFAULT_TREASURY_GITHUB_URL = "https://github.com/alexar76/treasury"


def treasury_poll_url() -> str:
    return (os.environ.get("ALIEN_TREASURY_URL") or os.environ.get("TREASURY_URL")
            or DEFAULT_TREASURY_URL).rstrip("/")


def treasury_public_url() -> str:
    return (os.environ.get("ALIEN_PUBLIC_TREASURY_URL") or os.environ.get("TREASURY_PUBLIC_URL")
            or DEFAULT_PUBLIC_TREASURY_URL).rstrip("/")


def treasury_links() -> dict[str, str]:
    github = (os.environ.get("ALIEN_TREASURY_GITHUB_URL") or os.environ.get("TREASURY_GITHUB_URL")
              or DEFAULT_TREASURY_GITHUB_URL).rstrip("/")
    return {"landing": treasury_public_url(), "github": github, "docs": f"{github}#readme"}


@ttl_cached(env_var="ALIEN_TREASURY_CACHE_TTL")
def fetch_treasury_status_sync(*, base_url: str | None = None, timeout: float = 4.0) -> dict[str, Any] | None:
    root = (base_url or treasury_poll_url()).rstrip("/")
    try:
        with httpx.Client(timeout=timeout) as client:
            h = client.get(f"{root}/health")
            if h.status_code != 200 or not isinstance(h.json(), dict):
                return None
            health = h.json()
            ledger: list[dict[str, Any]] = []
            try:
                r = client.get(f"{root}/ledger", params={"limit": 20})
                if r.status_code == 200 and isinstance(r.json(), dict):
                    ledger = [e for e in (r.json().get("entries") or []) if isinstance(e, dict)][:20]
            except Exception:
                ledger = []
            return {"health": health, "ledger": ledger}
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# Settlement tiers — balance per tier, each with its own provenance
# ═══════════════════════════════════════════════════════════════════════════════

# Tier states. Three of them, because "we measured zero", "we could not reach the source" and
# "there is nothing to ask" are three different facts and the panel must never conflate them.
TIER_OK = "ok"                        # measured — figures are real
TIER_UNREACHABLE = "unreachable"      # source down — NO figures, not even a stale one
TIER_NOT_CONNECTED = "not_connected"  # nothing deployed — we never asked; this is not a zero

# The Treasury's own loopback address. /vault is not proxied publicly and must not become
# reachable through the monitor either: we read it, we publish the numbers, we never forward
# the endpoint.
DEFAULT_TREASURY_VAULT_URL = "http://127.0.0.1:9411"

# BountySplitter on Base mainnet (docs/onchain-journal.md). Deployed; unfunded on purpose.
BOUNTY_SPLITTER_BASE = "0x89A618F66767101B96977e536797838661A63426"

# On-chain balances change slowly and the monitor ticks every ~1.5s, so the chain tiers are read
# on a TTL. Each tier carries the timestamp of the read that produced it, so a figure is never
# shown without saying when it was measured.
DEFAULT_CHAIN_TTL_S = 45.0
_chain_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_evm_pool_cache: chain_net.RpcPool | None = None
_solana_pool_cache: chain_net.RpcPool | None = None


def treasury_vault_url() -> str:
    return (os.environ.get("ALIEN_TREASURY_VAULT_URL") or DEFAULT_TREASURY_VAULT_URL).rstrip("/")


def bounty_splitter_address() -> str:
    return (os.environ.get("ALIEN_BOUNTY_SPLITTER") or os.environ.get("MOMUS_BOUNTY_SPLITTER")
            or BOUNTY_SPLITTER_BASE).strip()


def solana_treasury_account() -> str:
    """The Solana treasury account, or "" when none is deployed (the normal case today)."""
    return (os.environ.get("ALIEN_TREASURY_SOLANA_ACCOUNT")
            or os.environ.get("MOMUS_BOUNTY_SOLANA_ACCOUNT") or "").strip()


def _chain_ttl() -> float:
    try:
        return float(os.environ.get("ALIEN_TREASURY_CHAIN_TTL", DEFAULT_CHAIN_TTL_S))
    except ValueError:
        return DEFAULT_CHAIN_TTL_S


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hex_int(value: Any) -> int:
    if isinstance(value, int):
        return value
    s = str(value or "0").strip()
    return int(s, 16) if s.startswith("0x") else int(s)


def _detail(exc: Exception) -> str:
    """A short, credential-free reason a read failed — safe to render in the panel."""
    return chain_net.scrub_secrets(f"{type(exc).__name__}: {exc}")[:160]


def _base_spec() -> chain_net.NetworkSpec:
    # testnet=False on purpose: the BountySplitter is on Base MAINNET, so AIMARKET_TESTNET must
    # not silently point this read at Sepolia and report someone else's balance as ours.
    return chain_net.network("base", testnet=False)


def _explorer_address_url(spec: chain_net.NetworkSpec, address: str) -> str:
    base = (spec.explorer_tx or "").split("/tx/")[0]
    return f"{base}/address/{address}" if base and address else ""


def _evm_pool() -> chain_net.RpcPool:
    """One cached pool, so its health/cooldown state survives across ticks and a dead endpoint
    fails fast instead of being re-probed every 1.5 seconds."""
    global _evm_pool_cache
    if _evm_pool_cache is None:
        _evm_pool_cache = chain_net.RpcPool(_base_spec(), timeout=3.0)
    return _evm_pool_cache


def _solana_pool() -> chain_net.RpcPool:
    global _solana_pool_cache
    if _solana_pool_cache is None:
        _solana_pool_cache = chain_net.RpcPool(chain_net.network("solana", testnet=False), timeout=3.0)
    return _solana_pool_cache


def fetch_vault_state_sync(*, base_url: str | None = None,
                           timeout: float = 3.0) -> tuple[dict[str, Any] | None, str]:
    """Read the UNI vault over loopback. Returns ``(state, "")`` or ``(None, reason)``."""
    root = (base_url or treasury_vault_url()).rstrip("/")
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(f"{root}/vault")
            if r.status_code != 200:
                return None, f"vault HTTP {r.status_code}"
            body = r.json()
        if not isinstance(body, dict):
            return None, "vault returned a non-object body"
        return body, ""
    except Exception as exc:  # noqa: BLE001 — offline is a state, not a crash
        return None, _detail(exc)


def _money(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value), 6)


def uni_tier(vault: dict[str, Any] | None, *, error: str = "") -> dict[str, Any]:
    """The simulated vault. ALWAYS flagged ``simulated`` — a balance shown without that word
    invites a reader to believe money moved."""
    tier: dict[str, Any] = {
        "tier": "uni", "label": "UNI", "simulated": True, "measured": False,
        "state": TIER_UNREACHABLE, "read_at": _now_iso(),
        "source": "treasury /vault (loopback)",
    }
    balance = _money((vault or {}).get("balance_usd")) if isinstance(vault, dict) else None
    if not isinstance(vault, dict) or balance is None:
        tier["detail"] = error or ("vault response has no balance_usd" if vault else "vault not read")
        return tier
    txs = vault.get("transactions")
    tier.update({
        "state": TIER_OK,
        "measured": True,
        "balance_usd": balance,
        "reserved_usd": _money(vault.get("reserved_usd")),
        "available_usd": _money(vault.get("available_usd")),
        "transactions": int(txs) if isinstance(txs, int) and not isinstance(txs, bool) else None,
        "settlement_mode": str(vault.get("settlement_mode") or "") or None,
    })
    return tier


def base_tier(*, pool: Any = None, address: str | None = None, usdc_address: str | None = None,
              settlement_mode: str | None = None) -> dict[str, Any]:
    """ETH + USDC held by the BountySplitter on Base mainnet.

    ``0 / 0`` is the expected reading, not a fault: enabling crypto alone never starts paying
    bounties — on-chain settlement needs ``MOMUS_BOUNTY_ONCHAIN=1`` plus a splitter address. The
    panel renders the zero together with that explanation. A pool may be injected for tests; when
    it is, the TTL cache is bypassed so a test always sees its own fake.
    """
    addr = (address or bounty_splitter_address()).strip()
    injected = pool is not None
    if not injected:
        cached = _chain_cache.get("base")
        if cached and (time.monotonic() - cached[0]) < _chain_ttl():
            return dict(cached[1])

    tier: dict[str, Any] = {
        "tier": "base", "label": "BASE", "simulated": False, "measured": False,
        "state": TIER_UNREACHABLE, "read_at": _now_iso(),
        "chain": "base", "chain_id": 8453, "address": addr,
        "eth": None, "usdc": None, "deployed": None,
        # Why a zero here is correct: the on-chain payout switch is a SECOND opt-in.
        "payout_optin_required": True,
        "settlement_mode": settlement_mode,
        "source": "Base mainnet · eth_getBalance + ERC-20 balanceOf",
        "errors": [],
    }
    spec: chain_net.NetworkSpec | None = None
    try:
        spec = _base_spec()
        tier["explorer"] = _explorer_address_url(spec, addr)
        if pool is None:
            pool = _evm_pool()
    except Exception as exc:  # noqa: BLE001 — no usable RPC config is "unreachable", not a crash
        tier["detail"] = _detail(exc)
        return tier
    if not addr.startswith("0x") or len(addr) != 42:
        tier["detail"] = "no valid BountySplitter address configured"
        return tier

    usdc = (usdc_address if usdc_address is not None else (spec.addresses.get("USDC") or "")).strip()
    try:
        tier["eth"] = round(_hex_int(pool.call("eth_getBalance", [addr, "latest"])) / 1e18, 9)
    except Exception as exc:  # noqa: BLE001
        tier["errors"].append(f"eth: {_detail(exc)}")
    try:
        code = pool.call("eth_getCode", [addr, "latest"])
        tier["deployed"] = bool(code and str(code) not in ("0x", "0x0"))
    except Exception as exc:  # noqa: BLE001
        tier["errors"].append(f"code: {_detail(exc)}")
    if usdc:
        try:
            data = oc.call_data(oc.SEL_BALANCE_OF, oc.addr_arg(addr))
            raw = pool.call("eth_call", [{"to": usdc, "data": data}, "latest"])
            tier["usdc"] = round(oc.decode_uint(raw) / 1e6, 6)
            tier["usdc_token"] = usdc
        except Exception as exc:  # noqa: BLE001
            tier["errors"].append(f"usdc: {_detail(exc)}")
    else:
        tier["errors"].append("usdc: no USDC address known for base")

    # Per-figure degradation: one failed call must not erase the figure the other one measured.
    if tier["eth"] is not None or tier["usdc"] is not None:
        tier["state"] = TIER_OK
        tier["measured"] = True
    else:
        tier["detail"] = tier["errors"][0] if tier["errors"] else "no reading"
    if not injected:
        _chain_cache["base"] = (time.monotonic(), dict(tier))
    return tier


def solana_tier(*, pool: Any = None, account: str | None = None) -> dict[str, Any]:
    """Solana is optional and currently not deployed → ``not connected``, never ``0``.

    Zero would claim we queried an account and found it empty. There is no account. If one is
    ever configured, this becomes a real ``getBalance`` read and the figure is measured.
    """
    acct = (account if account is not None else solana_treasury_account()).strip()
    tier: dict[str, Any] = {
        "tier": "solana", "label": "SOLANA", "simulated": False, "measured": False,
        "state": TIER_NOT_CONNECTED, "read_at": _now_iso(),
        "chain": "solana", "account": acct or None, "sol": None,
        "source": "no Solana treasury account deployed — never queried",
    }
    if not acct:
        return tier
    injected = pool is not None
    if not injected:
        cached = _chain_cache.get("solana")
        if cached and (time.monotonic() - cached[0]) < _chain_ttl():
            return dict(cached[1])
    tier["source"] = "Solana mainnet · getBalance"
    tier["state"] = TIER_UNREACHABLE
    try:
        if pool is None:
            pool = _solana_pool()
        result = pool.call("getBalance", [acct])
        lamports = (result or {}).get("value") if isinstance(result, dict) else result
        tier["sol"] = round(int(lamports) / 1e9, 9)
        tier["state"] = TIER_OK
        tier["measured"] = True
    except Exception as exc:  # noqa: BLE001
        tier["detail"] = _detail(exc)
    if not injected:
        _chain_cache["solana"] = (time.monotonic(), dict(tier))
    return tier


def treasury_tiers(*, vault_url: str | None = None, evm_pool: Any = None,
                   solana_pool: Any = None) -> list[dict[str, Any]]:
    """All three tiers, each read independently. A source that is down produces an
    ``unreachable`` tier — it never removes a tier and never blanks its neighbours."""
    def _safe(fn: Any, tier_id: str, label: str) -> dict[str, Any]:
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — defensive: a tier must not kill the panel
            return {"tier": tier_id, "label": label, "state": TIER_UNREACHABLE, "measured": False,
                    "simulated": tier_id == "uni", "read_at": _now_iso(), "detail": _detail(exc)}

    vault, err = fetch_vault_state_sync(base_url=vault_url)
    uni = _safe(lambda: uni_tier(vault, error=err), "uni", "UNI")
    mode = uni.get("settlement_mode")
    return [
        uni,
        _safe(lambda: base_tier(pool=evm_pool, settlement_mode=mode), "base", "BASE"),
        _safe(lambda: solana_tier(pool=solana_pool), "solana", "SOLANA"),
    ]


def _counts(ledger: list[dict[str, Any]]) -> dict[str, int]:
    c = {"paid": 0, "held": 0, "refused": 0}
    for e in ledger:
        if e.get("kind") == "decision":
            st = str(e.get("state"))
            if st in c:
                c[st] += 1
    return c


def apply_treasury_to_nodes(nodes: list[dict], status: dict[str, Any] | None, *,
                            public_url: str | None = None,
                            tiers: list[dict[str, Any]] | None = None) -> None:
    node = next((n for n in nodes if n.get("id") == "treasury"), None)
    if not node:
        return
    node["url"] = public_url or treasury_public_url()
    node["links"] = treasury_links()
    if not status:
        # The public audit surface is down. That hides the pubkey and the decision counters —
        # and NOTHING else: the tiers were read from their own sources and still render.
        node["status"] = "offline"
        node["metrics"] = {"paid": 0, "held": 0, "refused": 0}
        if tiers:
            node["treasury_live"] = {"health_online": False, "tiers": tiers}
        else:
            node.pop("treasury_live", None)
        return
    health = status.get("health") or {}
    ledger = status.get("ledger") or []
    counts = _counts(ledger)
    node["status"] = "active" if health.get("status") == "ok" else "idle"
    node["treasury_live"] = {
        "health_online": True,
        "version": health.get("version"),
        "treasury_pubkey": (health.get("treasury_pubkey") or "")[:24],
        "crypto_enabled": health.get("crypto_enabled"),
        "prod": health.get("prod"),
        "external_verifiers": len(health.get("external_verifiers") or []),
        "counts": counts,
        "ledger": ledger[:12],
        "tiers": tiers or [],
    }
    node["metrics"] = counts


def apply_treasury_graph(nodes: list[dict], *, mode: str = "real") -> None:
    _ = mode
    status = fetch_treasury_status_sync()
    apply_treasury_to_nodes(nodes, status, public_url=treasury_public_url(),
                            tiers=treasury_tiers())


def fill_treasury_sim_node(node: dict, *, tick: int = 0) -> None:
    """TEST mode: a synthetic Treasury. Every figure here is invented, so every figure here is
    flagged ``synthetic`` — on the tier itself, not only on the card — and the panel prints the
    word. A made-up balance that reads like a measurement is the exact lie this panel exists to
    avoid."""
    counts = {"paid": tick % 3, "held": 1, "refused": 0}
    node["url"] = treasury_public_url()
    node["links"] = treasury_links()
    node["status"] = "active"
    node["metrics"] = counts
    node["treasury_live"] = {
        "health_online": True,
        "synthetic": True,
        "treasury_pubkey": "sim",
        "registered_scanners": 1,
        "crypto_enabled": False,
        "write_gated": True,
        "counts": counts,
        "tiers": [
            {"tier": "uni", "label": "UNI", "state": TIER_OK, "simulated": True, "measured": False,
             "synthetic": True, "read_at": _now_iso(), "source": "TEST mode simulator",
             "balance_usd": 400.0, "reserved_usd": 150.0, "available_usd": 250.0,
             "transactions": 5, "settlement_mode": "uni"},
            {"tier": "base", "label": "BASE", "state": TIER_OK, "simulated": False,
             "measured": False, "synthetic": True, "read_at": _now_iso(),
             "source": "TEST mode simulator", "chain": "base", "chain_id": 8453,
             "address": BOUNTY_SPLITTER_BASE, "eth": 0.0, "usdc": 0.0, "deployed": True,
             "payout_optin_required": True, "settlement_mode": "uni", "errors": []},
            # Even in TEST mode Solana stays "not connected": inventing a zero would teach the
            # reader to expect one in LIVE, where it would be a lie.
            {"tier": "solana", "label": "SOLANA", "state": TIER_NOT_CONNECTED, "simulated": False,
             "measured": False, "synthetic": True, "read_at": _now_iso(),
             "account": None, "sol": None, "chain": "solana",
             "source": "no Solana treasury account deployed — never queried"},
        ],
    }
