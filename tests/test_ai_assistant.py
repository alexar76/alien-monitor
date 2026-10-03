"""Tests for live-state AI context and provider registry."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from ai_assistant import (  # noqa: E402
    build_live_context,
    build_system_prompt,
    detect_question_locale,
    list_providers,
    normalize_locale,
    resolve_response_locale,
)


def test_normalize_locale():
    assert normalize_locale("ru-RU") == "ru"
    assert normalize_locale("xx") == "en"


def test_detect_question_locale():
    assert detect_question_locale("How do payment channels work?") == "en"
    assert detect_question_locale("Как работают платёжные каналы?") == "ru"
    assert detect_question_locale("¿Cómo funcionan los canales de pago?") == "es"


def test_resolve_response_locale_prefers_question():
    assert resolve_response_locale("How do payment channels work?", "ru") == "en"
    assert resolve_response_locale("Как работает хаб?", "en") == "ru"
    assert resolve_response_locale("???", "ru") == "ru"


def test_build_live_context_includes_tick_and_nodes():
    state = {
        "tick": 42,
        "ts": "2026-05-24T12:00:00Z",
        "summary": {"mode": "test", "tick": 42, "agents_online": 3},
        "nodes": [
            {"id": "hub", "label": "Hub", "group": "core", "status": "active", "metrics": {"peers": 2}},
        ],
        "events": [{"id": "e1", "action": "invoke"}],
        "transactions": [],
    }
    ctx = json.loads(build_live_context(state, "test", "hub"))
    assert ctx["tick"] == 42
    assert ctx["nodes"][0]["id"] == "hub"
    assert ctx["nodes"][0]["selected"] is True
    assert len(ctx["recent_events"]) == 1


def test_build_live_context_empty():
    ctx = json.loads(build_live_context(None, "real"))
    assert ctx["monitor_mode"] == "real"
    assert "note" in ctx


def test_list_providers_has_default():
    data = list_providers()
    assert data["default_provider"]
    assert isinstance(data["providers"], list)


def test_system_prompt_embeds_live_json():
    prompt = build_system_prompt("STATIC", "ru", '{"tick":1}')
    assert "LIVE MONITOR SNAPSHOT" in prompt
    assert '{"tick":1}' in prompt
    assert "русском" in prompt
    assert "RESPONSE LANGUAGE" in prompt


def test_the_snapshot_reports_what_it_omitted(monkeypatch):
    """A truncated node list that does not say it is truncated turns "I cannot see it" into "it does
    not exist" — which is exactly the answer the assistant gave about MOMUS while MOMUS was deployed,
    documented and in the graph.

    The budget is pinned here rather than left at the default: when the default rose to 1000 the
    90-node fixture stopped exceeding it, and this test silently stopped covering truncation.
    """
    import json

    from ai_assistant import build_live_context

    monkeypatch.setenv("ALIEN_AI_NODE_BUDGET", "64")
    state = {"nodes": [{"id": f"n{i}", "label": f"N{i}", "group": "g"} for i in range(90)]}
    payload = json.loads(build_live_context(state, mode="real"))
    assert payload["nodes_total"] == 90
    assert payload["nodes_omitted"] == 90 - len(payload["nodes"])
    assert payload["nodes_omitted"] > 0, "the fixture must exceed the budget for this to mean anything"


def test_momus_and_treasury_are_never_the_nodes_that_get_dropped():
    """They are the newest satellites, so they sat at the end of the list and fell off the cap."""
    import json

    from ai_assistant import build_live_context

    filler = [{"id": f"n{i}", "label": f"N{i}", "group": "g"} for i in range(120)]
    state = {"nodes": filler + [{"id": "momus", "label": "MOMUS", "group": "security"},
                                {"id": "treasury", "label": "Treasury", "group": "security"}]}
    ids = [n["id"] for n in json.loads(build_live_context(state, mode="real"))["nodes"]]
    assert "momus" in ids and "treasury" in ids


def test_the_prompt_forbids_denying_a_components_existence():
    from ai_assistant import build_system_prompt

    prompt = build_system_prompt("REGISTRY", "en", '{"nodes": [], "nodes_omitted": 7}')
    assert "NEVER answer that a component does not exist" in prompt
    assert "nodes_omitted" in prompt
