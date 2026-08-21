"""The assistant must know every component the ecosystem documents.

A user asked the monitor's AI «где логос» and was told the component does not
exist in the ecosystem — while LOGOS was deployed, documented in the central
knowledge base with its live URL, and listed in satellite-map.yaml. Three separate
gaps produced that one answer:

  1. the assistant's knowledge came from a 13 KB prose block hand-maintained
     inside main.py, which named every satellite except the newest;
  2. the snapshot's priority list omitted `logos`, so the node could be truncated
     out of the live payload;
  3. `logos` had no nav aliases, so "где логос" focused nothing on the map —
     the user got a denial AND a map that did not move.

These tests hold all three shut, and the drift checks hold shut the reason the
in-container fallbacks went stale in the first place.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest
import yaml

_HERE = Path(__file__).resolve()
# Monorepo: …/alien-monitor/tests/… → parents[2] is aicom root.
# Satellite: …/alien-monitor/tests/… (GitHub repo root) → parents[1] is the package.
if (_HERE.parents[1] / "backend").is_dir() and not (_HERE.parents[2] / "alien-monitor").is_dir():
    MONITOR = _HERE.parents[1]
    ROOT = MONITOR.parent  # may lack monorepo scripts/ — drift tests skip
else:
    ROOT = _HERE.parents[2]
    MONITOR = ROOT / "alien-monitor"
sys.path.insert(0, str(MONITOR / "backend"))

_MONOREPO_MAP = ROOT / "scripts" / "satellite-map.yaml"
_IN_MONOREPO = _MONOREPO_MAP.is_file()

# Everything a user can reasonably name and expect the assistant to know.
CORE_COMPONENTS = [
    "logos", "momus", "treasury", "atlas", "gaia", "metis", "skopos",
    "dioscuri", "helios", "argus", "hub", "lottery", "platon", "theoros",
    "themis", "hephaestus",
]


def _map_ids(path: Path) -> set[str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {s["id"] for s in (data.get("satellites") or []) if isinstance(s, dict) and s.get("id")}


class TestCentralSourcesDoNotDrift:
    """The monitor ships fallback copies for the container, where the monorepo is
    not mounted. A copy that lags is indistinguishable, at runtime, from a
    component that does not exist."""

    @pytest.mark.skipif(not _IN_MONOREPO, reason="monorepo-only drift check")
    def test_satellite_map_copy_matches_the_central_one(self):
        central = ROOT / "scripts" / "satellite-map.yaml"
        copy = MONITOR / "scripts" / "satellite-map.yaml"
        assert copy.is_file(), "monitor fallback map missing"
        missing = _map_ids(central) - _map_ids(copy)
        assert not missing, (
            f"monitor's satellite-map copy is missing {sorted(missing)}. "
            "Re-copy scripts/satellite-map.yaml — the assistant reads this file "
            "inside the container and cannot know what it does not list."
        )

    @pytest.mark.skipif(not _IN_MONOREPO, reason="monorepo-only drift check")
    def test_knowledge_base_copy_matches_the_central_one(self):
        """The copy is the central file with its relative links absolutised.

        It is NOT byte-identical: the copy lives in another repo, where the source's
        ../onchain-journal.md and ./whitepaper/en.md resolve to nothing — 72 links were
        dead on GitHub for exactly that reason. scripts/sync_knowledge_base.py owns the
        transform; this asserts the copy is its current output.
        """
        central = ROOT / "docs" / "ecosystem" / "knowledge-base.md"
        copy = MONITOR / "docs" / "ecosystem" / "knowledge-base.md"
        assert copy.is_file(), "monitor fallback knowledge base missing"
        sys.path.insert(0, str(ROOT / "scripts"))
        import sync_knowledge_base as sync

        want = sync.mirror_text(
            "docs/ecosystem/knowledge-base.md", central.read_text(encoding="utf-8")
        )
        h = lambda text: hashlib.sha256(text.encode("utf-8")).hexdigest()
        assert h(want) == h(copy.read_text(encoding="utf-8")), (
            "monitor's knowledge-base copy has drifted from "
            "docs/ecosystem/knowledge-base.md — run "
            "`python3 scripts/sync_knowledge_base.py --write`."
        )


class TestAssistantKnowledge:
    def test_knowledge_base_is_loaded_at_all(self):
        from ecosystem_registry import load_knowledge_base

        kb = load_knowledge_base()
        assert kb, "the central knowledge base is not reaching the assistant"

    @pytest.mark.parametrize("component", CORE_COMPONENTS)
    def test_component_is_findable_in_the_assistant_context(self, component):
        """Documented anywhere central ⇒ present in the prompt. This is the test
        that would have caught the «LOGOS does not exist» answer."""
        from ecosystem_registry import build_ecosystem_registry_context, load_knowledge_base

        context = (load_knowledge_base() + "\n" + build_ecosystem_registry_context()).lower()
        assert component in context, (
            f"{component!r} appears in neither the knowledge base nor the satellite "
            "registry the assistant receives — it will deny that it exists."
        )

    def test_registry_cap_covers_every_satellite(self):
        """The cap used to silently drop entries past the 48th, and new satellites
        are appended at the end — exactly where a cap bites."""
        from ecosystem_registry import build_ecosystem_registry_context, load_satellites

        total = len(load_satellites())
        context = build_ecosystem_registry_context()
        listed = context.count("\n- **")
        assert listed >= total, (
            f"registry context lists {listed} of {total} satellites; raise max_items "
            "in build_ecosystem_registry_context()."
        )


class TestSnapshotPriority:
    def test_new_satellites_are_in_the_snapshot_priority_list(self):
        """`nodes` is capped; anything not prioritised can vanish from the payload."""
        from ai_assistant import build_live_context  # noqa: F401  (import guard)

        source = (MONITOR / "backend" / "ai_assistant.py").read_text(encoding="utf-8")
        for component in ("logos", "momus", "treasury", "atlas", "gaia", "themis",
                          "hephaestus"):
            assert f'"{component}"' in source, f"{component} missing from priority_ids"


class TestNavigation:
    @pytest.mark.parametrize(
        "question,expected",
        [
            ("где логос", "logos"),
            ("где логоса?", "logos"),
            ("show logos", "logos"),
            ("покажи аналитический движок", "logos"),
            ("где момус", "momus"),
            ("show treasury", "treasury"),
            ("где темис", "themis"),
            ("где темис?", "themis"),
            ("show THEMIS", "themis"),
            ("покажи допуск", "themis"),
            ("где гефест", "hephaestus"),
            ("покажи кузницу", "hephaestus"),
            ("show the forge", "hephaestus"),
        ],
    )
    def test_the_map_focuses_what_the_user_named(self, question, expected):
        from ai_nav_actions import resolve_nav_actions

        actions = resolve_nav_actions(question)
        ids = [a.get("node_id") for a in actions]
        assert expected in ids, f"{question!r} focused {ids} instead of {expected!r}"

    def test_every_core_component_has_a_focus_label(self):
        from ai_nav_actions import nav_focus_label

        for component in ("logos", "momus", "treasury", "atlas", "gaia", "metis", "themis",
                          "hephaestus"):
            label = nav_focus_label(component, "ru")
            assert label and label != component, f"{component} has no display label"


class TestLogosNodeIsOnTheMap:
    def test_node_spec_and_links_exist(self):
        from logos_layers import logos_node_spec, logos_topology_links

        spec = logos_node_spec()
        assert spec["id"] == "logos"
        assert spec["label"] == "LOGOS"
        assert spec["position"], "logos has no layout position"
        assert {l["target"] for l in logos_topology_links()} >= {"hub", "metis"}

    def test_the_node_is_actually_wired_into_the_graph(self):
        """logos_layers.py existed for a while and nothing imported it — the node
        was defined and unreachable, which is why the map never showed it."""
        main_src = (MONITOR / "backend" / "main.py").read_text(encoding="utf-8")
        assert "logos_node_spec()" in main_src, "logos node never added to the graph"
        assert "logos_topology_links()" in main_src, "logos links never added"
        assert "apply_logos_to_nodes" in main_src, "logos live status never applied"

    def test_health_probe_hits_a_route_that_exists(self):
        """LOGOS serves /health; /api/health is a 404, so the node would have sat
        at "unknown" forever while the service was up."""
        from logos_status import poll_url

        assert poll_url().endswith("/health")
        assert "/api/health" not in poll_url()

    def test_links_do_not_point_at_the_stripped_monorepo_path(self):
        """The public aicom mirror has satellite folders removed, so a
        blob/main/logos/... link is a guaranteed 404."""
        from logos_layers import logos_node_spec
        from logos_status import links

        for url in list(links().values()) + list(logos_node_spec()["links"].values()):
            assert "aicom/blob/main/logos" not in url, url


class TestSnapshotWindowFitsTheMap:
    """The window used to be 64 nodes while a universe run can hold 450.

    The assistant then answered from a seventh of the map — and its own honesty
    rule ("say you cannot see it") only helps if the operator reads the caveat.
    Carrying the whole map costs ~130 characters per node, which is cheap next to
    being wrong about what exists.
    """

    def _state(self, count: int) -> dict:
        return {
            "tick": 1, "ts": "now", "summary": {"tick": 1},
            "nodes": [
                {"id": f"n{i}", "label": f"N{i}", "group": "products",
                 "status": "active", "metrics": {"invokes": i}}
                for i in range(count)
            ],
            "events": [], "transactions": [], "channels": [],
        }

    def test_a_full_universe_fits_without_omission(self):
        """50 core entities + ALIEN_MAX_PRODUCT_ENTITIES (400) products."""
        import json

        from ai_assistant import build_live_context

        payload = json.loads(build_live_context(self._state(450), mode="universe"))
        assert payload["nodes_total"] == 450
        assert payload["nodes_omitted"] == 0
        assert len(payload["nodes"]) == 450

    def test_the_window_is_at_least_a_thousand(self):
        import json

        from ai_assistant import build_live_context

        payload = json.loads(build_live_context(self._state(1000), mode="universe"))
        assert payload["nodes_omitted"] == 0, "the window is smaller than 1000 nodes"

    def test_beyond_the_window_the_omission_is_still_stated(self):
        """A cap that hides itself is how "I cannot see it" becomes "it does not exist"."""
        import json

        from ai_assistant import build_live_context

        payload = json.loads(build_live_context(self._state(1400), mode="universe"))
        assert payload["nodes_total"] == 1400
        assert payload["nodes_omitted"] == 1400 - len(payload["nodes"])
        assert payload["nodes_omitted"] > 0

    def test_the_window_is_env_tunable_for_small_context_models(self, monkeypatch):
        import importlib
        import json

        monkeypatch.setenv("ALIEN_AI_NODE_BUDGET", "80")
        import ai_assistant

        importlib.reload(ai_assistant)
        payload = json.loads(ai_assistant.build_live_context(self._state(300), mode="universe"))
        assert len(payload["nodes"]) == 80
        assert payload["nodes_omitted"] == 220
        monkeypatch.delenv("ALIEN_AI_NODE_BUDGET")
        importlib.reload(ai_assistant)
