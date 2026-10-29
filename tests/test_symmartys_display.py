"""The local rename is visible without changing remote wire identity or evidence."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from ai_assistant import build_live_context
from ai_nav_actions import match_live_node_id
from live_graph import describe_node
from product_display import current_product_label, is_symmartys_node
import ecosystem_registry


def legacy_state():
    return {"nodes": [{"id": "provider:hub:emporion", "label": "EMPORION — public-record facts",
                       "description": "EMPORION checks public registries.", "group": "peer_hub_provider",
                       "url": "https://emporion.modelmarket.dev/", "status": "active", "metrics": {"capabilities": 16},
                       "manifest": {"product_id": "emporion", "signature": {"value": "original-bytes"}}}],
            "links": [], "summary": {"mode": "real"}}


def test_current_and_former_names_focus_the_actual_observed_node_without_changing_its_id():
    state = legacy_state()
    original = copy.deepcopy(state)
    for question in ("show symmartys", "покажи симмартис", "show emporion", "покажи эмпорион"):
        assert match_live_node_id(question, state) == "provider:hub:emporion"
    answer = describe_node(state, "provider:hub:emporion", "en")
    assert "**SYMMARTYS — public-record facts**" in answer
    assert "EMPORION checks" not in answer
    assert "https://emporion.modelmarket.dev/" in answer
    assert state == original


def test_prompt_uses_current_display_name_but_keeps_the_observed_id_url_and_metrics():
    state = legacy_state()
    original = copy.deepcopy(state)
    prompt = json.loads(build_live_context(state, "real", "provider:hub:emporion"))
    node = prompt["nodes"][0]
    assert node["label"] == "SYMMARTYS — public-record facts"
    assert node["description"] == "SYMMARTYS checks public registries."
    assert node["id"] == state["nodes"][0]["id"]
    assert node["url"] == state["nodes"][0]["url"]
    assert node["metrics"] == state["nodes"][0]["metrics"]
    assert state == original


def test_registry_aliases_answer_with_current_name(monkeypatch):
    monkeypatch.setattr(ecosystem_registry, "build_live_federation_context", lambda: "- SYMMARTYS (16 capabilities)")
    for question in ("where is symmartys", "where is emporion", "где эмпорион"):
        assert "SYMMARTYS" in ecosystem_registry.live_component_answer(question)


def test_unpublished_local_source_does_not_become_an_invented_github_repository(monkeypatch):
    monkeypatch.setattr(ecosystem_registry, "load_satellites", lambda: [{"id": "symmartys", "repo": "symmartys",
        "github_published": False, "description": "SYMMARTYS — public-record facts"}])
    prompt = ecosystem_registry.build_ecosystem_registry_context()
    assert "local monorepo source: symmartys/" in prompt
    assert "github.com/alexar76/symmartys" not in prompt


def test_text_projection_does_not_modify_addresses_or_a_strangers_same_named_provider():
    assert current_product_label("EMPORION · emporion.vat.check@v1 · https://emporion.modelmarket.dev") == (
        "SYMMARTYS · emporion.vat.check@v1 · https://emporion.modelmarket.dev")
    assert not is_symmartys_node({"id": "foreign-provider", "label": "EMPORION", "url": "https://other.example"})
