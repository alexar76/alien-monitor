"""The simulated buyer must not transact against a hub that takes real money.

Found in production on 2026-08-24: the buyer's default hub URL is loopback, the monitor runs
with host networking, so "loopback" was the live payment API — and every round ended in
`400 on-chain verification unavailable`, once every ~40 seconds, indefinitely. A demo cannot
fund an escrow-backed channel, so the refusals were structural, not transient.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _backend() -> Path:
    for candidate in (Path(__file__).resolve().parents[1] / "backend",
                      Path(os.environ.get("ALIEN_BACKEND_DIR", "") or "/app/backend")):
        if (candidate / "universe_external_buyer.py").is_file():
            return candidate
    raise RuntimeError("backend not found")


sys.path.insert(0, str(_backend()))

import universe_external_buyer as ueb   # noqa: E402


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _Client:
    def __init__(self, payload=None, raise_on_get=False):
        self._payload = payload
        self._raise = raise_on_get

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url):
        if self._raise:
            raise ConnectionError("no route")
        return _Resp(self._payload)


def _buyer(monkeypatch, payload, *, raise_on_get=False, allow=None):
    monkeypatch.delenv("ALIEN_UNIVERSE_BUYER_ALLOW_REAL_HUB", raising=False)
    if allow is not None:
        monkeypatch.setenv("ALIEN_UNIVERSE_BUYER_ALLOW_REAL_HUB", allow)
    monkeypatch.setattr(ueb.httpx, "Client",
                        lambda *a, **k: _Client(payload, raise_on_get=raise_on_get))
    return ueb.ExternalAIBuyer(hub_url="http://127.0.0.1:9083")


def test_a_real_money_hub_halts_the_buyer(monkeypatch):
    buyer = _buyer(monkeypatch, {"payment_configured": True, "payment_testnet": False})
    out = buyer.execute_round(vu=None)
    assert out["purchases"] == 0
    assert "real-money hub" in out["halted"]


def test_a_sandbox_hub_is_allowed(monkeypatch):
    buyer = _buyer(monkeypatch, {"payment_configured": False})
    assert buyer._hub_takes_real_money() is False


def test_a_testnet_hub_is_allowed(monkeypatch):
    buyer = _buyer(monkeypatch, {"payment_configured": True, "payment_testnet": True})
    assert buyer._hub_takes_real_money() is False


def test_an_unreachable_hub_counts_as_real(monkeypatch):
    """Fail closed: a simulation must not decide it may transact because it could not tell."""
    buyer = _buyer(monkeypatch, None, raise_on_get=True)
    assert buyer._hub_takes_real_money() is True


def test_the_operator_can_override(monkeypatch):
    buyer = _buyer(monkeypatch, {"payment_configured": True, "payment_testnet": False}, allow="1")
    assert buyer._hub_takes_real_money() is False


def test_the_posture_is_asked_once(monkeypatch):
    calls = {"n": 0}

    class Counting(_Client):
        def get(self, url):
            calls["n"] += 1
            return _Resp({"payment_configured": True, "payment_testnet": False})

    monkeypatch.delenv("ALIEN_UNIVERSE_BUYER_ALLOW_REAL_HUB", raising=False)
    monkeypatch.setattr(ueb.httpx, "Client", lambda *a, **k: Counting(None))
    buyer = ueb.ExternalAIBuyer(hub_url="http://127.0.0.1:9083")
    for _ in range(5):
        buyer.execute_round(vu=None)
    assert calls["n"] == 1, "the guard re-probed the hub on every round"


def test_the_hub_url_is_configurable(monkeypatch):
    monkeypatch.setenv("ALIEN_UNIVERSE_BUYER_HUB_URL", "http://sandbox.local:9083/")
    buyer = ueb.ExternalAIBuyer()
    assert buyer.hub_url == "http://sandbox.local:9083"
