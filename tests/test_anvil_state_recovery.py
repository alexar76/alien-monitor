"""A state dump cut short must not take the demo chain down for good.

2026-10-03 15:44 UTC: the watchdog killed anvil while it was writing ``state.json``. The file
ended mid-string, anvil refused it on every start with its stderr discarded, and the monitor
logged "anvil rpc timeout after 90s (loading 4MB of state)" every 90 s for 14 hours while the
UNI demo chain (charity lottery, ACEX) was gone.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from universe import VirtualUniverse  # noqa: E402

GOOD = {"block": {"number": "0x31"}, "accounts": {"0xabc": {"nonce": 7}}}


@pytest.fixture
def universe(tmp_path, monkeypatch):
    monkeypatch.setenv("ALIEN_UNIVERSE_ANVIL_STATE_DIR", str(tmp_path / "anvil-state"))
    u = VirtualUniverse.__new__(VirtualUniverse)     # no bootstrap, no anvil, no network
    u.tick = 0
    u._bootstrap_notes = []
    u.data_dir = tmp_path
    return u


def _state(u) -> Path:
    return u._anvil_state_dir() / "state.json"


def test_a_truncated_state_is_moved_aside_and_the_good_copy_restored(universe):
    _state(universe).write_text(json.dumps(GOOD))
    universe._keep_last_good_anvil_state()
    _state(universe).write_text(json.dumps(GOOD)[:-9])      # a dump cut short

    universe._quarantine_unreadable_anvil_state()

    assert json.loads(_state(universe).read_text()) == GOOD
    aside = list(universe._anvil_state_dir().parent.glob("anvil-state.unreadable-*.json"))
    assert len(aside) == 1, "the broken file is kept for whoever looks, not deleted"
    assert "restored the last good copy" in universe._bootstrap_notes[-1]


def test_without_a_good_copy_the_chain_starts_empty(universe):
    _state(universe).write_text('{"block": {"num')
    universe._quarantine_unreadable_anvil_state()
    assert not _state(universe).exists()
    assert "contracts are redeployed" in universe._bootstrap_notes[-1]


def test_a_readable_state_is_left_alone(universe):
    _state(universe).write_text(json.dumps(GOOD))
    universe._quarantine_unreadable_anvil_state()
    assert json.loads(_state(universe).read_text()) == GOOD
    assert universe._bootstrap_notes == []


def test_an_unreadable_state_never_becomes_the_good_copy(universe):
    _state(universe).write_text(json.dumps(GOOD))
    universe._keep_last_good_anvil_state()
    _state(universe).write_text("{broken")
    universe._keep_last_good_anvil_state()
    assert json.loads(universe._anvil_good_state_path().read_text()) == GOOD


def test_the_good_copy_is_outside_the_state_dir(universe):
    """Inside, the size cap would count it twice and anvil could read it."""
    assert universe._anvil_good_state_path().parent != universe._anvil_state_dir()


def test_a_reset_drops_the_good_copy_too(universe):
    _state(universe).write_text(json.dumps(GOOD))
    universe._keep_last_good_anvil_state()
    universe._reset_anvil_state()
    assert not universe._anvil_good_state_path().exists()


class _Alive:
    def poll(self):
        return None


def test_one_missed_probe_does_not_kill_a_live_anvil(universe, monkeypatch):
    monkeypatch.setenv("ALIEN_ANVIL_WATCHDOG_TICKS", "1")
    universe.anvil_proc = _Alive()
    universe.blockchain_ready = True
    universe._anvil_watchdog_cooldown_until = 0
    stops: list[int] = []
    monkeypatch.setattr(universe, "_wait_for_anvil_rpc", lambda timeout_sec: False, raising=False)
    monkeypatch.setattr(universe, "stop_blockchain", lambda: stops.append(1), raising=False)
    monkeypatch.setattr(universe, "bootstrap", lambda: {"ok": True}, raising=False)

    universe.tick = 2
    universe._ensure_anvil_alive()
    assert stops == [], "a live anvil busy writing its state can miss one probe"
    universe.tick = 3
    universe._ensure_anvil_alive()
    assert stops == [1], "a second miss in a row means it is down"
