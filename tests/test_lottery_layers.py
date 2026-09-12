"""Tests for Agent Lottery monitor integration."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from factory_products import merge_factory_products
from lottery_layers import apply_lottery_metrics, lottery_financial_links, lottery_node_spec
from main import build_topology


def test_lottery_node_is_economy_group():
    nodes, links = build_topology()
    lot = next(n for n in nodes if n["id"] == "lottery")
    assert lot["group"] == "economy"
    assert lot["url"].startswith("https://")
    assert any(l["target"] == "lottery" and l["source"] == "hub" for l in links)


def test_merge_factory_products_keeps_lottery():
    nodes, links = build_topology()
    merge_factory_products(nodes, links, [{"id": "prod-a", "name": "Demo", "category": "saas"}])
    assert any(n["id"] == "lottery" for n in nodes)
    assert any(l["target"] == "lottery" for l in links)


def test_hub_volume_never_becomes_lottery_money():
    """The card used to be arithmetic on the hub's escrow volume, not the lottery.

    `prize_pool = volume * 0.05`, `payouts_24h = volume * 0.03`,
    `opex_24h = volume * 0.02`, `funding_24h = volume * 0.20`. On 2026-09-07 that put a
    $0.17 prize pool and a $0.66 hub tithe on the LIVE map from $3.32 of lifetime escrow
    volume, while the deployed contract had never opened a round.
    """
    from live_lottery_feed import clear_live_lottery

    clear_live_lottery()
    nodes, _ = build_topology()
    apply_lottery_metrics(
        nodes,
        hub_hints={"invocations_24h": 120, "volume_24h": 100.0},
        mesh_stats={"agents": 7},
    )
    lot = next(n for n in nodes if n["id"] == "lottery")
    assert lot["metrics"]["players"] == 7          # a real mesh reading
    assert "funding_24h" not in lot["metrics"]
    assert "payouts_24h" not in lot["metrics"]
    assert "opex_24h" not in lot["metrics"]
    assert "prize_pool_usd" not in lot["metrics"]
    # Nothing read the contract, so the node does not claim to know its state.
    assert lot["status"] == "unknown"


def test_apply_lottery_metrics_from_the_contract():
    from live_lottery_feed import clear_live_lottery

    clear_live_lottery()
    nodes, _ = build_topology()
    apply_lottery_metrics(
        nodes,
        hub_hints={"invocations_24h": 120, "volume_24h": 100.0},
        mesh_stats={"agents": 7},
        chain={
            "lottery": {
                "read_ok": True, "round": 3, "players": 5, "tickets": 12,
                "prize_pool": 0.25, "prize_token": "USDC",
                "funding_total": 1.5, "prizes_paid": 0.75,
                "opex_accrued": 0.1, "ticket_revenue": 0.36,
            }
        },
    )
    lot = next(n for n in nodes if n["id"] == "lottery")
    assert lot["status"] == "active"
    assert lot["metrics"]["round"] == 3
    assert lot["metrics"]["players"] == 5
    assert lot["metrics"]["prize_pool_usd"] == 0.25
    assert lot["metrics"]["funding_total"] == 1.5
    assert "funding_24h" not in lot["metrics"]


def test_eth_prize_pool_is_not_labelled_usd():
    """No price oracle in this ecosystem — the live lottery settles in native ETH."""
    from live_lottery_feed import clear_live_lottery

    clear_live_lottery()
    nodes, _ = build_topology()
    apply_lottery_metrics(
        nodes,
        chain={"lottery": {"read_ok": True, "round": 0, "prize_pool": 0.003, "prize_token": "ETH"}},
    )
    lot = next(n for n in nodes if n["id"] == "lottery")
    assert lot["metrics"]["prize_pool"] == 0.003
    assert lot["metrics"]["prize_token"] == "ETH"
    assert "prize_pool_usd" not in lot["metrics"]
    assert lot["status"] == "idle"          # read, and quiet: no round open


def test_relayer_push_still_wins():
    from live_lottery_feed import clear_live_lottery, set_live_lottery

    set_live_lottery({"mode": "uni", "metrics": {"prize_pool_usd": 9.0, "round": 4, "players": 2}})
    try:
        nodes, _ = build_topology()
        apply_lottery_metrics(nodes, chain={"lottery": {"read_ok": True, "round": 1}})
        lot = next(n for n in nodes if n["id"] == "lottery")
        assert lot["metrics"]["prize_pool_usd"] == 9.0
        assert lot["status"] == "active"
    finally:
        clear_live_lottery()


def test_lottery_financial_links_to_oracles():
    links = lottery_financial_links(oracle_ids=["oracle-platon", "oracle-chronos"])
    assert {"source": "hub", "target": "lottery"} == {"source": links[0]["source"], "target": links[0]["target"]}
    targets = {l["target"] for l in links if l["source"] == "lottery"}
    assert "oracle-platon" in targets
    assert "oracle-chronos" in targets
