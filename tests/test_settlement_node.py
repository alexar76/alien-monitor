"""The settlement node: what it shows, and what it must never show.

Two of these are architectural rather than behavioural, and they are the ones worth keeping:
the node must not carry the signer's spend caps (a public "budget nearly gone" is an
invitation), and it must not turn an unreadable chain into a zero (a zero and "we could not
read" mean opposite things and look identical).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

def _backend_dir() -> Path:
    """Where the backend lives, whether this file sits in the repo or is mounted elsewhere.

    The container runs the app from /app/backend and a mounted test file has no repo above it,
    so a path derived purely from __file__ resolves to a directory that does not exist.
    """
    candidates = [
        Path(__file__).resolve().parents[1] / "backend",
        Path(os.environ.get("ALIEN_BACKEND_DIR", "")) if os.environ.get("ALIEN_BACKEND_DIR") else None,
        Path("/app/backend"),
    ]
    for candidate in candidates:
        if candidate and (candidate / "settlement_status.py").is_file():
            return candidate
    raise RuntimeError("backend directory not found — set ALIEN_BACKEND_DIR")


BACKEND = _backend_dir()
sys.path.insert(0, str(BACKEND))

import settlement_status as ss          # noqa: E402
from settlement_layers import (settlement_node_spec, settlement_topology_links)  # noqa: E402


def test_the_node_sits_between_the_hub_and_the_escrow():
    spec = settlement_node_spec()
    assert spec["id"] == "settlement"
    assert spec["group"] == "crypto"
    pos = spec["position"]
    assert pos != {"x": 0.0, "y": 0.0, "z": 0.0}, (
        "no position registered — the node would land on top of the hub at the origin")


def test_every_edge_points_at_a_node_that_exists():
    """A link to a node id nobody seeds is how an edge silently vanishes."""
    from main import build_topology

    nodes, links = build_topology()
    ids = {n["id"] for n in nodes}
    assert "settlement" in ids, "the node is not in build_topology"
    for edge in settlement_topology_links():
        assert edge["source"] in ids, edge
        assert edge["target"] in ids, edge
    drawn = {(e["source"], e["target"]) for e in links}
    for edge in settlement_topology_links():
        assert (edge["source"], edge["target"]) in drawn, f"edge not drawn: {edge}"


def test_the_node_greys_out_when_crypto_is_off():
    import main

    assert "settlement" in main._CRYPTO_NODE_IDS, (
        "every number on this node is an on-chain read; with crypto off it must grey out "
        "rather than publish zeros")


def test_an_unreadable_chain_is_offline_not_zero():
    nodes = [settlement_node_spec()]
    ss.apply_settlement_to_nodes(nodes, None)
    assert nodes[0]["status"] == "offline"
    assert nodes[0]["detail_unavailable"]
    # No invented numbers: the USD figures and the gas float must be ABSENT, not zero. A seeded
    # 0.0 made an unreadable chain look like a settled one.
    for key in ("escrow_held_usd", "collected_unswept_usd", "collector_gas_eth"):
        assert key not in nodes[0]["metrics"], f"{key} was rendered as a number we never read"


def test_a_collector_out_of_gas_is_degraded_not_idle():
    """An empty float presents to the hub as a string of indistinguishable refusals."""
    nodes = [settlement_node_spec()]
    ss.apply_settlement_to_nodes(nodes, {
        "collector": "0x" + "be" * 20,
        "escrow_held_usd": 5.0, "collected_unswept_usd": 0.0, "collector_gas_eth": 0.00001,
        "gas_low": True, "recent_debits": 0, "recent_window_blocks": 50,
    })
    assert nodes[0]["status"] == "degraded"


def test_no_collector_means_no_gas_alarm():
    """UNI has its own escrow and no policy signer. Reading a Base address's balance on the
    universe chain returns 0, which looked exactly like "out of gas" — a false alarm on the one
    node whose job is to make the real path legible."""
    nodes = [settlement_node_spec()]
    ss.apply_settlement_to_nodes(nodes, {
        "collector": "", "escrow_held_usd": 0.0, "collected_unswept_usd": None,
        "collector_gas_eth": None, "gas_low": None, "recent_debits": 0,
        "recent_window_blocks": 50,
    })
    assert nodes[0]["status"] == "idle", "a world with no collector must not report degraded"


def test_recent_debits_make_it_active_and_revenue_makes_it_online():
    nodes = [settlement_node_spec()]
    ss.apply_settlement_to_nodes(nodes, {
        "escrow_held_usd": 1.0, "collected_unswept_usd": 0.0, "collector_gas_eth": 0.002,
        "gas_low": False, "recent_debits": 2, "recent_window_blocks": 50})
    assert nodes[0]["status"] == "active"

    nodes = [settlement_node_spec()]
    ss.apply_settlement_to_nodes(nodes, {
        "escrow_held_usd": 1.0, "collected_unswept_usd": 0.31, "collector_gas_eth": 0.002,
        "gas_low": False, "recent_debits": 0, "recent_window_blocks": 50})
    assert nodes[0]["status"] == "online", "revenue on the collector means it worked recently"


def test_the_public_payload_carries_no_spend_caps():
    """The privacy invariant. The signer's caps and remaining budget are not public facts, and
    'the budget is nearly gone' tells a griefer exactly when to push."""
    status = {
        "escrow_held_usd": 1.0, "collected_unswept_usd": 0.0, "collector_gas_eth": 0.002,
        "gas_low": False, "recent_debits": 0, "recent_window_blocks": 50,
        "historical_total_available": False, "pending_visible_here": False,
    }
    nodes = [settlement_node_spec()]
    ss.apply_settlement_to_nodes(nodes, status)
    rendered = repr(nodes[0]).lower()
    for forbidden in ("cap_units", "cap_tx", "units_24h", "remaining_budget", "signer_token",
                      "private_key", "bearer"):
        assert forbidden not in rendered, f"the node leaked {forbidden}"


def test_the_lookback_is_bounded_but_no_longer_one_endpoints_limit(monkeypatch):
    """The old ceiling was 50 blocks — 1rpc.io's limit, generalised to every endpoint.

    Measured 2026-09-11: six of the eleven live public Base endpoints serve a 1000-block
    eth_getLogs and publicnode serves 10 000. The lookback is still BOUNDED, because a
    monitor tick cannot afford hundreds of requests, but it is no longer ~100 seconds of
    history; the span is now walked in chunks (see _scan_debit_logs).
    """
    monkeypatch.setenv("ALIEN_SETTLEMENT_LOOKBACK_BLOCKS", "400000")
    assert ss.lookback_blocks() == ss.MAX_LOOKBACK_BLOCKS
    assert ss.MAX_LOOKBACK_BLOCKS > 50
    monkeypatch.setenv("ALIEN_SETTLEMENT_LOOKBACK_BLOCKS", "not-a-number")
    assert ss.lookback_blocks() == ss.DEFAULT_LOOKBACK_BLOCKS
    monkeypatch.setenv("ALIEN_SETTLEMENT_LOOKBACK_BLOCKS", "10")
    assert ss.lookback_blocks() == 10


def test_the_debit_scan_narrows_its_window_instead_of_losing_the_probe():
    """A 1rpc-style endpoint must still yield the whole span, in 50-block bites."""
    calls: list[tuple[int, int]] = []
    refusals = {"n": 0}

    def fake_rpc(_client, _urls, method, params):
        assert method == "eth_getLogs"
        lo = int(params[0]["fromBlock"], 16)
        hi = int(params[0]["toBlock"], 16)
        if hi - lo + 1 > 50:
            refusals["n"] += 1
            raise RuntimeError("eth_getLogs is limited to 0 - 50 blocks range")
        calls.append((lo, hi))
        return []

    original = ss._rpc
    ss._rpc = fake_rpc
    try:
        out = ss._scan_debit_logs(None, ["https://x"], "0xescrow", 1_000, 1_199)
    finally:
        ss._rpc = original

    assert out == []
    assert refusals["n"] > 0, "the fixture never exercised the refusal path"
    covered: set[int] = set()
    for lo, hi in calls:
        assert hi - lo + 1 <= 50
        covered.update(range(lo, hi + 1))
    assert covered == set(range(1_000, 1_200)), "the chunked scan left a hole"


def test_a_non_range_failure_returns_a_partial_window_not_a_crash():
    """The window is a probe. Losing it mid-scan must not blank the node."""
    seen = {"n": 0}

    def fake_rpc(_client, _urls, _method, params):
        seen["n"] += 1
        if seen["n"] == 1:
            return [{"blockNumber": "0x1", "data": "0x" + "00" * 96, "topics": ["0x" + "11" * 32]}]
        raise RuntimeError("401 Client Error: Unauthorized")

    original = ss._rpc
    ss._rpc = fake_rpc
    try:
        out = ss._scan_debit_logs(None, ["https://x"], "0xescrow", 0, 5_000)
    finally:
        ss._rpc = original
    assert len(out) == 1, "the first chunk's logs were thrown away"


def test_the_node_says_what_it_cannot_show():
    """Rather than drawing a plausible zero for the two things it genuinely cannot see."""
    spec = settlement_node_spec()
    assert "queue" in spec["description"].lower() or "unsubmitted" in spec["description"].lower()


def test_the_signer_is_not_a_node_and_is_never_polled():
    """HORKOS is reachable only from the hub host, by design. Nothing here may dial it."""
    from main import build_topology

    nodes, _ = build_topology()
    assert not any(n["id"] in ("horkos", "signer", "escrow_signer") for n in nodes)
    source = (BACKEND / "settlement_status.py").read_text(encoding="utf-8")
    for forbidden in (":9500", "/sign", "SIGNER_TOKEN", "escrow-signer"):
        assert forbidden not in source, (
            f"the poller references {forbidden} — the settlement node must read chain, not the "
            f"signer")
