"""The offline assistant answering from the map instead of from a hardcoded product list.

Every case here is a question that was asked of a REAL deployment and answered wrongly:
`monitor.attestedmemory.net` replied "ask about the hub, SKOPOS, Metis, THEMIS, DIOSCURI,
MOMUS, contracts, plugins, mesh or ACEX" to «где аттестед мемори?» and «Где мемори маркет?»
— naming another operator's satellites while its own hub and its own Memory Market were on
screen. Two independent causes: a transliterated name matched nothing, and the give-up line
was a build-time list.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from ai_nav_actions import _fold, match_live_node_id, resolve_nav_actions
from live_graph import describe_node, graph_overview, neighbours


ATTESTED_STATE = {
    "tick": 26071,
    "summary": {"mode": "real", "tick": 26071},
    "nodes": [
        {
            "id": "hub", "label": "Attested Memory Hub", "group": "core", "role": "hub",
            "url": "https://hub.attestedmemory.net", "status": "active",
            "description": "Federated capability catalog + payment routing",
            "metrics": {"peers": 9, "capabilities": 20, "invocations_24h": 6},
            "hub": {"id": "hub", "label": "AIMarket Hub"},
        },
        {
            "id": "provider:hub:memory-market", "label": "Memory Market",
            "group": "peer_hub_provider", "role": "provider", "parent_id": "hub",
            "url": "http://memory-market:8810", "status": "idle",
            "metrics": {"capabilities": 5},
        },
        {
            "id": "provider:hub:provenance-ledger", "label": "Provenance Ledger",
            "group": "peer_hub_provider", "role": "provider", "parent_id": "hub",
            "url": "http://provenance-ledger:8812", "status": "idle",
            "metrics": {"capabilities": 3},
        },
        {
            "id": "signal-hunt-hub", "label": "Signal Hunt Hub", "group": "peer_hub",
            "role": "hub", "hop": 1, "url": "https://hunt.modelmarket.dev", "status": "idle",
        },
        {
            "id": "fedchild:https://themis.modelmarket.dev", "label": "THEMIS",
            "group": "peer_hub_node", "role": "peer", "hop": 2,
            "parent_id": "signal-hunt-hub", "url": "https://themis.modelmarket.dev",
            "status": "idle", "metrics": {"trust_score": 0.2655},
        },
    ],
    "links": [
        {"source": "hub", "target": "provider:hub:memory-market", "label": "owned provider"},
        {"source": "hub", "target": "provider:hub:provenance-ledger", "label": "owned provider"},
        {"source": "signal-hunt-hub", "target": "fedchild:https://themis.modelmarket.dev",
         "label": "its peer"},
    ],
}


class TestFold:
    def test_cyrillic_spelling_folds_onto_the_latin_name(self):
        """«мемори» and *Memory* differ in their last letter under any transliteration."""
        assert _fold("где мемори маркет?").endswith(_fold("Memory Market"))
        assert _fold("Attested Memory Hub") == "atested memori hub"
        assert _fold("темис") == _fold("THEMIS")
        assert _fold("варден") == _fold("Warden")

    def test_fold_keeps_distinct_names_distinct(self):
        assert _fold("Memory Market") != _fold("Signal Hunt Hub")
        assert _fold("Provenance Ledger") != _fold("Truth Layer")


class TestMatching:
    def test_finds_its_own_hub_asked_in_russian(self):
        assert match_live_node_id("где аттестед мемори?", ATTESTED_STATE) == "hub"

    def test_finds_a_provider_asked_in_russian(self):
        assert (
            match_live_node_id("Где мемори маркет?", ATTESTED_STATE)
            == "provider:hub:memory-market"
        )

    def test_a_matched_name_also_moves_the_camera(self):
        actions = resolve_nav_actions("Где мемори маркет?", ATTESTED_STATE)
        assert [a["node_id"] for a in actions] == ["provider:hub:memory-market"]

    def test_one_weak_token_is_not_a_match(self):
        """"lab" alone must not resolve a three-word hub name — hence the two-token quorum."""
        assert match_live_node_id("что такое lab", ATTESTED_STATE) is None


class TestDescribe:
    def test_describes_where_a_node_sits(self):
        text = describe_node(ATTESTED_STATE, "provider:hub:memory-market", "ru")
        assert "Memory Market" in text
        assert "Attested Memory Hub" in text          # whose system it lives in
        assert "capabilities=5" in text               # its own metrics
        assert "memory-market:8810" in text

    def test_a_hub_does_not_live_in_its_own_former_name(self):
        """The `hub` back-reference points at itself and carries the build-time label."""
        text = describe_node(ATTESTED_STATE, "hub", "en")
        assert "AIMarket Hub" not in text
        assert "Attested Memory Hub" in text

    def test_neighbours_come_from_the_links(self):
        wired = dict(neighbours(ATTESTED_STATE, "hub"))
        assert wired["Memory Market"] == "owned provider"
        assert wired["Provenance Ledger"] == "owned provider"

    def test_absent_node_describes_nothing(self):
        assert describe_node(ATTESTED_STATE, "no-such-node", "en") == ""


class TestOverview:
    def test_overview_names_this_deployments_own_things_first(self):
        text = graph_overview(ATTESTED_STATE, "ru")
        assert "Attested Memory Hub" in text
        assert "Memory Market" in text
        # …and never a component that is not on this map.
        for foreign in ("SKOPOS", "DIOSCURI", "ACEX"):
            assert foreign not in text

    def test_russian_node_count_agrees_with_its_number(self):
        assert "5 узлов" in graph_overview(ATTESTED_STATE, "ru")

    def test_empty_state_has_nothing_to_say(self):
        assert graph_overview({"nodes": []}, "en") == ""
        assert graph_overview(None, "en") == ""


class TestNavigation:
    def test_focus_hint_uses_the_nodes_real_name(self):
        """`node_id.upper()` announced «Открываю PROVIDER:HUB:MEMORY-MARKET» on live prod."""
        from ai_nav_actions import append_nav_hint, nav_focus_label

        assert nav_focus_label(
            "provider:hub:memory-market", "ru", ATTESTED_STATE
        ) == "Memory Market"
        hint = append_nav_hint(
            "…", [{"type": "focus_node", "node_id": "provider:hub:memory-market"}],
            "ru", ATTESTED_STATE,
        )
        assert "Memory Market" in hint
        assert "PROVIDER:HUB" not in hint

    def test_curated_alias_loses_to_the_node_that_exists(self):
        """«где темис» resolved to the curated `themis`, absent from this map.

        The answer described the right node (the live matcher found the fedchild) while
        the camera flew to an id nothing on screen had.
        """
        from ai_nav_actions import resolve_nav_actions

        actions = resolve_nav_actions("где темис", ATTESTED_STATE)
        assert [a["node_id"] for a in actions] == ["fedchild:https://themis.modelmarket.dev"]

    def test_curated_alias_still_wins_where_it_exists(self):
        from ai_nav_actions import resolve_nav_actions

        state = {"nodes": [{"id": "themis", "label": "THEMIS", "group": "security"}]}
        actions = resolve_nav_actions("где темис", state)
        assert [a["node_id"] for a in actions] == ["themis"]
