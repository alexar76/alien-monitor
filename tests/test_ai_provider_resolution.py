"""A configured default that cannot be called is not a default.

The shipped config names `deepseek_api`. A deployment without DEEPSEEK_API_KEY answered
every question with "empty answer" while a perfectly good provider sat next to it in the
same file with its key present — which is what the monitor's AI panel did in production.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

CONFIG = """
default_provider: deepseek_api
providers:
  deepseek_api:
    api_key_env: DEEPSEEK_API_KEY
    base_url: https://api.deepseek.com/v1
    enabled: true
    provider_type: openai_compatible
    models: {heavy: deepseek-v4-pro, light: deepseek-v4-flash}
  openrouter_api:
    api_key_env: OPENROUTER_API_KEY
    base_url: https://openrouter.ai/api/v1
    enabled: true
    provider_type: openai_compatible
    models: {heavy: minimax/minimax-m3, light: minimax/minimax-m3}
"""


@pytest.fixture
def ai(tmp_path, monkeypatch):
    cfg = tmp_path / "model_providers.yaml"
    cfg.write_text(CONFIG, encoding="utf-8")
    monkeypatch.setenv("ALIEN_LLM_CONFIG", str(cfg))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ALIEN_AI_PROVIDER", raising=False)
    import ai_assistant

    importlib.reload(ai_assistant)
    yield ai_assistant
    importlib.reload(ai_assistant)


def test_falls_through_to_a_provider_that_has_a_key(ai, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    ai._config_cache = None
    assert ai.resolve_default_provider() == "openrouter_api"
    assert ai.list_providers()["providers"], "the available provider must be listed"


def test_the_named_default_wins_when_it_can_actually_be_called(ai, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    ai._config_cache = None
    assert ai.resolve_default_provider() == "deepseek_api"


def test_the_operator_can_pin_one(ai, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("ALIEN_AI_PROVIDER", "openrouter_api")
    ai._config_cache = None
    assert ai.resolve_default_provider() == "openrouter_api"
    assert ai.list_providers()["default_provider"] == "openrouter_api", (
        "the panel must show the provider that will answer"
    )


def test_a_pin_at_a_provider_this_deployment_does_not_have_is_ignored(ai, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("ALIEN_AI_PROVIDER", "some_provider_we_never_configured")
    ai._config_cache = None
    assert ai.resolve_default_provider() == "openrouter_api"
