"""GAIA's device registry is fetched on its own, longer cycle than /health.

Every monitor asked for the whole 880-device registry (456 KB) on each 30 s poll: three
monitors, ~3.9 GB a day, for a list that changes on a deploy. /health stays on the poll;
the registry is refetched every ALIEN_GAIA_FLEET_CACHE_TTL (300 s).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import gaia_status  # noqa: E402
import poll_cache  # noqa: E402

DEVICE = {"device_id": "ws-01", "model": "WS", "site": "s", "fields": {"t": "C"},
          "online": True, "fault": "none", "readings_recorded": 3, "source": None}


class _Resp:
    def __init__(self, status: int, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


class _FakeGaia:
    """Counts what the monitor asks GAIA for."""

    def __init__(self):
        self.health = 0
        self.fleet = 0
        self.fleet_ok = True

    def client(self, *a, **k):
        gaia = self

        class _Client:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def get(self, url):
                gaia.health += 1
                return _Resp(200, {"status": "ok", "service": "gaia", "devices": 1})

            def post(self, url, json=None):
                gaia.fleet += 1
                if not gaia.fleet_ok:
                    return _Resp(503, {})
                return _Resp(200, {"ok": True, "output": {"devices": [DEVICE], "count": 1}})

        return _Client()


@pytest.fixture
def gaia(monkeypatch):
    fake = _FakeGaia()
    monkeypatch.setattr(gaia_status.httpx, "Client", fake.client)
    monkeypatch.delenv("ALIEN_GAIA_FLEET_CACHE_TTL", raising=False)
    monkeypatch.delenv("ALIEN_POLL_CACHE_TTL", raising=False)
    clock = [1000.0]
    monkeypatch.setattr(poll_cache.time, "monotonic", lambda: clock[0])
    gaia_status._fetch_fleet_devices.cache_clear()
    gaia_status.fetch_gaia_status_sync.cache_clear()
    yield fake, clock
    gaia_status._fetch_fleet_devices.cache_clear()
    gaia_status.fetch_gaia_status_sync.cache_clear()


def _poll():
    return gaia_status.fetch_gaia_status_sync(base_url="https://gaia.test", force_refresh=True)


def test_health_every_poll_registry_once_per_five_minutes(gaia):
    fake, clock = gaia
    for _ in range(10):                      # ten 30 s polls = 5 minutes
        status = _poll()
        assert status["devices"][0]["id"] == "ws-01"
        clock[0] += 29
    assert fake.health == 10 and fake.fleet == 1
    clock[0] += 30                           # past 300 s since the first fetch
    _poll()
    assert fake.fleet == 2


def test_a_failed_registry_read_keeps_the_last_good_list(gaia):
    fake, clock = gaia
    _poll()
    fake.fleet_ok = False
    clock[0] += 301
    status = _poll()                          # refetch fails: last good list, not a blank panel
    assert fake.fleet == 2 and status["devices"][0]["id"] == "ws-01"


def test_the_operator_can_make_it_refetch_every_poll(gaia, monkeypatch):
    fake, clock = gaia
    monkeypatch.setenv("ALIEN_GAIA_FLEET_CACHE_TTL", "0")
    for _ in range(3):
        _poll()
    assert fake.fleet == 3


def test_health_down_shows_offline_once_the_grace_runs_out(gaia, monkeypatch):
    """The registry cache never keeps a dead GAIA looking alive: /health decides, and the
    30 s poll cache covers a blip for two cycles at most."""
    fake, clock = gaia
    assert _poll() is not None

    def down(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(gaia_status.httpx, "Client", down)
    clock[0] += 31
    assert _poll() is not None               # a blip: the last good status covers it
    clock[0] += 40                           # 71 s since the last good read, past 2 × 30 s
    assert _poll() is None
