"""A stranger's on-chain declaration: bounded, checked, and never believed on its word.

The declaration is the third way a second-hop node can earn a sphere (see
test_sphere_participation for the other two). It is the only one whose evidence does not
come from our own books, which makes the boundary between "declared" and "verified" the
whole feature: get it wrong and the map republishes a stranger's claims as facts.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import foreign_contracts as fc  # noqa: E402


ESCROW = "0x12Db8FAC81E5999D2f2087B79e38951571562CF2"
WALLET = "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a"


def declaration(**over):
    base = {
        "version": 1,
        "chain": "base",
        "chain_id": 8453,
        "network": "Base",
        "explorer": "https://basescan.org",
        "entries": [
            {"role": "escrow", "name": "AIMarketEscrow", "address": ESCROW,
             "explorer": f"https://basescan.org/address/{ESCROW}"},
            {"role": "wallet", "name": "settlement wallet", "address": WALLET},
        ],
    }
    base.update(over)
    return base


# ── sanitize: untrusted input from a stranger's JSON ────────────────────────────


def test_sanitize_keeps_a_well_formed_declaration():
    out = fc.sanitize(declaration())
    assert out is not None
    assert [e["address"] for e in out["entries"]] == [ESCROW, WALLET]
    assert out["chain_id"] == 8453


def test_sanitize_rejects_anything_that_is_not_an_address():
    out = fc.sanitize(declaration(entries=[
        {"role": "escrow", "address": "0xdeadbeef"},            # too short
        {"role": "escrow", "address": "not an address"},
        {"role": "escrow", "address": "0x" + "0" * 40},          # zero address = unset
        {"role": "escrow", "address": "0x" + "z" * 40},          # not hex
        {"role": "escrow", "address": ESCROW},
    ]))
    assert out is not None
    assert [e["address"] for e in out["entries"]] == [ESCROW]


def test_sanitize_drops_a_javascript_explorer_url():
    """A stranger's 'explorer' is rendered as a link in the operator's browser."""
    out = fc.sanitize(declaration(entries=[
        {"role": "escrow", "address": ESCROW, "explorer": "javascript:alert(1)"},
    ]))
    assert "explorer" not in out["entries"][0]


def test_sanitize_bounds_entries_and_strings():
    flood = [
        {"role": "escrow", "address": "0x" + f"{i:040x}", "name": "n" * 5_000}
        for i in range(1, 40)
    ]
    out = fc.sanitize(declaration(entries=flood))
    assert len(out["entries"]) == fc.MAX_ENTRIES
    assert all(len(e["name"]) <= 120 for e in out["entries"])


def test_sanitize_normalises_an_unknown_role():
    out = fc.sanitize(declaration(entries=[{"role": "TOTALLY_MADE_UP", "address": ESCROW}]))
    assert out["entries"][0]["role"] == "other"


def test_sanitize_returns_none_for_nothing_usable():
    assert fc.sanitize(None) is None
    assert fc.sanitize({}) is None
    assert fc.sanitize({"entries": []}) is None
    assert fc.sanitize({"entries": [{"address": "nope"}]}) is None


def test_declarations_in_separates_own_from_peers():
    wk = {
        "contracts": declaration(),
        "peers": [
            {"url": "https://peer.example/", "contracts": declaration()},
            {"url": "https://silent.example", "contracts": None},
        ],
    }
    found = fc.declarations_in(wk)
    assert set(found) == {"", "https://peer.example"}


# ── verify: what the chain says ────────────────────────────────────────────────


class FakeRPC:
    """Minimal JSON-RPC double. Records what was asked, so we can assert we did not ask."""

    def __init__(self, code_by_addr=None, nonce_by_addr=None, fail=False):
        self.code = code_by_addr or {}
        self.nonce = nonce_by_addr or {}
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    async def post(self, url, json=None, timeout=None):  # noqa: A002 - httpx signature
        method = json["method"]
        address = str(json["params"][0]).lower()
        self.calls.append((method, address))
        if self.fail:
            raise RuntimeError("rpc down")
        if method == "eth_getCode":
            return _Resp({"result": self.code.get(address, "0x")})
        if method == "eth_getTransactionCount":
            return _Resp({"result": hex(self.nonce.get(address, 0))})
        return _Resp({"result": None})


class _Resp:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch):
    fc._cache.clear()
    monkeypatch.setattr(fc, "_reading_chain", lambda: ("http://rpc.test", 8453, False))
    yield
    fc._cache.clear()


def test_a_deployed_contract_is_verified():
    client = FakeRPC(code_by_addr={ESCROW.lower(): "0x60806040"})
    out = asyncio.run(fc.verify(client, {"": declaration()}))
    assert out[ESCROW.lower()]["verified"] is True
    assert out[ESCROW.lower()]["reason"] == "contract deployed"


def test_a_wallet_is_verified_only_once_it_has_transacted():
    quiet = FakeRPC()
    out = asyncio.run(fc.verify(quiet, {"": declaration()}))
    assert out[WALLET.lower()]["verified"] is False
    assert out[WALLET.lower()]["reason"] == "no code and no transactions"

    fc._cache.clear()
    busy = FakeRPC(nonce_by_addr={WALLET.lower(): 41})
    out = asyncio.run(fc.verify(busy, {"": declaration()}))
    assert out[WALLET.lower()]["verified"] is True
    assert out[WALLET.lower()]["txs_sent"] == 41


def test_an_address_of_all_zero_code_is_not_a_contract():
    """Some nodes answer eth_getCode with padded zeros rather than bare 0x."""
    client = FakeRPC(code_by_addr={ESCROW.lower(): "0x" + "0" * 64})
    out = asyncio.run(fc.verify(client, {"": declaration()}))
    assert out[ESCROW.lower()]["verified"] is False


def test_a_declaration_for_another_chain_is_never_checked():
    """We say nothing about chains we cannot read — not 'probably fine'."""
    client = FakeRPC(code_by_addr={ESCROW.lower(): "0x60806040"})
    out = asyncio.run(fc.verify(client, {"": declaration(chain_id=1, chain="ethereum")}))
    assert out == {}
    assert client.calls == []


def test_a_declaration_with_no_chain_id_is_never_checked():
    client = FakeRPC(code_by_addr={ESCROW.lower(): "0x60806040"})
    stated = declaration()
    stated.pop("chain_id")
    out = asyncio.run(fc.verify(client, {"": stated}))
    assert out == {}
    assert client.calls == []


def test_a_simulated_declaration_is_not_verified_by_a_live_monitor(monkeypatch):
    """Bubble money must not become evidence on the real map."""
    monkeypatch.setattr(fc, "_reading_chain", lambda: ("http://rpc.test", 8453, False))
    client = FakeRPC(code_by_addr={ESCROW.lower(): "0x60806040"})
    out = asyncio.run(fc.verify(client, {"": declaration(simulated=True)}))
    assert out == {}
    assert client.calls == []


def test_a_simulated_declaration_IS_verified_inside_the_bubble(monkeypatch):
    monkeypatch.setattr(fc, "_reading_chain", lambda: ("http://anvil", 31337, True))
    client = FakeRPC(code_by_addr={ESCROW.lower(): "0x60806040"})
    out = asyncio.run(fc.verify(client, {"": declaration(chain_id=31337, simulated=True)}))
    assert out[ESCROW.lower()]["verified"] is True


def test_an_rpc_failure_reports_unknown_and_never_verified():
    """'We could not look' and 'it is not there' are different claims."""
    out = asyncio.run(fc.verify(FakeRPC(fail=True), {"": declaration()}))
    assert out[ESCROW.lower()]["verified"] is False
    assert out[ESCROW.lower()]["reason"] == "rpc unavailable"


def test_no_chain_configured_checks_nothing(monkeypatch):
    monkeypatch.setattr(fc, "_reading_chain", lambda: ("", None, False))
    client = FakeRPC(code_by_addr={ESCROW.lower(): "0x60806040"})
    assert asyncio.run(fc.verify(client, {"": declaration()})) == {}
    assert client.calls == []


def test_a_verified_result_is_cached_and_not_re_asked():
    client = FakeRPC(code_by_addr={ESCROW.lower(): "0x60806040"})
    asyncio.run(fc.verify(client, {"": declaration()}))
    first = len(client.calls)
    asyncio.run(fc.verify(client, {"": declaration()}))
    assert len(client.calls) == first, "a cached verdict must not re-hit the RPC"


def test_addresses_are_bounded_per_tick():
    """A hub with many peers must not turn one tick into hundreds of RPC calls."""
    decls = {
        f"peer{i}": declaration(entries=[{"role": "escrow", "address": "0x" + f"{i:040x}"}])
        for i in range(1, 200)
    }
    client = FakeRPC()
    asyncio.run(fc.verify(client, decls))
    asked = {addr for _m, addr in client.calls}
    assert len(asked) <= fc._MAX_ADDRESSES_PER_TICK


# ── evidence_for / has_verified_contract: what the card and the rule read ──────


def test_evidence_marks_each_entry_and_adds_a_scanner_link():
    verified = {ESCROW.lower(): {"verified": True, "reason": "contract deployed", "contract": True}}
    out = fc.evidence_for(fc.sanitize(declaration()), verified)
    escrow, wallet = out["entries"]
    assert escrow["verified"] is True and escrow["scan_url"] == f"/api/chain/address/{ESCROW}"
    assert wallet["verified"] is False
    assert wallet["reason"] == "not on the chain this monitor reads"
    assert out["verified"] is True


def test_evidence_says_unverified_when_nothing_was_confirmed():
    out = fc.evidence_for(fc.sanitize(declaration()), {})
    assert out["verified"] is False
    assert all(e["verified"] is False for e in out["entries"])


def test_participation_needs_a_confirmed_address_not_a_declared_one():
    declared = fc.sanitize(declaration())
    assert fc.has_verified_contract(declared, {}) is False
    assert fc.has_verified_contract(
        declared, {WALLET.lower(): {"verified": True}},
    ) is True
    assert fc.has_verified_contract(
        declared, {WALLET.lower(): {"verified": False}},
    ) is False


# ── the fold into a seeded node ────────────────────────────────────────────────


def test_a_seeded_hub_keeps_the_declaration_discovery_verified():
    """`competing_hub` and `signal_hunt_hub` are seeded suns on the live map, hydrated by
    discovery through `merge_discovered_peers`. That fold copied numeric metrics only, so a
    verified escrow — not a number — was dropped exactly for the hubs a viewer is most
    likely to open, and nothing failed: the node kept working without ever showing an
    address."""
    from oracle_family import merge_discovered_peers

    seeded = [{"id": "competing_hub", "label": "Competing Lab Hub", "group": "network",
               "url": "https://competing.example", "metrics": {}}]
    declaration = {
        "chain_id": 8453, "verified": True,
        "entries": [{"role": "escrow", "address": ESCROW, "verified": True}],
    }
    discovered = {"nodes": [{
        "id": "peer_hub:competing", "canonical_id": "competing_hub",
        "label": "Competing Lab Hub", "url": "https://competing.example",
        "group": "peer_hub", "hop": 1, "metrics": {"capabilities": 165},
        "contracts": declaration,
    }], "links": []}
    merge_discovered_peers(seeded, [], discovered)
    assert seeded[0]["contracts"] == declaration
    assert seeded[0]["metrics"]["capabilities"] == 165
