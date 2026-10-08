"""The public AI panel spends the operator's provider key, so it has a budget, not only a
per-address limit: an IPv6 /64 or a proxy pool has as many addresses as the caller wants.
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

os.environ.setdefault("ALIEN_API_TOKEN", "test-monitor-token")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import ai_assistant  # noqa: E402
import main  # noqa: E402


def _request(addr: str):
    return SimpleNamespace(client=SimpleNamespace(host=addr), headers={})


@pytest.fixture(autouse=True)
def _fresh_buckets(monkeypatch):
    monkeypatch.setattr(main, "_AI_ASK_HITS", {})
    monkeypatch.setattr(main, "_AI_ASK_GLOBAL", [], raising=False)


def test_every_address_in_one_ipv6_64_shares_a_bucket(monkeypatch):
    monkeypatch.setattr(main, "_AI_ASK_LIMIT", 2)
    main._ai_ask_rate_limit(_request("2001:db8:1:2::1"))
    main._ai_ask_rate_limit(_request("2001:db8:1:2::ffff"))
    with pytest.raises(HTTPException) as exc:
        main._ai_ask_rate_limit(_request("2001:db8:1:2:abcd::9"))
    assert exc.value.status_code == 429
    main._ai_ask_rate_limit(_request("2001:db8:1:3::1"))  # another /64


def test_fresh_addresses_still_meet_the_hourly_ceiling(monkeypatch):
    monkeypatch.setattr(main, "_AI_ASK_LIMIT", 1000)
    monkeypatch.setattr(main, "_AI_ASK_MAX_PER_HOUR", 3, raising=False)
    for i in range(3):
        main._ai_ask_rate_limit(_request(f"198.51.100.{i + 1}"))
    with pytest.raises(HTTPException) as exc:
        main._ai_ask_rate_limit(_request("198.51.100.200"))
    assert exc.value.status_code == 429
    assert "hourly" in exc.value.detail


def test_a_disabled_provider_named_by_the_caller_is_not_used(monkeypatch):
    cfg = {
        "default_provider": "on",
        "providers": {
            "on": {"enabled": True, "provider_type": "openai_compatible", "api_key": "k1",
                   "base_url": "https://on.example/v1", "models": {"heavy": "m"}},
            "off": {"enabled": False, "provider_type": "openai_compatible", "api_key": "k2",
                    "base_url": "https://off.example/v1", "models": {"heavy": "m"}},
        },
    }
    monkeypatch.setattr(ai_assistant, "load_providers_config", lambda: cfg)
    monkeypatch.setattr(ai_assistant, "resolve_default_provider", lambda: "on")
    used = {}

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, *a, **kw):
            used["url"] = url
            raise RuntimeError("stop before the network")

    monkeypatch.setattr(ai_assistant.httpx, "AsyncClient", _Client)
    import asyncio

    try:
        asyncio.run(ai_assistant.generate_answer(
            question="hi", locale="en", system_prompt="s", provider_id="off"))
    except Exception:  # noqa: BLE001 - only which host was called matters here
        pass
    assert "on.example" in used.get("url", ""), used
