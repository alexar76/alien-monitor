"""A stranger hub's on-chain declaration, checked against the chain before it is believed.

A federation is cyclic, so this map stops at the second hop and never fetches a peer's
peers. That bound is what keeps the graph finite — and it is also why a stranger hub used
to arrive as a name, a capability count and nothing else. Nothing about it could be
checked, so nothing about it could be trusted, so the honest thing was to leave it off the
map (see the sphere rule in ``hub_discovery``).

An on-chain declaration breaks that deadlock, because it is the one kind of claim a third
party can falsify without asking anybody. A hub now publishes the escrow it settles
through and the wallet it is paid to (``aimarket_hub/contracts_declaration.py``), each hub
re-exports what its peers declared, and this module does the only thing that turns a
declared address into evidence: it asks the chain.

Two questions, and they are cheap — one or two RPC calls per address, cached:

  * a contract — does the address hold code? An escrow that was never deployed holds none.
  * a wallet — has it ever transacted? ``eth_getTransactionCount`` on an EOA is its nonce.

Both answers come from the chain THIS monitor is already reading (``chain_metrics.
chain_source``). If the declaration names a chain we do not read, it is not verified —
not "assumed fine", not "probably real". We do not draw conclusions from chains we cannot
see, and the map says so.

What verification buys the reader is a sphere they can open: the address goes into the
node card with a link to this monitor's own scanner (``/api/chain/address/<addr>``) and to
the public explorer, so "some hub over there" becomes a contract whose transactions you
can read yourself.

Untrusted input throughout: every declaration is bounded and re-validated here even though
the publishing hub bounded it too. A monitor that trusts a stranger's JSON because a
stranger's hub said it was fine has not checked anything.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

MAX_ENTRIES = 8
_MAX_STR = 120
_MAX_ADDRESSES_PER_TICK = 24
_ALLOWED_ROLES = frozenset({"escrow", "wallet", "token", "registry", "lottery", "nft", "other"})

#: Verification outcomes, keyed by (chain_id, lowercase address). A deployment does not
#: change often and a tick is seconds, so re-asking every tick would be pure RPC load;
#: an hour is short enough that a redeploy is picked up while an operator is still watching.
_TTL_S = 3600.0
_NEGATIVE_TTL_S = 300.0  # a not-yet-deployed address may be deployed in a minute
_cache: dict[tuple[int, str], tuple[float, dict[str, Any]]] = {}
_RPC_TIMEOUT = 6.0


def _addr(value: Any) -> str:
    """An EVM address, or "". Anything else must never reach an RPC call or a browser."""
    text = str(value or "").strip()
    if len(text) != 42 or not text.startswith("0x"):
        return ""
    try:
        if int(text, 16) == 0:
            return ""
    except ValueError:
        return ""
    return text


def sanitize(raw: Any) -> dict[str, Any] | None:
    """Bound and validate a declaration read from a hub's well-known.

    Mirrors ``aimarket_hub.contracts_declaration.sanitize`` deliberately rather than
    importing it: the monitor must not depend on the hub package, and a validator that
    only runs on the publishing side is not a validator at all.
    """
    if not isinstance(raw, dict):
        return None
    entries: list[dict[str, Any]] = []
    for item in (raw.get("entries") or [])[: MAX_ENTRIES * 4]:
        if not isinstance(item, dict) or len(entries) >= MAX_ENTRIES:
            continue
        address = _addr(item.get("address"))
        if not address or any(e["address"].lower() == address.lower() for e in entries):
            continue
        role = str(item.get("role") or "other").strip().lower()[:20]
        entry: dict[str, Any] = {
            "role": role if role in _ALLOWED_ROLES else "other",
            "name": str(item.get("name") or "")[:_MAX_STR],
            "address": address,
        }
        # This URL is rendered as a link in an operator's browser. Only absolute http(s):
        # a `javascript:` "explorer" in a stranger's declaration is one click from the
        # monitor's own origin.
        explorer = str(item.get("explorer") or "").strip()[:300]
        if explorer.startswith(("http://", "https://")):
            entry["explorer"] = explorer
        note = str(item.get("note") or "")[:_MAX_STR]
        if note:
            entry["note"] = note
        entries.append(entry)
    if not entries:
        return None

    out: dict[str, Any] = {"version": 1, "entries": entries}
    chain = str(raw.get("chain") or "").strip().lower()[:32]
    if chain:
        out["chain"] = chain
    try:
        chain_id = int(raw.get("chain_id"))
    except (TypeError, ValueError):
        chain_id = 0
    if 0 < chain_id < 2**53:
        out["chain_id"] = chain_id
    network = str(raw.get("network") or "").strip()[:_MAX_STR]
    if network:
        out["network"] = network
    explorer = str(raw.get("explorer") or "").strip()[:300]
    if explorer.startswith(("http://", "https://")):
        out["explorer"] = explorer
    for flag in ("testnet", "simulated"):
        if bool(raw.get(flag)):
            out[flag] = True
    return out


def declarations_in(well_known: Any) -> dict[str, dict[str, Any]]:
    """Every declaration in one hub's well-known, keyed by whose it is.

    ``""`` is the hub's own; a peer's is keyed by its normalised URL, which is how the
    child node built from that peer entry finds it again.
    """
    if not isinstance(well_known, dict):
        return {}
    found: dict[str, dict[str, Any]] = {}
    own = sanitize(well_known.get("contracts"))
    if own:
        found[""] = own
    peers = well_known.get("peers")
    for peer in (peers if isinstance(peers, list) else [])[:64]:
        if not isinstance(peer, dict):
            continue
        declared = sanitize(peer.get("contracts"))
        if declared:
            found[str(peer.get("url") or "").rstrip("/").lower()] = declared
    return found


def _reading_chain() -> tuple[str, int | None, bool]:
    """(rpc url, chain id, is_simulated) for the chain this monitor actually reads."""
    try:
        from chain_metrics import chain_source

        source = chain_source()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("foreign contracts: no chain source (%s)", exc)
        return "", None, False
    urls = source.get("urls") or []
    chain_id = source.get("chain_id")
    return (
        str(urls[0]) if urls else "",
        int(chain_id) if isinstance(chain_id, int) else None,
        source.get("source") == "uni-bubble",
    )


async def _rpc(client: Any, url: str, method: str, params: list[Any]) -> Any:
    resp = await client.post(
        url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        timeout=_RPC_TIMEOUT,
    )
    resp.raise_for_status()
    body = resp.json()
    if isinstance(body, dict) and "error" in body:
        raise RuntimeError(str(body["error"])[:200])
    return (body or {}).get("result") if isinstance(body, dict) else None


async def _check_one(client: Any, url: str, chain_id: int, address: str,
                     role: str) -> dict[str, Any]:
    """Ask the chain about one address. Never raises: unknown is a valid answer."""
    key = (chain_id, address.lower())
    now = time.time()
    cached = _cache.get(key)
    if cached and cached[0] > now:
        return cached[1]
    result: dict[str, Any] = {"address": address, "verified": False, "reason": "unchecked"}
    try:
        code = str(await _rpc(client, url, "eth_getCode", [address, "latest"]) or "0x")
        has_code = len(code) > 2 and set(code[2:]) != {"0"}
        nonce_hex = await _rpc(client, url, "eth_getTransactionCount", [address, "latest"])
        try:
            nonce = int(str(nonce_hex or "0x0"), 16)
        except ValueError:
            nonce = 0
        result = {
            "address": address,
            "contract": has_code,
            "txs_sent": nonce,
            # A contract is evidence once it EXISTS: an escrow holding code was deployed by
            # someone who paid gas for it. A wallet has no code, so the only thing that makes
            # it more than a string is having transacted at least once.
            "verified": bool(has_code or nonce > 0),
            "reason": (
                "contract deployed" if has_code
                else f"wallet with {nonce} outgoing tx" if nonce > 0
                else "no code and no transactions"
            ),
            "chain_id": chain_id,
            "role": role,
            "checked_at": int(now),
        }
    except Exception as exc:
        # An RPC that failed says nothing about the address. Cached briefly so a flapping
        # endpoint cannot turn into a per-tick retry storm, and reported as unknown rather
        # than as absent — "we could not look" and "it is not there" are different claims.
        result = {"address": address, "verified": False, "reason": "rpc unavailable",
                  "error": str(exc)[:120], "chain_id": chain_id, "role": role}
        _cache[key] = (now + _NEGATIVE_TTL_S, result)
        return result
    _cache[key] = (now + (_TTL_S if result["verified"] else _NEGATIVE_TTL_S), result)
    return result


async def verify(client: Any, declarations: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Check every declared address we are able to check.

    Returns ``{lowercase address: evidence}`` for the addresses we asked about. An address
    on a chain this monitor does not read is absent from the result — deliberately, so a
    caller cannot mistake "not checkable here" for "checked and fine".
    """
    if not declarations:
        return {}
    url, our_chain_id, simulated = _reading_chain()
    if not url or our_chain_id is None:
        return {}
    wanted: dict[str, str] = {}  # address -> role
    for declaration in declarations.values():
        declared_chain = declaration.get("chain_id")
        if not isinstance(declared_chain, int) or declared_chain != our_chain_id:
            # Different chain (or unstated). We cannot see it, so we say nothing about it.
            continue
        if bool(declaration.get("simulated")) != simulated:
            # A simulated declaration read by a live monitor (or the reverse) would put
            # bubble money on the real map. The chain ids already differ in practice; this
            # is the check that does not depend on that staying true.
            continue
        for entry in declaration.get("entries") or []:
            address = _addr(entry.get("address"))
            if address and len(wanted) < _MAX_ADDRESSES_PER_TICK:
                wanted.setdefault(address, str(entry.get("role") or "other"))
    if not wanted:
        return {}
    results = await asyncio.gather(
        *(_check_one(client, url, our_chain_id, address, role)
          for address, role in wanted.items()),
        return_exceptions=True,
    )
    out: dict[str, dict[str, Any]] = {}
    for address, result in zip(wanted, results):
        if isinstance(result, dict):
            out[address.lower()] = result
    verified = sum(1 for r in out.values() if r.get("verified"))
    if out:
        logger.info(
            "foreign contracts: %d/%d declared address(es) verified on chain %s",
            verified, len(out), our_chain_id,
        )
    return out


def evidence_for(declaration: Any, verified: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """Fold verification back into one node's declaration, for the node card.

    The declaration travels with per-entry ``verified``/``reason`` so the card can show
    "escrow, deployed, 41 transactions" or "declared, could not check on this chain" —
    never a bare address that reads as confirmed because it is rendered in a monospace font.
    """
    if not isinstance(declaration, dict):
        return None
    entries = []
    any_verified = False
    for entry in declaration.get("entries") or []:
        address = _addr(entry.get("address"))
        if not address:
            continue
        item = dict(entry)
        found = verified.get(address.lower())
        if found:
            item["verified"] = bool(found.get("verified"))
            item["reason"] = str(found.get("reason") or "")
            if found.get("contract"):
                item["contract"] = True
            if isinstance(found.get("txs_sent"), int):
                item["txs_sent"] = found["txs_sent"]
            any_verified = any_verified or bool(found.get("verified"))
        else:
            item["verified"] = False
            item["reason"] = "not on the chain this monitor reads"
        # This monitor's own scanner, so an operator can read the transactions without
        # leaving the map (and without a public explorer existing at all, which is the
        # normal case inside the bubble).
        item["scan_url"] = f"/api/chain/address/{address}"
        entries.append(item)
    if not entries:
        return None
    out = {k: v for k, v in declaration.items() if k != "entries"}
    out["entries"] = entries
    out["verified"] = any_verified
    return out


def has_verified_contract(declaration: Any, verified: dict[str, dict[str, Any]]) -> bool:
    """Does this node hold at least one address we CONFIRMED on chain?

    The participation test. Not "did it declare one" — anybody can declare an address.
    """
    if not isinstance(declaration, dict):
        return False
    for entry in declaration.get("entries") or []:
        address = _addr(entry.get("address"))
        if address and (verified.get(address.lower()) or {}).get("verified"):
            return True
    return False
