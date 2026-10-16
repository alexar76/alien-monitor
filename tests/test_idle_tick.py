"""The state ticker polls hard only while somebody is watching.

It used to poll every satellite every 1.5 s around the clock. On the attested host that was
the hub's /stats/live and /.well-known every tick with zero viewers, ~25% of a core, and on
2026-10-16 it was the load that kept the hub's /health queued while the CPU was crowded:
hub.attestedmemory.net went down twice. These pin the slow idle tick, the early wake when a
viewer arrives, and the /.well-known memo.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import main  # noqa: E402


class _Viewer:
    def __init__(self) -> None:
        self.frames = 0

    async def send_text(self, _payload: str) -> None:
        self.frames += 1


@pytest.fixture
def fast_clock(monkeypatch):
    """Ticks scaled down 30x so the test runs in about a second."""
    monkeypatch.setattr(main, "STATE_TICK_INTERVAL", 0.05)
    monkeypatch.setattr(main, "STATE_IDLE_TICK_INTERVAL", 0.6)
    ticks: list[float] = []

    async def fake_state(_mode=None):
        ticks.append(time.monotonic())
        return {"nodes": [{"id": "hub"}], "summary": {}}

    monkeypatch.setattr(main, "_fetch_monitor_state", fake_state)
    monkeypatch.setattr(main, "CONNECTED_CLIENTS", set())
    monkeypatch.setattr(main, "_viewer_arrived", asyncio.Event())
    return ticks


async def _run_broadcaster(seconds: float, during=None) -> None:
    task = asyncio.create_task(main._monitor_broadcaster())
    try:
        if during is not None:
            await during()
        await asyncio.sleep(seconds)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


def test_interval_depends_on_viewers(monkeypatch):
    monkeypatch.setattr(main, "STATE_TICK_INTERVAL", 1.5)
    monkeypatch.setattr(main, "STATE_IDLE_TICK_INTERVAL", 20.0)
    monkeypatch.setattr(main, "CONNECTED_CLIENTS", set())
    assert main._tick_interval() == 20.0
    main.CONNECTED_CLIENTS.add(object())
    assert main._tick_interval() == 1.5


def test_idle_interval_never_speeds_the_ticker_up(monkeypatch):
    """An operator who set a slow ALIEN_STATE_TICK_SEC keeps it when nobody is watching."""
    monkeypatch.setattr(main, "STATE_TICK_INTERVAL", 60.0)
    monkeypatch.setattr(main, "STATE_IDLE_TICK_INTERVAL", 20.0)
    monkeypatch.setattr(main, "CONNECTED_CLIENTS", set())
    assert main._tick_interval() == 60.0


def test_nobody_watching_means_few_polls(fast_clock):
    asyncio.run(_run_broadcaster(1.5))
    # 0.3 s warm-up, then one tick per 0.6 s: 2-3 ticks. At the viewer rate it would be ~24.
    assert 1 <= len(fast_clock) <= 4, fast_clock


def test_a_viewer_gets_the_fast_rate(fast_clock):
    viewer = _Viewer()
    main.CONNECTED_CLIENTS.add(viewer)
    asyncio.run(_run_broadcaster(1.5))
    assert len(fast_clock) >= 12, len(fast_clock)
    assert viewer.frames == len(fast_clock)


def test_a_viewer_arriving_wakes_an_idle_ticker(fast_clock, monkeypatch):
    monkeypatch.setattr(main, "STATE_IDLE_TICK_INTERVAL", 30.0)

    async def connect_after_first_tick():
        await asyncio.sleep(0.5)  # first tick at 0.3 s, then a 30 s idle sleep begins
        assert len(fast_clock) == 1
        main.CONNECTED_CLIENTS.add(_Viewer())
        main._viewer_arrived.set()  # what websocket_endpoint does on accept
        connected_at.append(time.monotonic())

    connected_at: list[float] = []
    asyncio.run(_run_broadcaster(0.3, during=connect_after_first_tick))
    assert len(fast_clock) >= 3
    assert fast_clock[1] - connected_at[0] < 0.2, "the ticker slept through a new viewer"


def test_the_websocket_handler_wakes_the_ticker():
    import inspect

    src = inspect.getsource(main.websocket_endpoint)
    assert "_viewer_arrived.set()" in src


# ── /.well-known memo ───────────────────────────────────────────


def _hub(counter: list[str], *, fail: bool = False):
    def handler(request: httpx.Request) -> httpx.Response:
        counter.append(request.url.path)
        if fail:
            raise httpx.ConnectError("down")
        return httpx.Response(200, json={"name": "Attested Memory Hub"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def fresh_identity(monkeypatch):
    monkeypatch.setattr(main, "_hub_identity_cache", {"at": 0.0, "doc": None})
    monkeypatch.setattr(main, "HUB_IDENTITY_TTL", 300.0)


def test_well_known_is_fetched_once_per_ttl(fresh_identity):
    calls: list[str] = []

    async def scenario():
        async with _hub(calls) as client:
            for _ in range(5):
                errors: list[str] = []
                doc = await main._hub_identity(client, errors)
                assert doc == {"name": "Attested Memory Hub"}
                assert errors == []

    asyncio.run(scenario())
    assert calls == ["/.well-known/ai-market.json"]


def test_well_known_refreshes_after_the_ttl(fresh_identity, monkeypatch):
    calls: list[str] = []

    async def scenario():
        async with _hub(calls) as client:
            await main._hub_identity(client, [])
            monkeypatch.setattr(main, "HUB_IDENTITY_TTL", 0.0)
            await main._hub_identity(client, [])

    asyncio.run(scenario())
    assert len(calls) == 2


def test_a_failed_refresh_keeps_the_name_and_reports(fresh_identity, monkeypatch):
    calls: list[str] = []

    async def scenario():
        async with _hub(calls) as client:
            await main._hub_identity(client, [])
        monkeypatch.setattr(main, "HUB_IDENTITY_TTL", 0.0)
        errors: list[str] = []
        async with _hub(calls, fail=True) as client:
            doc = await main._hub_identity(client, errors)
        return doc, errors

    doc, errors = asyncio.run(scenario())
    assert doc == {"name": "Attested Memory Hub"}
    assert errors and errors[0].startswith("hub identity unavailable")
