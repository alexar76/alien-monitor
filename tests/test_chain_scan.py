"""The block scanner: it may mislabel nothing, and it may never take the dashboard down."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from chain_scan import (  # noqa: E402
    SELECTORS, _deployment_names, _hex_int, scan_address, scan_chain, scan_tx,
)


def test_selectors_are_the_ones_the_abi_actually_has():
    """Derived from contracts/evm/out/AIMarketEscrow.sol/AIMarketEscrow.json, not from memory.

    These two were the unknown four-bytes on the live UNI chain before the table existed.
    """
    assert SELECTORS["0xba999563"] == "openChannel"
    assert SELECTORS["0xf7becd80"] == "debitChannel"
    assert SELECTORS["0xa9059cbb"] == "transfer"


def test_lottery_and_acex_selectors_render_as_names():
    """The UNI bubble's economy — the raffle relayer and the ACEX AMM — must read as method
    names, not hex, or the scanner shows its own operator a wall of four-byte selectors.
    Derived from lottery/contracts/out/AIAgentLottery.sol and acex .../PulseAMM.sol."""
    assert SELECTORS["0xe562dfd9"] == "openRound"
    assert SELECTORS["0x54a75ed5"] == "buyTicketsWithVoucher"
    assert SELECTORS["0xc39ec144"] == "fulfillDraw"
    assert SELECTORS["0xd7098154"] == "claimPrize"
    assert SELECTORS["0xa5ebc6cd"] == "swapUsdcForShare"


def test_the_uni_deployment_is_readable_and_named():
    """The bubble's own contracts must resolve, or the scanner shows hex to its own operator."""
    names = _deployment_names("uni")
    assert names, "no deployment names resolved — check the roots list"
    assert names.get("0x5fbdb2315678afecb367f032d93f642f64180aa3") == "USDC"
    assert names.get("0xe7f1725e7734ce288f8367e1bb143e90bb3f0512") == "AIMarketEscrow"


def test_an_unset_override_does_not_win_the_root_lookup(monkeypatch):
    """`Path("")` is `Path(".")`, which IS a directory — so an unset env var silently made the
    current working directory the deployments root and every label came back empty."""
    monkeypatch.delenv("ALIEN_DEPLOYMENTS_DIR", raising=False)
    assert _deployment_names("uni"), "the empty-string override is winning again"


def test_hex_parsing_never_raises():
    assert _hex_int("0x10") == 16
    assert _hex_int("16") == 16
    assert _hex_int(None) == 0
    assert _hex_int("nonsense") == 0


def test_no_rpc_is_an_empty_scan_not_an_error():
    out = asyncio.run(scan_chain("", realm="uni"))
    assert out["txs"] == [] and out["note"]


def test_an_unreachable_chain_is_an_empty_scan_not_an_error():
    """A scanner that raises takes the dashboard with it."""
    out = asyncio.run(scan_chain("http://127.0.0.1:9", realm="uni", timeout=1.0))
    assert out["txs"] == []
    assert out["note"], "a failure must say why"
    assert out["chain_id"] is None


# --- scan_tx / scan_address: a fake RPC so the receipt logic is tested without a chain ----

def _fake_client_rpc(responses):
    """Return an async stand-in for chain_scan._rpc that answers by method name."""
    async def _rpc(_client, _url, method, params):
        val = responses.get(method)
        return val(params) if callable(val) else val
    return _rpc


def test_scan_tx_rejects_a_non_hash():
    out = asyncio.run(scan_tx("http://x", "0xdeadbeef", realm="uni"))
    assert out["found"] is False and out["note"] == "not a transaction hash"


def test_scan_tx_reads_status_gas_and_named_logs(monkeypatch):
    import chain_scan
    txh = "0x" + "ab" * 32
    monkeypatch.setattr(chain_scan, "_rpc", _fake_client_rpc({
        "eth_getTransactionByHash": {
            "hash": txh, "blockNumber": "0x5",
            "from": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
            "to": "0xe7f1725e7734ce288f8367e1bb143e90bb3f0512",  # AIMarketEscrow (uni)
            "value": "0x0", "nonce": "0x3", "gas": "0x30d40",
            "input": "0xba999563" + "00" * 32, "gasPrice": "0x3b9aca00",
        },
        "eth_getBlockByNumber": {"timestamp": "0x66f00000"},
        "eth_getTransactionReceipt": {
            "status": "0x1", "gasUsed": "0x520c", "effectiveGasPrice": "0x3b9aca00",
            "logs": [{
                "address": "0x5fbdb2315678afecb367f032d93f642f64180aa3",  # USDC (uni)
                "topics": ["0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
                           "0x00", "0x00"],
                "data": "0x" + "00" * 32,
            }],
        },
    }))
    out = asyncio.run(scan_tx("http://x", txh, realm="uni"))
    assert out["found"] is True
    assert out["status"] == 1
    assert out["gas_used"] == 0x520c
    assert out["method"] == "openChannel"
    assert out["to_label"] == "AIMarketEscrow"
    assert out["logs"][0]["event"] == "Transfer"
    assert out["logs"][0]["address_label"] == "USDC"


def test_scan_tx_missing_tx_is_a_soft_miss(monkeypatch):
    import chain_scan
    monkeypatch.setattr(chain_scan, "_rpc", _fake_client_rpc({"eth_getTransactionByHash": None}))
    out = asyncio.run(scan_tx("http://x", "0x" + "11" * 32, realm="uni"))
    assert out["found"] is False and "no such transaction" in out["note"]


def test_scan_address_rejects_a_non_address():
    out = asyncio.run(scan_address("http://x", "0xnope", realm="uni"))
    assert out["found"] is False and out["note"] == "not an address"


def test_scan_address_reports_balance_nonce_and_touching_txs(monkeypatch):
    import chain_scan
    me = "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"
    monkeypatch.setattr(chain_scan, "MAX_BLOCK_SPAN", 2)
    monkeypatch.setattr(chain_scan, "_rpc", _fake_client_rpc({
        "eth_getBalance": "0x1bc16d674ec80000",  # 2 ether
        "eth_getTransactionCount": "0x4",
        "eth_getCode": "0x",  # an EOA, not a contract
        "eth_blockNumber": "0x1",
        "eth_getBlockByNumber": lambda p: (
            {"timestamp": "0x66f00000", "transactions": [
                {"hash": "0x" + "cd" * 32, "from": me,
                 "to": "0xe7f1725e7734ce288f8367e1bb143e90bb3f0512",
                 "value": "0x0", "input": "0xf7becd80"},
            ]} if p[0] == "0x1" else {"timestamp": "0x0", "transactions": []}
        ),
    }))
    out = asyncio.run(scan_address("http://x", me, realm="uni"))
    assert out["found"] is True
    assert out["balance_wei"] == str(2 * 10**18)
    assert out["nonce"] == 4
    assert out["is_contract"] is False
    assert len(out["txs"]) == 1
    assert out["txs"][0]["direction"] == "out"
    assert out["txs"][0]["method"] == "debitChannel"


# --- the monitor pointed at a chain it is not advertising ---------------------------------

def test_a_scan_flags_a_chain_that_is_not_the_configured_network(monkeypatch):
    """The LIVE monitor rendered a "Base" header over a local Anvil: `network.chain_id` said
    8453, `evm.chain_id` said 31337, and nothing in the payload compared the two."""
    import chain_scan
    monkeypatch.setenv("ALIEN_EVM_RPC", "http://127.0.0.1:8545")
    monkeypatch.setenv("AIMARKET_PRIMARY_CHAIN", "base")
    monkeypatch.setenv("ALIEN_MODE", "real")
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")   # crypto on → the settings network
    monkeypatch.setattr(chain_scan, "_rpc", _fake_client_rpc({
        "eth_chainId": "0x7a69",        # 31337 — Anvil
        "eth_blockNumber": "0x1",
        "eth_getBlockByNumber": {"timestamp": "0x66f00000", "transactions": []},
    }))
    out = asyncio.run(scan_chain("http://x", realm="live", limit=1))
    mismatch = out["chain_mismatch"]
    assert mismatch, "a scan of a chain that is not the configured network must say so"
    assert mismatch["observed_chain_id"] == 31337
    assert mismatch["declared_chain_id"] == 8453
    assert "NOT Base" in mismatch["message"]


def test_the_matching_chain_raises_no_flag(monkeypatch):
    import chain_scan
    monkeypatch.setenv("AIMARKET_PRIMARY_CHAIN", "base")
    monkeypatch.setenv("ALIEN_MODE", "real")
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
    monkeypatch.setattr(chain_scan, "_rpc", _fake_client_rpc({
        "eth_chainId": "0x2105",        # 8453 — Base
        "eth_blockNumber": "0x1",
        "eth_getBlockByNumber": {"timestamp": "0x66f00000", "transactions": []},
    }))
    out = asyncio.run(scan_chain("http://x", realm="live", limit=1))
    assert out["chain_mismatch"] is None


def test_the_status_snapshot_carries_the_same_warning(monkeypatch):
    """One implementation, so the scanner and the status panel cannot disagree."""
    import chain_metrics
    monkeypatch.setenv("AIMARKET_PRIMARY_CHAIN", "base")
    monkeypatch.setenv("ALIEN_MODE", "real")
    assert chain_metrics.declared_network_mismatch(8453) is None
    assert chain_metrics.declared_network_mismatch(None) is None
    assert chain_metrics.declared_network_mismatch("nonsense") is None
    out = chain_metrics.declared_network_mismatch(31337)
    assert out and out["declared_chain"] == "base" and out["observed_chain_id"] == 31337


def test_the_bubble_declares_its_own_chain_id_not_the_preset_one(monkeypatch):
    """In the hub, the realm seal swaps the preset's chain id for the bubble's. chain_net.py is
    vendored byte-identical into the monitor (no `aimarket_hub` to import), so that swap never
    happened here and the UNI panel advertised Base's 8453 over an Anvil answering 31337."""
    import chain_metrics
    monkeypatch.setenv("AIMARKET_PRIMARY_CHAIN", "base")
    monkeypatch.setenv("ALIEN_MODE", "universe")
    info = chain_metrics.active_network_info()
    assert info["chain_id"] == 31337 and info["realm"] == "uni"
    assert info["name"] == "Base", "the bubble keeps the network's NAME on purpose"
    assert chain_metrics.declared_network_mismatch(31337) is None
    monkeypatch.setenv("ALIEN_MODE", "real")
    assert chain_metrics.declared_network_mismatch(31337) is not None
