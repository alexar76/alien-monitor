"""UNI ACEX CapShare bootstrap wiring."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from universe import VirtualUniverse, resolve_acex_evm_dir


def test_resolve_acex_evm_dir():
    p = resolve_acex_evm_dir()
    if p is None:
        pytest.skip("acex/contracts/evm not present (standalone alien-monitor mirror)")
    assert (p / "src" / "PulseAMM.sol").is_file()


def test_hub_snippet_includes_acex_addresses(tmp_path):
    u = VirtualUniverse(data_dir=tmp_path)
    u.evm_escrow_address = "0x" + "e" * 40
    u.evm_nft_address = "0x" + "9" * 40
    u.evm_usdt_address = "0x" + "5" * 40
    u.evm_acex_amm_address = "0x" + "a" * 40
    u.evm_acex_registry_address = "0x" + "b" * 40
    u.evm_acex_lending_address = "0x" + "c" * 40
    u.payment_recipient = "0x" + "f" * 40
    u._write_hub_env_snippet()
    text = (tmp_path / "hub.env.snippet").read_text(encoding="utf-8")
    assert "ARGUS_UNI_ACEX_AMM=0x" + "a" * 40 in text
    assert "AIMARKET_ADDR_UNI_PulseAMM=0x" + "a" * 40 in text
    assert "ACEX_AUTO_IPO=1" in text


def test_acex_uni_enabled_default():
    from acex_uni import acex_uni_enabled

    assert acex_uni_enabled() is True
