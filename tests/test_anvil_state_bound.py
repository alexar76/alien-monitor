"""The demo chain's state file must be bounded WHILE RUNNING, not only at start.

`--block-time 2` mines forever and `--state` writes every block, so the file grows for as long as the
container lives. The existing cap runs once, just before anvil is launched, which bounds how slow a
*start* can be and nothing else.

That gap cost a real outage on the oracle host: five days of uptime took `state.json` to **1.73 GB**,
which was 3.9 GB of RSS on a 12 GB box with swap exhausted — and then anvil could no longer load its
own state inside the readiness timeout, so the chain came back dead on the next restart. The
start-time cap did fire, but only after the damage, on the boot that was already broken.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from universe import VirtualUniverse  # noqa: E402


@pytest.fixture
def universe(tmp_path, monkeypatch):
    monkeypatch.setenv("ALIEN_UNIVERSE_ANVIL_STATE_DIR", str(tmp_path / "anvil-state"))
    monkeypatch.setenv("ALIEN_ANVIL_STATE_MAX_MB", "1")
    monkeypatch.setenv("ALIEN_ANVIL_STATE_CHECK_TICKS", "10")
    u = VirtualUniverse.__new__(VirtualUniverse)     # no bootstrap, no anvil, no network
    u.tick = 0
    u._bootstrap_notes = []
    u.data_dir = tmp_path
    return u


def _write_state(u, mb: float) -> None:
    state = u._anvil_state_dir() / "state.json"
    state.write_bytes(b"x" * int(mb * 1024 * 1024))


def _record_calls(u, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(u, "stop_blockchain", lambda: calls.append("stop"), raising=False)
    monkeypatch.setattr(u, "_reset_anvil_state", lambda: calls.append("reset"), raising=False)
    monkeypatch.setattr(u, "bootstrap", lambda: calls.append("bootstrap"), raising=False)
    return calls


def test_a_small_state_is_left_alone(universe, monkeypatch):
    calls = _record_calls(universe, monkeypatch)
    _write_state(universe, 0.2)
    universe.tick = 10
    universe._recycle_anvil_if_oversized()
    assert calls == []


def test_an_oversized_state_is_recycled_in_run(universe, monkeypatch):
    """The whole point: this must happen without waiting for a restart, because by the time a
    restart comes the file is already too big to load and the host is already starved."""
    calls = _record_calls(universe, monkeypatch)
    _write_state(universe, 2.0)                      # cap is 1 MB
    universe.tick = 10
    universe._recycle_anvil_if_oversized()
    assert calls == ["stop", "reset", "bootstrap"], calls
    note = " ".join(universe._bootstrap_notes)
    assert "grew to 2MB while running" in note and "cap 1MB" in note
    # The note has to say what was dropped and why, or an operator sees a chain reset itself with
    # no explanation.
    assert "contracts" in note


def test_the_check_does_not_run_every_tick(universe, monkeypatch):
    """Sizing the directory means stat()ing it; doing that on every tick of a 2s loop is wasteful,
    so the interval is the point, not an accident."""
    calls = _record_calls(universe, monkeypatch)
    _write_state(universe, 2.0)
    for tick in (1, 2, 3, 9, 11, 19):
        universe.tick = tick
        universe._recycle_anvil_if_oversized()
    assert calls == [], "no check should have fired off-interval"
    universe.tick = 20
    universe._recycle_anvil_if_oversized()
    assert calls == ["stop", "reset", "bootstrap"]


def test_tick_one_never_recycles(universe, monkeypatch):
    """Bootstrap has just run its own start-time cap; recycling immediately would double the work
    and reset a chain whose contracts were deployed seconds ago."""
    calls = _record_calls(universe, monkeypatch)
    _write_state(universe, 5.0)
    universe.tick = 1
    universe._recycle_anvil_if_oversized()
    assert calls == []


def test_a_failure_while_recycling_does_not_break_the_tick(universe, monkeypatch):
    """A tick that raises takes the whole monitor loop down with it. Recycling is best-effort."""
    _write_state(universe, 2.0)
    monkeypatch.setattr(universe, "stop_blockchain",
                        lambda: (_ for _ in ()).throw(RuntimeError("docker said no")),
                        raising=False)
    universe.tick = 10
    universe._recycle_anvil_if_oversized()           # must not raise
    assert any("grew to" in n for n in universe._bootstrap_notes)
