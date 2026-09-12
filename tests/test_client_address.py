"""Public rate limits must key on the caller, not on the reverse proxy in front of it.

The monitor runs with ``network_mode: host`` behind
``deploy/nginx/monitor.modelmarket.dev.conf``, so every request's peer is 127.0.0.1. Keying
the AI (20/min) and session (10/5min) buckets on that peer gave the whole internet one
bucket each: one visitor could 429 the public AI panel for everyone, and lock the operator
out of ``/api/auth/session``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from monitor_auth import client_address, trusted_proxies  # noqa: E402


class _Request:
    """The two attributes client_address touches."""

    def __init__(self, peer: str, forwarded: str | None = None) -> None:
        self.client = type("C", (), {"host": peer})()
        self.headers = {"x-forwarded-for": forwarded} if forwarded is not None else {}


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALIEN_TRUSTED_PROXIES", raising=False)


def test_without_a_declared_proxy_the_header_is_ignored() -> None:
    assert client_address(_Request("203.0.113.9", "198.51.100.7")) == "203.0.113.9"


def test_declared_proxy_yields_the_hop_nginx_observed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALIEN_TRUSTED_PROXIES", "127.0.0.1")
    # nginx uses $proxy_add_x_forwarded_for, which APPENDS the real peer to whatever the
    # caller sent. Reading left to right would take the forged value and hand the caller a
    # fresh bucket per request — strictly worse than one shared bucket.
    request = _Request("127.0.0.1", "1.2.3.4, 203.0.113.9")
    assert client_address(request) == "203.0.113.9"


def test_two_callers_behind_the_proxy_do_not_share_a_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALIEN_TRUSTED_PROXIES", "127.0.0.1")
    first = client_address(_Request("127.0.0.1", "203.0.113.9"))
    second = client_address(_Request("127.0.0.1", "198.51.100.7"))
    assert first != second


def test_a_chain_of_only_proxies_falls_back_to_the_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALIEN_TRUSTED_PROXIES", "127.0.0.1,10.0.0.1")
    assert client_address(_Request("127.0.0.1", "10.0.0.1")) == "127.0.0.1"


def test_missing_header_behind_a_proxy_is_not_exempt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALIEN_TRUSTED_PROXIES", "127.0.0.1")
    assert client_address(_Request("127.0.0.1")) == "127.0.0.1"


def test_wildcard_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    # Trusting every peer's header lets any caller name its own address.
    monkeypatch.setenv("ALIEN_TRUSTED_PROXIES", "*")
    assert trusted_proxies() == frozenset()
    assert client_address(_Request("127.0.0.1", "1.2.3.4")) == "127.0.0.1"


def test_peerless_request_is_still_keyed() -> None:
    request = _Request("")
    request.client = None
    assert client_address(request) == "unknown"
