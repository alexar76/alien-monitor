"""MiniMax as the monitor's LLM, and the two things that make it actually answer.

The assistant was falling back to its offline responder because no provider had a key
(`deepseek_api` ships the placeholder `sk-keep`). MiniMax is the model this ecosystem
already prices and benchmarks — `minimax/minimax-m3` via OpenRouter, see
`llm/pricing_estimate.py` and `metis/config.production.yaml` — so that is the route wired
here rather than a second, unvalidated one.

Two traps come with it, both already paid for elsewhere in this repo:

* MiniMax M3 spends `max_tokens` on hidden reasoning and returns HTTP 200 with an EMPTY
  `content` when the budget runs out first. Measured live on 2026-09-07:
  `max_tokens=300` → 299 reasoning tokens, `finish_reason=length`, `content=''`;
  `max_tokens=4096` → 159 reasoning tokens and a real answer. `reasoning.exclude` only
  keeps the thinking out of the RESPONSE (it is generated and billed regardless), so the
  fix is the floor on the budget, not the flag.
* OpenRouter attributes spend by `HTTP-Referer` / `X-Title`; without them the monitor's
  traffic is an unlabelled share of the factory's bill.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import ai_assistant as ai

_REPO = Path(__file__).resolve().parent.parent.parent
_PROVIDERS = _REPO / "data" / "config" / "model_providers.yaml"


def _require_monorepo_providers() -> dict:
    if not _PROVIDERS.is_file():
        pytest.skip("data/config/model_providers.yaml not in this checkout (satellite CI)")
    return yaml.safe_load(_PROVIDERS.read_text())


class TestConfigEntry:
    def test_minimax_is_a_configured_provider(self):
        cfg = _require_monorepo_providers()
        entry = cfg["providers"]["openrouter_api"]
        assert entry["enabled"] is True
        assert entry["provider_type"] == "openai_compatible"
        assert entry["base_url"] == "https://openrouter.ai/api/v1"
        assert entry["api_key_env"] == "OPENROUTER_API_KEY"
        # The slug the rest of the ecosystem already prices, not an invented model id.
        assert entry["models"]["heavy"] == "minimax/minimax-m3"

    def test_the_key_is_not_in_the_file(self):
        """A provider key belongs in the environment; `deepseek_api` ships `sk-keep`."""
        cfg = _require_monorepo_providers()
        assert not cfg["providers"]["openrouter_api"].get("api_key")

    def test_the_id_is_the_one_production_already_pins(self):
        """Both deployed monitors run `ALIEN_AI_PROVIDER=openrouter_api`.

        The name did not exist in the config, and `resolve_default_provider` ignored the
        pin in silence — so the operator's stated choice of OpenRouter had been falling
        through to `deepseek_api` and its placeholder `sk-keep` key.
        """
        cfg = _require_monorepo_providers()
        assert "openrouter_api" in cfg["providers"]

    def test_pinning_it_makes_it_the_default(self, monkeypatch):
        monkeypatch.setenv("ALIEN_AI_PROVIDER", "openrouter_api")
        ai._config_cache = None
        try:
            assert ai.resolve_default_provider() == "openrouter_api"
        finally:
            ai._config_cache = None


class TestReasoningBudget:
    def test_minimax_on_openrouter_reserves_its_answer_budget(self):
        payload = ai._reasoning_payload("https://openrouter.ai/api/v1", "minimax/minimax-m3")
        assert payload == {"reasoning": {"effort": "low", "exclude": True}}

    def test_a_plain_model_is_left_alone(self):
        assert ai._reasoning_payload("https://openrouter.ai/api/v1", "openai/gpt-4o-mini") == {}

    def test_only_openrouter_takes_the_parameter(self):
        """DeepSeek's own API rejects unknown top-level fields."""
        assert ai._reasoning_payload("https://api.deepseek.com/v1", "minimax/minimax-m3") == {}

    @pytest.mark.parametrize("model", ["minimax/minimax-m3", "deepseek-r2", "qwen/qwq-32b"])
    def test_reasoning_models_are_recognised(self, model):
        assert ai._is_reasoning_model(model)


class TestAnswerBudget:
    def test_a_reasoning_model_gets_room_for_an_answer(self):
        """300 tokens went entirely to reasoning on the live probe; 2048 is the floor."""
        assert ai._answer_token_budget(300, "minimax/minimax-m3") == ai._REASONING_MIN_MAX_TOKENS
        assert ai._REASONING_MIN_MAX_TOKENS >= 2048

    def test_a_generous_budget_is_left_alone(self):
        assert ai._answer_token_budget(4096, "minimax/minimax-m3") == 4096

    def test_a_plain_model_keeps_its_configured_budget(self):
        assert ai._answer_token_budget(300, "deepseek-v4-pro") == 300


class TestAttribution:
    def test_openrouter_calls_are_labelled(self, monkeypatch):
        monkeypatch.setenv("ALIEN_MONITOR_PUBLIC_URL", "https://monitor.example.dev")
        headers = ai._openrouter_headers("https://openrouter.ai/api/v1")
        assert headers["X-Title"] == "Alien Monitor"
        assert headers["HTTP-Referer"] == "https://monitor.example.dev"

    def test_other_providers_get_no_extra_headers(self):
        assert ai._openrouter_headers("https://api.deepseek.com/v1") == {}


class TestPinnedProviderVisibility:
    def test_a_pin_that_names_nothing_is_reported(self, monkeypatch):
        """Silence here cost the deployment its LLM.

        Both monitors ran `ALIEN_AI_PROVIDER=openrouter_api` against a config with no such
        entry; the pin was dropped without a word and answers came from `deepseek_api`
        with its placeholder `sk-keep` key.
        """
        monkeypatch.setenv("ALIEN_AI_PROVIDER", "no_such_provider")
        ai._config_cache = None
        try:
            listed = ai.list_providers()
            assert listed["pinned_provider_missing"] == "no_such_provider"
        finally:
            ai._config_cache = None

    def test_a_pin_that_resolves_is_not_reported(self, monkeypatch):
        monkeypatch.setenv("ALIEN_AI_PROVIDER", "openrouter_api")
        ai._config_cache = None
        try:
            assert "pinned_provider_missing" not in ai.list_providers()
        finally:
            ai._config_cache = None
