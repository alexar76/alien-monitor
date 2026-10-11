"""Tests for AI map navigation action detection."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from ai_nav_actions import resolve_nav_actions  # noqa: E402
import pytest


def test_show_skopos_ru():
    q = "теме появился skopos?покажи мне его"
    actions = resolve_nav_actions(q)
    assert actions[0]["type"] == "focus_node"
    assert actions[0]["node_id"] == "skopos"


def test_show_skopos_en():
    actions = resolve_nav_actions("Show me SKOPOS on the map")
    assert actions[0]["node_id"] == "skopos"


def test_what_is_skopos_no_nav():
    assert resolve_nav_actions("What is SKOPOS?") == []


def test_where_is_metis():
    actions = resolve_nav_actions("Где METIS на карте?")
    assert actions[0]["node_id"] == "metis"


def test_show_gaia_ru_accusative():
    """«покажи гею» must focus — accusative «гею» used to miss alias «гея»."""
    actions = resolve_nav_actions("покажи гею")
    assert actions and actions[0]["node_id"] == "gaia"


def test_open_gaia_ru_accusative():
    assert resolve_nav_actions("открой гайю")[0]["node_id"] == "gaia"


def test_show_gaia_fr():
    assert resolve_nav_actions("montre gaia")[0]["node_id"] == "gaia"
    assert resolve_nav_actions("où est gaïa")[0]["node_id"] == "gaia"


def test_show_skopos_zh():
    assert resolve_nav_actions("显示 SKOPOS")[0]["node_id"] == "skopos"
    assert resolve_nav_actions("盖亚在哪里")[0]["node_id"] == "gaia"
    assert resolve_nav_actions("打开赫利俄斯")[0]["node_id"] == "helios"


def test_what_is_gaia_fr_zh_no_nav():
    assert resolve_nav_actions("Qu'est-ce que Gaia ?") == []
    assert resolve_nav_actions("什么是盖亚") == []


def test_core_satellite_without_state_entry():
    state = {"nodes": [{"id": "hub", "label": "Hub"}]}
    assert resolve_nav_actions("show skopos", state)[0]["node_id"] == "skopos"


def test_focus_when_node_present_in_state():
    state = {"nodes": [{"id": "hub", "label": "Hub"}]}
    assert resolve_nav_actions("show hub", state)[0]["node_id"] == "hub"


# ── MOMUS and Treasury: absent from the alias table, so the map never focused ────────────────────
# The user asked "где момус?" and got "there is no such node" while MOMUS was deployed, documented
# and present in the graph. Two independent gaps produced that one answer: no alias here (so no
# focus action) and a truncated node list in the prompt (so the model could not see it either).
@pytest.mark.parametrize("question,expected", [
    # en
    ("show momus", "momus"),
    ("where is momus?", "momus"),
    ("focus the red team", "momus"),
    ("show the treasury", "treasury"),
    ("where is the bounty treasury?", "treasury"),
    # ru — including the declensions the matcher derives
    ("где момус?", "momus"),
    ("покажи момуса", "momus"),
    ("покажи красную команду", "momus"),
    ("где казна?", "treasury"),
    ("покажи трезури", "treasury"),
    ("покажи вознаграждения", "treasury"),
    # es
    ("muéstrame momus", "momus"),
    ("¿dónde está el equipo rojo?", "momus"),
    ("muestra la tesorería", "treasury"),
    # fr
    ("montre momus", "momus"),
    ("où est l'équipe rouge ?", "momus"),
    ("montre la trésorerie", "treasury"),
    # zh
    ("显示 momus", "momus"),
    ("红队在哪里", "momus"),
    ("显示金库", "treasury"),
])
def test_momus_and_treasury_focus_in_every_locale(question, expected):
    actions = resolve_nav_actions(question)
    assert actions, f"no focus action for {question!r}"
    assert actions[0]["type"] == "focus_node"
    assert actions[0]["node_id"] == expected, f"{question!r} → {actions[0]['node_id']}"


def test_a_question_about_momus_without_a_nav_intent_does_not_hijack_the_camera():
    """Asking WHAT something is must not fly the camera — only asking WHERE or to SHOW it does."""
    assert resolve_nav_actions("what is momus and who pays it?") == []
    assert resolve_nav_actions("кто платит момусу?") == []


def test_live_state_node_is_focusable_without_alias():
    """New graph nodes (competing galaxy, discovered peers) focus via live labels/ids."""
    state = {
        "nodes": [
            {
                "id": "competing_hub",
                "label": "Competing Lab Hub",
                "galaxy": "competing",
            },
            {"id": "signal_hunt_hub", "label": "Signal Hunt Hub", "galaxy": "competing"},
            {"id": "signal_hunt", "label": "Signal Hunt", "galaxy": "competing"},
            {"id": "use_cases", "label": "Use Cases Portal", "galaxy": "competing"},
        ]
    }
    assert resolve_nav_actions("покажи Competing Lab Hub", state)[0]["node_id"] == "competing_hub"
    assert resolve_nav_actions("show signal hunt hub", state)[0]["node_id"] == "signal_hunt_hub"
    assert resolve_nav_actions("show signal hunt", state)[0]["node_id"] == "signal_hunt"
    assert resolve_nav_actions("где use cases portal?", state)[0]["node_id"] == "use_cases"
    assert resolve_nav_actions("fly to competing_hub", state)[0]["node_id"] == "competing_hub"


def test_live_state_match_requires_nav_intent():
    state = {"nodes": [{"id": "competing_hub", "label": "Competing Lab Hub"}]}
    assert resolve_nav_actions("what is Competing Lab Hub?", state) == []


def test_new_latin_provider_matches_cyrillic_transliteration():
    state = {
        "nodes": [
            {"id": "provider:hub:kova-gateway", "label": "KOVA"},
            {"id": "provider:hub:aegis-independent", "label": "AEGIS"},
        ]
    }
    assert resolve_nav_actions("где кова?", state)[0]["node_id"] == "provider:hub:kova-gateway"
    assert resolve_nav_actions("покажи аегис", state)[0]["node_id"] == "provider:hub:aegis-independent"
