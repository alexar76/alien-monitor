"""The demo chain is written to disk on a timer, not only on a clean exit.

With `--state` alone, a container stop that outlasted its grace period killed Anvil before it
dumped, so everything deployed since the last clean exit vanished: the ACEX stack came back
at new addresses after every restart and the UNI hub and ARGUS-UNI pointed at empty code.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import universe  # noqa: E402


def _anvil_args(monkeypatch, tmp_path, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    seen = []

    class _Proc:
        def __init__(self, args, **kw):
            seen.append(args)

        def poll(self):
            return None

    monkeypatch.setattr(universe.shutil, "which", lambda name: "/usr/bin/" + name if name == "anvil" else None)
    monkeypatch.setattr(universe.subprocess, "Popen", _Proc)
    monkeypatch.setattr(universe, "_universe_solana_enabled", lambda: False)
    u = universe.VirtualUniverse(data_dir=tmp_path)
    monkeypatch.setattr(u, "_kill_chain_orphans", lambda: None)
    monkeypatch.setattr(u, "_trim_oversized_anvil_state", lambda: None)
    monkeypatch.setattr(u, "_wait_for_anvil_rpc", lambda timeout_sec=20: True)
    u._start_blockchain_locked()
    return next(a for a in seen if a and a[0] == "anvil")


def test_state_is_dumped_every_30_seconds_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("ALIEN_ANVIL_STATE_INTERVAL_S", raising=False)
    args = _anvil_args(monkeypatch, tmp_path)
    assert args[args.index("--state-interval") + 1] == "30"
    assert "--state" in args


def test_the_interval_can_be_turned_off(monkeypatch, tmp_path):
    args = _anvil_args(monkeypatch, tmp_path, ALIEN_ANVIL_STATE_INTERVAL_S="0")
    assert "--state-interval" not in args
