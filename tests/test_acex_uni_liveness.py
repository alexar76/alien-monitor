"""ACEX in the bubble: trade against contracts that exist, and label its counters honestly.

Found by looking at the UNI map on 2026-09-07: the ACEX node read `volume_24h: 281200`,
`trades: 1136`, `pools_active: 3` while EVERY trade tick in the log was failing —
"Could not transact with/call contract function" and "tx reverted", once per interval.

Both halves were wrong:

* the three CapShare tokens (SNTL / ATLS / GAIA) had **no code** on the chain any more —
  the bubble Anvil had lost the block range they were deployed in — but
  `seed_acex_markets` decided it was already done by reading `acex_uni_state.json`, which
  still pinned their addresses. It trusted a file about the state of a chain.
* `volume_24h` and `trades` were the file's CUMULATIVE counters, with no time window
  anywhere near them, so eight hours of nothing still displayed as 281 200 in 24h.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import acex_uni


class _Eth:
    def __init__(self, coded: set[str]):
        self._coded = {a.lower() for a in coded}

    def get_code(self, address):
        return b"\x60\x60" if str(address).lower() in self._coded else b""


class _W3:
    def __init__(self, coded: set[str]):
        self.eth = _Eth(coded)

    @staticmethod
    def to_checksum_address(a):
        return a

    @staticmethod
    def is_connected():
        return True


SNTL = "0x8c310f133d4906cf931f55d6574c790cd5964afd"
ATLS = "0xeebc0aa65ea22a901034e80a192171434bb87c67"
GAIA = "0x812d8c8dc340ad4fa1a4c5f25f23cc4515d70ce7"


class _Universe:
    """Just enough universe for the metrics/seed paths."""

    def __init__(self, tmp: Path, coded: set[str]):
        self._w3 = _W3(coded)
        self.data_dir = tmp
        self.tick = 30
        self.evm_acex_amm_address = "0x610178da211fef7d417bc0e6fed39f05609ad788"
        self.evm_acex_registry_address = "0x0165878a594ca255338adfa4d48449f69242eb8f"
        self.evm_usdt_address = "0x5fbdb2315678afecb367f032d93f642f64180aa3"
        self.transactions: list = []


def _state_file(tmp: Path) -> Path:
    return tmp / "acex_uni_state.json"


def _write_state(tmp: Path, pools: list[dict]) -> None:
    _state_file(tmp).write_text(json.dumps({
        "pools": pools, "volume_usdc": 281200.0, "trades": 1136, "seeded_at": 1.0,
    }), encoding="utf-8")


def _pools() -> list[dict]:
    return [
        {"slug": "sentinel", "share": SNTL, "symbol": "SNTL"},
        {"slug": "atlas", "share": ATLS, "symbol": "ATLS"},
        {"slug": "gaia", "share": GAIA, "symbol": "GAIA"},
    ]


def _patch_state_path(monkeypatch, tmp: Path) -> None:
    monkeypatch.setattr(acex_uni, "_state_path", lambda u: _state_file(tmp))


class TestCodeCheck:
    def test_a_ghost_address_is_not_a_pool(self):
        w3 = _W3({SNTL})
        assert acex_uni._has_code(w3, SNTL) is True
        assert acex_uni._has_code(w3, ATLS) is False
        assert acex_uni._has_code(w3, None) is False
        assert acex_uni._has_code(None, SNTL) is False


class TestMetrics:
    def test_only_tradeable_pools_count_as_active(self, tmp_path, monkeypatch):
        _patch_state_path(monkeypatch, tmp_path)
        _write_state(tmp_path, _pools())
        universe = _Universe(tmp_path, coded={SNTL})     # two of three are gone

        metrics = acex_uni.acex_metrics_for_monitor(universe)
        assert metrics["pools_active"] == 1
        assert metrics["pools_recorded"] == 3

    def test_cumulative_counters_do_not_wear_a_24h_label(self, tmp_path, monkeypatch):
        _patch_state_path(monkeypatch, tmp_path)
        _write_state(tmp_path, _pools())
        universe = _Universe(tmp_path, coded={SNTL, ATLS, GAIA})

        metrics = acex_uni.acex_metrics_for_monitor(universe)
        assert "volume_24h" not in metrics          # the hub owns that name
        assert "trades" not in metrics
        assert metrics["volume_total_usd"] == 281200.0
        assert metrics["trades_total"] == 1136

    def test_a_dead_market_reports_nothing_active(self, tmp_path, monkeypatch):
        _patch_state_path(monkeypatch, tmp_path)
        _write_state(tmp_path, _pools())
        universe = _Universe(tmp_path, coded=set())

        metrics = acex_uni.acex_metrics_for_monitor(universe)
        assert metrics["pools_active"] == 0
        assert metrics["listings"] == 0
        # …but the turnover that DID happen is not erased.
        assert metrics["volume_total_usd"] == 281200.0


class TestTickSafety:
    def test_a_tick_does_not_swap_against_a_ghost(self, tmp_path, monkeypatch, capsys):
        _patch_state_path(monkeypatch, tmp_path)
        _write_state(tmp_path, _pools())
        monkeypatch.setenv("ALIEN_ACEX_TRADE_TICKS", "30")
        monkeypatch.setattr(acex_uni, "acex_uni_enabled", lambda: True)
        universe = _Universe(tmp_path, coded=set())

        acex_uni.tick_acex_trades(universe)          # must not raise, must not transact
        assert "waiting for a re-seed" in capsys.readouterr().out
