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

import os
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from universe import VirtualUniverse, sweep_foundry_anvil_tmp  # noqa: E402


@pytest.fixture
def universe(tmp_path, monkeypatch):
    monkeypatch.setenv("ALIEN_UNIVERSE_ANVIL_STATE_DIR", str(tmp_path / "anvil-state"))
    monkeypatch.setenv("ALIEN_ANVIL_STATE_MAX_MB", "1")
    monkeypatch.setenv("ALIEN_ANVIL_STATE_CHECK_TICKS", "10")
    monkeypatch.setenv("ALIEN_FOUNDRY_ANVIL_TMP_DIR", str(tmp_path / "foundry-tmp"))
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


def _dump_tree(tmp: Path, name: str, n_files: int, *, mtime: float, size: int = 64) -> Path:
    dump = tmp / name
    dump.mkdir(parents=True)
    for i in range(n_files):
        f = dump / f"{i:04d}.json"
        f.write_bytes(b"x" * size)
        os.utime(f, (mtime + i, mtime + i))
    os.utime(dump, (mtime, mtime))
    return dump


def test_foundry_tmp_keeps_one_dir_and_drops_the_rest(tmp_path, monkeypatch):
    """The 35 GB outage was five anvil-state-* trees Foundry never reaps. The --state cap
    never sees them, so this sweeper has to exist as its own pass."""
    monkeypatch.setenv("ALIEN_FOUNDRY_ANVIL_TMP_KEEP_DIRS", "1")
    monkeypatch.setenv("ALIEN_FOUNDRY_ANVIL_TMP_KEEP_FILES", "3")
    monkeypatch.setenv("ALIEN_FOUNDRY_ANVIL_TMP_MAX_MB", "256")
    tmp = tmp_path / "foundry-tmp"
    _dump_tree(tmp, "anvil-state-old", 8, mtime=1_000)
    _dump_tree(tmp, "anvil-state-mid", 8, mtime=2_000)
    newest = _dump_tree(tmp, "anvil-state-new", 8, mtime=3_000)
    stats = sweep_foundry_anvil_tmp(tmp)
    assert not (tmp / "anvil-state-old").exists()
    assert not (tmp / "anvil-state-mid").exists()
    assert newest.is_dir()
    kept = sorted(p.name for p in newest.iterdir())
    assert kept == ["0005.json", "0006.json", "0007.json"], kept
    assert stats["removed_dirs"] == 2
    assert stats["removed_files"] >= 5


def test_foundry_tmp_size_cap_drops_the_kept_dir_too(tmp_path, monkeypatch):
    monkeypatch.setenv("ALIEN_FOUNDRY_ANVIL_TMP_KEEP_DIRS", "1")
    monkeypatch.setenv("ALIEN_FOUNDRY_ANVIL_TMP_KEEP_FILES", "3")
    monkeypatch.setenv("ALIEN_FOUNDRY_ANVIL_TMP_MAX_MB", "1")
    tmp = tmp_path / "foundry-tmp"
    # 3 files × 1 MB = 3 MB after the keep-files pass, over the 1 MB cap.
    _dump_tree(tmp, "anvil-state-fat", 3, mtime=4_000, size=1024 * 1024)
    stats = sweep_foundry_anvil_tmp(tmp)
    remaining = _path_bytes_for_test(tmp)
    assert remaining <= 1 * 1024 * 1024, remaining
    assert stats["removed_files"] + stats["removed_dirs"] >= 1


def _path_bytes_for_test(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for p in path.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total


def test_a_small_state_still_sweeps_foundry_tmp(universe, tmp_path):
    """The 35 GB dumps were not state.json. Recycle used to return early when the
    --state file was under the cap, which is exactly when the dumps needed reaping."""
    tmp = tmp_path / "foundry-tmp"
    _dump_tree(tmp, "anvil-state-old", 6, mtime=1_000)
    _dump_tree(tmp, "anvil-state-new", 6, mtime=2_000)
    _write_state(universe, 0.2)
    universe.tick = 10
    universe._recycle_anvil_if_oversized()
    assert not (tmp / "anvil-state-old").exists()
    kept = tmp / "anvil-state-new"
    assert kept.is_dir()
    assert len(list(kept.iterdir())) <= 3


def test_foundry_tmp_sweep_does_not_raise(tmp_path, monkeypatch):
    monkeypatch.setenv("ALIEN_FOUNDRY_ANVIL_TMP_KEEP_DIRS", "not-a-number")
    # Missing dir, garbage env — the tick must survive.
    sweep_foundry_anvil_tmp(tmp_path / "no-such")
    sweep_foundry_anvil_tmp(tmp_path)
