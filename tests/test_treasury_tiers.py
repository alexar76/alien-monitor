"""Treasury settlement tiers in the Alien Monitor panel — offline, no network.

The panel's whole job is to be believed, so these tests assert the three ways it is allowed to
speak about money:

    measured        a figure appears, and something actually read it
    unreachable     the source is down → NO figure at all, not a stale one, not a placeholder
    not connected   nothing is deployed → we never asked, so there is no zero to report

Plus the two labels that stop a true number from telling a lie: UNI figures are SIMULATED, and
TEST-mode figures are SYNTHETIC.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import treasury_status as ts  # noqa: E402

SPLITTER = ts.BOUNTY_SPLITTER_BASE


# ── fakes ────────────────────────────────────────────────────────────────────
class FakePool:
    """Stands in for chain_net.RpcPool: dispatches by JSON-RPC method, or raises."""

    def __init__(self, answers: dict, *, fail: set[str] | None = None):
        self.answers = answers
        self.fail = fail or set()
        self.calls: list[tuple[str, list]] = []

    def call(self, method: str, params: list | None = None):
        self.calls.append((method, params or []))
        if method in self.fail:
            raise RuntimeError(f"{method} endpoint down")
        return self.answers[method]


class DeadPool:
    def call(self, method: str, params: list | None = None):
        raise ts.chain_net.AllEndpointsDown("all 5 RPC endpoint(s) for 'base' failed")


def _wei(eth: float) -> str:
    return hex(int(eth * 10**18))


def _usdc_word(amount: float) -> str:
    return "0x" + f"{int(amount * 10**6):064x}"


def _base_pool(*, eth: float = 0.0, usdc: float = 0.0, deployed: bool = True, **kw) -> FakePool:
    return FakePool({
        "eth_getBalance": _wei(eth),
        "eth_getCode": "0x60806040" if deployed else "0x",
        "eth_call": _usdc_word(usdc),
    }, **kw)


VAULT_LIVE = {
    "balance_usd": 400.0, "reserved_usd": 150.0, "available_usd": 250.0,
    "transactions": 5, "open_reservations": {}, "settlement_mode": "uni",
    "note": "UNI tier — simulated bookkeeping; no value moves anywhere",
}


@pytest.fixture(autouse=True)
def _no_chain_cache(monkeypatch):
    """Tier reads must never leak between tests through the TTL cache."""
    ts._chain_cache.clear()
    monkeypatch.setenv("ALIEN_TREASURY_CHAIN_TTL", "0")
    yield
    ts._chain_cache.clear()


# ── UNI: happy path ──────────────────────────────────────────────────────────
def test_uni_tier_happy_path_reports_the_live_vault():
    tier = ts.uni_tier(VAULT_LIVE)
    assert tier["state"] == ts.TIER_OK
    assert tier["measured"] is True
    assert (tier["balance_usd"], tier["reserved_usd"], tier["available_usd"]) == (400.0, 150.0, 250.0)
    assert tier["transactions"] == 5
    assert tier["settlement_mode"] == "uni"


def test_uni_tier_is_always_flagged_simulated():
    """A balance shown without the word 'simulated' invites someone to think money moved."""
    assert ts.uni_tier(VAULT_LIVE)["simulated"] is True
    assert ts.uni_tier(None, error="connection refused")["simulated"] is True


def test_uni_reads_the_loopback_vault_not_the_public_proxy():
    """/vault is not in the public allow-list; the monitor reads it on 127.0.0.1 only."""
    assert ts.treasury_vault_url().startswith("http://127.0.0.1")
    assert "momus.modelmarket.dev" not in ts.treasury_vault_url()


# ── UNI: unreachable → says so, shows nothing ────────────────────────────────
def test_uni_tier_unreachable_shows_no_figures_at_all():
    tier = ts.uni_tier(None, error="ConnectError: connection refused")
    assert tier["state"] == ts.TIER_UNREACHABLE
    assert tier["measured"] is False
    assert "connection refused" in tier["detail"]
    # Not a zero, not a stale value, not a placeholder — the keys are simply absent.
    for key in ("balance_usd", "reserved_usd", "available_usd", "transactions"):
        assert key not in tier


def test_uni_tier_refuses_a_vault_body_without_a_balance():
    tier = ts.uni_tier({"transactions": 5, "settlement_mode": "uni"})
    assert tier["state"] == ts.TIER_UNREACHABLE
    assert "balance_usd" not in tier


def test_fetch_vault_state_reports_the_reason_it_failed(monkeypatch):
    class _Client:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url): raise OSError("Connection refused")

    monkeypatch.setattr(ts.httpx, "Client", _Client)
    state, err = ts.fetch_vault_state_sync()
    assert state is None
    assert "Connection refused" in err


# ── BASE: happy path + the zero that is CORRECT ──────────────────────────────
def test_base_tier_happy_path_reads_eth_and_usdc():
    pool = ts.base_tier(pool=_base_pool(eth=1.5, usdc=42.5))
    assert pool["state"] == ts.TIER_OK
    assert pool["measured"] is True
    assert pool["eth"] == 1.5
    assert pool["usdc"] == 42.5
    assert pool["deployed"] is True


def test_base_tier_queries_the_deployed_splitter_on_mainnet():
    fake = _base_pool()
    tier = ts.base_tier(pool=fake)
    assert tier["address"] == SPLITTER
    assert tier["chain_id"] == 8453
    assert ("eth_getBalance", [SPLITTER, "latest"]) in fake.calls
    # USDC balance goes through the ERC-20 balanceOf selector against the token contract.
    eth_calls = [p for m, p in fake.calls if m == "eth_call"]
    assert eth_calls and eth_calls[0][0]["data"].startswith("0x" + ts.oc.SEL_BALANCE_OF)
    assert SPLITTER[2:].lower() in eth_calls[0][0]["data"].lower()
    assert tier["explorer"].endswith(f"/address/{SPLITTER}")


def test_base_zero_is_measured_and_carries_its_explanation():
    """0/0 is the CORRECT state, not a fault — render it WITH the reason, or it reads as broken."""
    tier = ts.base_tier(pool=_base_pool(eth=0.0, usdc=0.0), settlement_mode="uni")
    assert tier["state"] == ts.TIER_OK          # measured, so the zero is shown
    assert tier["measured"] is True
    assert tier["eth"] == 0.0 and tier["usdc"] == 0.0
    # The explanation the panel renders next to the zero: on-chain payout is a SECOND opt-in.
    assert tier["payout_optin_required"] is True
    assert tier["settlement_mode"] == "uni"     # settlement is not routed on-chain today
    assert tier["deployed"] is True             # the contract exists; it is simply unfunded


def test_base_zero_is_distinguishable_from_unreachable():
    measured = ts.base_tier(pool=_base_pool(eth=0.0, usdc=0.0))
    down = ts.base_tier(pool=DeadPool())
    assert measured["eth"] == 0.0 and measured["state"] == ts.TIER_OK
    assert down["eth"] is None and down["usdc"] is None and down["state"] == ts.TIER_UNREACHABLE


# ── BASE: degradation ────────────────────────────────────────────────────────
def test_base_tier_unreachable_shows_no_figures():
    tier = ts.base_tier(pool=DeadPool())
    assert tier["state"] == ts.TIER_UNREACHABLE
    assert tier["measured"] is False
    assert tier["eth"] is None and tier["usdc"] is None and tier["deployed"] is None
    assert tier["detail"]


def test_base_tier_degrades_per_figure():
    """A failed USDC call must not erase the ETH balance we did measure."""
    tier = ts.base_tier(pool=_base_pool(eth=0.25, fail={"eth_call"}))
    assert tier["state"] == ts.TIER_OK
    assert tier["eth"] == 0.25
    assert tier["usdc"] is None
    assert any(e.startswith("usdc:") for e in tier["errors"])


def test_base_tier_never_leaks_rpc_credentials_into_the_panel():
    class _LeakyPool:
        def call(self, method, params=None):
            raise RuntimeError("https://user:secret@rpc.example/base?api_key=abc123 refused")

    tier = ts.base_tier(pool=_LeakyPool())
    blob = json.dumps(tier)
    assert "secret@" not in blob and "abc123" not in blob


# ── SOLANA: not connected, never zero ────────────────────────────────────────
def test_solana_tier_is_not_connected_and_never_zero():
    tier = ts.solana_tier(account="")
    assert tier["state"] == ts.TIER_NOT_CONNECTED
    assert tier["measured"] is False
    assert tier["sol"] is None          # NOT 0.0 — we never looked
    assert tier["account"] is None
    assert "never queried" in tier["source"]
    # No figure anywhere in the tier is a zero. (bools are ints in Python — the flags are not
    # figures, so they are excluded; what must not appear is a numeric 0 posing as a reading.)
    numbers = [v for v in tier.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
    assert 0 not in numbers


def test_solana_default_environment_is_not_connected(monkeypatch):
    monkeypatch.delenv("ALIEN_TREASURY_SOLANA_ACCOUNT", raising=False)
    monkeypatch.delenv("MOMUS_BOUNTY_SOLANA_ACCOUNT", raising=False)
    assert ts.solana_tier()["state"] == ts.TIER_NOT_CONNECTED


def test_solana_tier_becomes_a_real_read_once_an_account_exists():
    """'not connected' must be a live state, not a hardcoded string."""
    pool = FakePool({"getBalance": {"context": {"slot": 1}, "value": 2_500_000_000}})
    tier = ts.solana_tier(pool=pool, account="So11111111111111111111111111111111111111112")
    assert tier["state"] == ts.TIER_OK
    assert tier["measured"] is True
    assert tier["sol"] == 2.5


def test_solana_configured_but_unreachable_is_not_not_connected():
    tier = ts.solana_tier(pool=DeadPool(), account="So1111")
    assert tier["state"] == ts.TIER_UNREACHABLE
    assert tier["sol"] is None


# ── independence: one dead source must not blank the card ────────────────────
def _tiers_by_id(tiers: list[dict]) -> dict[str, dict]:
    return {t["tier"]: t for t in tiers}


def test_vault_unreachable_still_renders_the_base_figure(monkeypatch):
    monkeypatch.setattr(ts, "fetch_vault_state_sync", lambda **kw: (None, "connection refused"))
    tiers = ts.treasury_tiers(evm_pool=_base_pool(eth=0.0, usdc=0.0), solana_pool=None)
    by_id = _tiers_by_id(tiers)
    assert [t["tier"] for t in tiers] == ["uni", "base", "solana"]
    assert by_id["uni"]["state"] == ts.TIER_UNREACHABLE
    assert "balance_usd" not in by_id["uni"]
    # …and the other two are unaffected.
    assert by_id["base"]["state"] == ts.TIER_OK and by_id["base"]["eth"] == 0.0
    assert by_id["solana"]["state"] == ts.TIER_NOT_CONNECTED


def test_base_unreachable_still_renders_the_vault_balance(monkeypatch):
    monkeypatch.setattr(ts, "fetch_vault_state_sync", lambda **kw: (dict(VAULT_LIVE), ""))
    by_id = _tiers_by_id(ts.treasury_tiers(evm_pool=DeadPool()))
    assert by_id["uni"]["balance_usd"] == 400.0
    assert by_id["base"]["state"] == ts.TIER_UNREACHABLE
    assert by_id["base"]["eth"] is None


def test_a_tier_that_explodes_does_not_kill_the_others(monkeypatch):
    monkeypatch.setattr(ts, "fetch_vault_state_sync", lambda **kw: (dict(VAULT_LIVE), ""))
    monkeypatch.setattr(ts, "base_tier", lambda **kw: (_ for _ in ()).throw(ValueError("boom")))
    by_id = _tiers_by_id(ts.treasury_tiers())
    assert by_id["uni"]["state"] == ts.TIER_OK
    assert by_id["base"]["state"] == ts.TIER_UNREACHABLE
    assert "boom" in by_id["base"]["detail"]
    assert by_id["solana"]["state"] == ts.TIER_NOT_CONNECTED


def test_health_offline_still_ships_the_tiers():
    """The public audit surface being down hides the pubkey and counters — nothing else."""
    nodes = [{"id": "treasury"}]
    tiers = ts.treasury_tiers(evm_pool=_base_pool())
    ts.apply_treasury_to_nodes(nodes, None, tiers=tiers)
    live = nodes[0]["treasury_live"]
    assert nodes[0]["status"] == "offline"
    assert live["health_online"] is False
    assert [t["tier"] for t in live["tiers"]] == ["uni", "base", "solana"]


def test_health_online_carries_tiers_alongside_the_counters():
    nodes = [{"id": "treasury"}]
    status = {"health": {"status": "ok", "treasury_pubkey": "abc", "external_verifiers": ["metis"]},
              "ledger": [{"kind": "decision", "state": "paid"}]}
    ts.apply_treasury_to_nodes(nodes, status, tiers=ts.treasury_tiers(evm_pool=_base_pool()))
    live = nodes[0]["treasury_live"]
    assert live["health_online"] is True
    assert live["counts"]["paid"] == 1
    assert len(live["tiers"]) == 3


def test_the_loopback_vault_url_is_never_published_in_the_node():
    nodes = [{"id": "treasury"}]
    ts.apply_treasury_to_nodes(nodes, None, tiers=ts.treasury_tiers(evm_pool=_base_pool()))
    assert "127.0.0.1:9411" not in json.dumps(nodes)


# ── TEST mode: synthetic, and said out loud ──────────────────────────────────
def test_test_mode_labels_every_figure_synthetic():
    node: dict = {"id": "treasury"}
    ts.fill_treasury_sim_node(node, tick=4)
    live = node["treasury_live"]
    assert live["synthetic"] is True
    assert len(live["tiers"]) == 3
    for tier in live["tiers"]:
        assert tier["synthetic"] is True, tier["tier"]
        # Synthetic is the opposite of measured: nothing here was read from anything.
        assert tier["measured"] is False


def test_test_mode_keeps_uni_simulated_and_solana_not_connected():
    node: dict = {"id": "treasury"}
    ts.fill_treasury_sim_node(node)
    by_id = _tiers_by_id(node["treasury_live"]["tiers"])
    assert by_id["uni"]["simulated"] is True
    assert by_id["uni"]["balance_usd"] == 400.0
    # Even in TEST mode: inventing a Solana zero would teach the reader to expect one in LIVE.
    assert by_id["solana"]["state"] == ts.TIER_NOT_CONNECTED
    assert by_id["solana"]["sol"] is None


def test_real_tiers_are_never_marked_synthetic(monkeypatch):
    monkeypatch.setattr(ts, "fetch_vault_state_sync", lambda **kw: (dict(VAULT_LIVE), ""))
    for tier in ts.treasury_tiers(evm_pool=_base_pool()):
        assert tier.get("synthetic") is not True
