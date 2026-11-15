"""UNI bootstrap includes EVM + optional Solana lottery contract addresses."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from universe import VirtualUniverse, resolve_lottery_contracts_dir
from lottery_layers import _metrics_from_layers


def test_resolve_lottery_contracts_dir():
    p = resolve_lottery_contracts_dir()
    if p is None:
        pytest.skip("lottery/contracts not present (standalone alien-monitor mirror)")
    assert (p / "src" / "AIAgentLottery.sol").is_file()


def test_hub_snippet_includes_lottery_addresses(tmp_path):
    u = VirtualUniverse(data_dir=tmp_path)
    u.evm_escrow_address = "0x" + "e" * 40
    u.evm_nft_address = "0x" + "9" * 40
    u.evm_usdt_address = "0x" + "5" * 40
    u.evm_lottery_address = "0x" + "d" * 40
    u.solana_lottery_program_id = "DT6QVF7HhCQTFRCcP7V6AJpQF6ZQzEc9LQSrq85MHpFD"
    u.payment_recipient = "0x" + "f" * 40
    u._write_hub_env_snippet()
    text = (tmp_path / "hub.env.snippet").read_text(encoding="utf-8")
    assert "HUB_LOTTERY_ADDRESS=0x" + "d" * 40 in text
    assert "AIMARKET_LOTTERY_SOLANA_PROGRAM_ID=DT6QVF7HhCQTFRCcP7V6AJpQF6ZQzEc9LQSrq85MHpFD" in text


def _chain_universe(call_result=b"\x00" * 31 + b"\x07"):
    u = VirtualUniverse(data_dir=Path("/tmp/unused"))
    u._w3 = MagicMock()
    u._w3.is_connected.return_value = True
    u._w3.to_checksum_address.side_effect = lambda a: a
    u._w3.eth.get_code.return_value = b"\x01"
    if isinstance(call_result, Exception):
        u._w3.eth.call.side_effect = call_result
    else:
        u._w3.eth.call.return_value = call_result
    return u


def test_lottery_contract_verified_checks_code():
    u = _chain_universe()
    u.evm_lottery_address = "0xabc"
    assert u._lottery_contract_verified() is True
    u._w3.eth.call.assert_called_once_with({"to": "0xabc", "data": "0x9cbe5efd"})


def test_lottery_address_of_another_core_contract_is_not_a_lottery():
    # 2026-11-14: after a chain reset the saved lottery address held the NFT; "has code" passed.
    u = _chain_universe()
    u.evm_nft_address = "0x9fe46736679d2d9a65f0992f2272de9f3c7fa6e0"
    u.evm_lottery_address = "0x9FE46736679D2D9A65F0992F2272DE9F3C7FA6E0"
    assert u._lottery_contract_verified() is False


def test_contract_without_current_round_id_is_not_a_lottery():
    u = _chain_universe(call_result=ValueError("execution reverted"))
    u.evm_lottery_address = "0xabc"
    assert u._lottery_contract_verified() is False
    u = _chain_universe(call_result=b"")  # a fallback that returns nothing
    u.evm_lottery_address = "0xabc"
    assert u._lottery_contract_verified() is False


def test_named_contract_missing_from_broadcast_gives_no_address(tmp_path):
    run_dir = tmp_path / "broadcast" / "DeployLottery.s.sol" / "31337"
    run_dir.mkdir(parents=True)
    (run_dir / "run-latest.json").write_text(
        '{"transactions": [{"contractName": "AgentNFT", '
        '"contractAddress": "0x9fe46736679d2d9a65f0992f2272de9f3c7fa6e0"}], '
        '"receipts": [{"transactionHash": "0x' + "ab" * 32 + '"}]}',
        encoding="utf-8",
    )
    u = VirtualUniverse(data_dir=tmp_path / "data")
    script = "script/DeployLottery.s.sol:DeployLottery"
    assert u._parse_broadcast_address(script, tmp_path, contract_name="AIAgentLottery") is None
    assert u._parse_broadcast_address(script, tmp_path) == "0x9fe46736679d2d9a65f0992f2272de9f3c7fa6e0"


def test_bootstrap_replaces_a_saved_lottery_that_is_not_one_after_acex(tmp_path):
    u = VirtualUniverse(data_dir=tmp_path)
    u.evm_lottery_address = "0x9fe46736679d2d9a65f0992f2272de9f3c7fa6e0"
    order = []
    lottery = iter([False, True])
    acex = iter([False, True])
    with patch.object(u, "_start_blockchain_locked", return_value=True), \
         patch.object(u, "_load_config_from_disk", return_value=True), \
         patch.object(u, "_core_contracts_verified", return_value=True), \
         patch.object(u, "_lottery_contract_verified", side_effect=lambda: next(lottery)), \
         patch.object(u, "_acex_contracts_verified", side_effect=lambda: next(acex)), \
         patch.object(u, "_deploy_acex_forge", side_effect=lambda: order.append("acex")), \
         patch.object(u, "_deploy_lottery_forge", side_effect=lambda: order.append(("lottery", u.evm_lottery_address))), \
         patch.object(u, "_save_config"), \
         patch.object(u, "sync_factory_catalog", return_value=0), \
         patch("acex_uni.acex_uni_enabled", return_value=True), \
         patch("acex_uni.seed_acex_markets", side_effect=lambda _u: order.append("seed")), \
         patch("universe._universe_solana_enabled", return_value=False):
        u._scenario_engine = MagicMock()
        u.entities = {"x": object()}
        u._bootstrap_locked()
    assert order == ["acex", ("lottery", None), "seed"]
    assert any("is not an AIAgentLottery" in n for n in u._bootstrap_notes)


def test_live_lottery_feed_overrides_layer_metrics():
    from live_lottery_feed import set_live_lottery

    set_live_lottery({
        "mode": "uni",
        "metrics": {"prize_pool_usd": 9.5, "round": 3, "players": 4,
                    "payouts_24h": 1.0, "opex_24h": 0.5, "funding_24h": 2.0},
        "events": [{"id": "lot_1", "agent": "Hub", "action": "tithe", "target": "lottery", "amount": 1}],
    })
    m = _metrics_from_layers({"invocations_24h": 999}, {"agents": 99})
    assert m["round"] == 3
    assert m["players"] == 4
    assert m["prize_pool_usd"] == 9.5
