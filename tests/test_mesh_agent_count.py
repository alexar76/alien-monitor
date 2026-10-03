"""The AGENTS counter read a field the mesh has never emitted.

Found from the live dashboard on 2026-09-05: `monitor.modelmarket.dev` showed AGENTS: 0
while `GET http://127.0.0.1:8090/v1/stats` answered

    {"agents_total": 3, "agents_verified": 3, "tasks_24h": 0, ...}

The monitor read `agents` / `agents_online`. Neither exists in that payload, so three real,
verified agents rendered as a zero — and a zero on a dashboard is indistinguishable from
"nothing is deployed", which is exactly how it was read.

Two call sites had the same expression copied, so a rename could fix one and miss the other.
They now share `mesh_agent_count`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from chain_metrics import mesh_agent_count  # noqa: E402


def test_the_shape_the_mesh_actually_returns():
    """Verbatim from the live mesh."""
    assert mesh_agent_count({
        "agents_total": 3, "agents_verified": 3, "tasks_24h": 0,
        "mesh_hops_24h": 0, "success_rate_24h": 1.0, "volume_usd_24h": 0.0,
    }) == 3


def test_the_older_names_still_win_when_present():
    """A mesh that does emit them must not be overridden by a fallback."""
    assert mesh_agent_count({"agents_online": 7}) == 7
    assert mesh_agent_count({"agents": 5, "agents_total": 99}) == 5


def test_verified_covers_a_zero_total():
    assert mesh_agent_count({"agents_total": 0, "agents_verified": 2}) == 2


def test_absence_is_zero_and_junk_does_not_raise():
    """A metrics reader may never take the dashboard down."""
    assert mesh_agent_count({}) == 0
    assert mesh_agent_count(None) == 0
    assert mesh_agent_count("not a dict") == 0
    assert mesh_agent_count({"agents_total": "abc"}) == 0


def test_both_readers_use_the_one_helper():
    """The bug was one expression copied into two files."""
    root = Path(__file__).resolve().parents[1] / "backend"
    for name in ("chain_metrics.py", "main.py"):
        src = (root / name).read_text(encoding="utf-8")
        assert 'get("agents_online")' not in src, (
            f"{name} reads the mesh field by hand again — use mesh_agent_count()")
