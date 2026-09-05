"""The touchstone on the map: registered everywhere, and honest about what it knows.

Two classes of defect are pinned here.

The first is structural, and this repository has been bitten by it repeatedly: a
satellite wired only into ``build_topology`` is invisible in UNI mode, because universe
mode builds its graph from seeded entities and the ``apply_*_graph`` helpers only
decorate a node that already exists. Four places or the node silently vanishes.

The second is about what this particular node may claim. A verdict (PASS / REVIEW /
FAIL) exists only per scan, and a scan is a paid ``POST /invoke``. The monitor never
runs one, so the node must never display a verdict — and it must not read as active
just because the agent answered a health probe. The knowledge base has to fight the
same confusion in prose ("not AgentAuditPool, not HEPHAESTUS"), so the node carries
that disclaimer through instead of re-deriving it.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import basanos_status  # noqa: E402
from basanos_layers import basanos_node_spec, basanos_topology_links  # noqa: E402
from ecosystem_layout import NODE_POSITIONS, ring_position  # noqa: E402


@pytest.fixture(autouse=True)
def _no_cache():
    if hasattr(basanos_status.fetch_basanos_status_sync, "cache_clear"):
        basanos_status.fetch_basanos_status_sync.cache_clear()
    yield


def _dist(a, b):
    return math.sqrt((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2 + (a["z"] - b["z"]) ** 2)


def _status(**over):
    payload = {
        "health": {
            "ok": True,
            "version": "0.1.0",
            "capability_id": "agent.security.contract-assurance@v1",
            "provider_pubkey": "U2Ni81NLViod8GjRSLfm2K6t3vMoYa0NBEJVojjgHy4=",
            "intel_enabled": True,
            "role": "contract-assurance",
            "not": ["AgentAuditPool", "MOMUS", "THEMIS", "HEPHAESTUS"],
        },
        "memos": {"total": 4, "hits": 2, "exploration": 0.5774, "lessons": ["reentrancy first"]},
        "intel": {"enabled": True, "cards": 11, "learned_pairs": 3,
                  "category_scores": {"reentrancy": 0.8}, "recent_cards": []},
    }
    payload.update(over)
    return payload


class TestRegisteredInEveryPlace:
    def test_the_node_is_in_build_topology_with_its_edges(self):
        import main

        nodes, links = main.build_topology()
        assert "basanos" in {n["id"] for n in nodes}

        pairs = {(link["source"], link["target"]) for link in links}
        assert ("acex", "basanos") in pairs, "scans the ACEX contracts"
        assert ("basanos", "acex") in pairs, "the pack is advisory input to the pool decision"

    def test_the_node_is_seeded_in_universe_mode(self):
        """Registered only in build_topology means invisible here — the known trap."""
        from universe import VirtualUniverse

        u = VirtualUniverse()
        u.seed_entities()
        assert "basanos" in u.entities

        entity = u.entities["basanos"]
        assert entity.position == NODE_POSITIONS["basanos"]
        assert entity.url

    def test_the_node_survives_the_topology_reseed_path(self):
        """`_ensure_topology_seeded()` runs when the UNI bootstrap partially failed; a
        satellite added only to `seed_entities()` vanishes on that path."""
        from universe import VirtualUniverse

        u = VirtualUniverse()
        u.seed_entities()
        u.entities.pop("basanos", None)
        u._ensure_topology_seeded()
        assert "basanos" in u.entities

    def test_universe_topology_links_include_it(self):
        from universe import VirtualUniverse

        u = VirtualUniverse()
        u.seed_entities()
        pairs = {(link["source"], link["target"]) for link in u.get_topology_links()}
        assert ("acex", "basanos") in pairs
        assert ("lottery", "basanos") in pairs

    def test_it_keeps_its_distance_from_everything_else(self):
        position = NODE_POSITIONS["basanos"]
        for node_id, other in NODE_POSITIONS.items():
            if node_id == "basanos" or not isinstance(other, dict) or "x" not in other:
                continue
            assert _dist(position, other) >= 4.5, f"too close to {node_id}"
        total = 17
        for i in range(total):
            assert _dist(position, ring_position(i, total)) >= 4.5, f"too close to oracle[{i}]"

    def test_the_spec_starts_offline_with_no_invented_numbers(self):
        spec = basanos_node_spec()
        assert spec["status"] == "offline"
        assert spec["metrics"] == {"intel_cards": 0, "memos": 0, "learned_pairs": 0}
        assert spec["group"] == "security"
        assert spec["links"]["console"].endswith("/ui/")

    def test_the_description_keeps_the_disclaimers_the_map_needs(self):
        """The map has confused this node with the insurance pool and the forge before."""
        description = basanos_node_spec()["description"]
        for other in ("AgentAuditPool", "HEPHAESTUS", "MOMUS", "THEMIS"):
            assert other in description

    def test_every_edge_ends_on_a_node_that_exists(self):
        import main

        nodes, _links = main.build_topology()
        ids = {n["id"] for n in nodes}
        for link in basanos_topology_links():
            assert link["source"] in ids, f"dangling source {link['source']}"
            assert link["target"] in ids, f"dangling target {link['target']}"

    def test_the_outgoing_edge_says_advisory(self):
        """A pack is a technical verdict; coverage stays a human call on AgentAuditPool."""
        labels = {(l["source"], l["target"]): l["label"] for l in basanos_topology_links()}
        assert "advisory" in labels[("basanos", "acex")].lower()


class TestApplyToNodes:
    def test_a_learned_touchstone_is_active(self):
        nodes = [basanos_node_spec()]
        basanos_status.apply_basanos_to_nodes(nodes, _status())
        node = nodes[0]
        assert node["status"] == "active"
        assert node["metrics"] == {"intel_cards": 11, "memos": 4, "learned_pairs": 3}
        assert node["basanos_live"]["capability_id"] == "agent.security.contract-assurance@v1"

    def test_reachable_but_untaught_is_idle_not_active(self):
        """A fresh agent with an empty memo and intel store is exactly that: idle."""
        nodes = [basanos_node_spec()]
        basanos_status.apply_basanos_to_nodes(
            nodes,
            _status(memos={"total": 0, "hits": 0}, intel={"enabled": False, "cards": 0}),
        )
        assert nodes[0]["status"] == "idle"

    def test_a_health_probe_that_is_not_ok_is_an_error_not_active(self):
        nodes = [basanos_node_spec()]
        basanos_status.apply_basanos_to_nodes(nodes, _status(health={"ok": False}))
        assert nodes[0]["status"] == "error"

    def test_going_offline_clears_the_last_good_payload(self):
        """Stale numbers under an offline badge are worse than no numbers."""
        nodes = [basanos_node_spec()]
        basanos_status.apply_basanos_to_nodes(nodes, _status())
        assert "basanos_live" in nodes[0]

        basanos_status.apply_basanos_to_nodes(nodes, None)
        assert nodes[0]["status"] == "offline"
        assert "basanos_live" not in nodes[0]
        assert nodes[0]["metrics"] == {"intel_cards": 0, "memos": 0, "learned_pairs": 0}
        assert nodes[0]["links"]["console"], "an offline node still has a console to open"

    def test_no_verdict_is_ever_published_by_the_node(self):
        """Verdicts belong to a signed pack from a paid scan; the monitor runs none.

        The description may name the three verdicts — that is what the agent emits, and
        explaining it is the node's job. The live payload and the metrics may not, because
        a value there reads as the current state of something that never ran here.
        """
        nodes = [basanos_node_spec()]
        basanos_status.apply_basanos_to_nodes(nodes, _status())
        live = repr(nodes[0]["basanos_live"])
        for verdict in ("PASS", "REVIEW", "FAIL"):
            assert verdict not in live
        assert not any("verdict" in key for key in nodes[0]["metrics"])

    def test_a_missing_node_is_not_an_error(self):
        nodes = [{"id": "hub"}]
        basanos_status.apply_basanos_to_nodes(nodes, _status())
        assert nodes == [{"id": "hub"}]


class TestFactSanitising:
    def test_only_known_health_fields_survive(self):
        facts = basanos_status._health_facts({
            "ok": True,
            "version": "0.1.0",
            "provider_pubkey": "pk",
            "secret": "do-not-carry-this",
            "not": ["AgentAuditPool", 7],
        })
        assert "secret" not in facts
        assert facts["not"] == ["AgentAuditPool"]

    def test_memo_lessons_are_clamped_and_typed(self):
        facts = basanos_status._memo_facts({
            "memos_total": 9,
            "hits": 3,
            "exploration": "not-a-number",
            "lessons": [f"lesson {i}" for i in range(20)] + [42],
        })
        assert facts["total"] == 9
        assert facts["exploration"] is None
        assert len(facts["lessons"]) == basanos_status.LESSON_LIMIT

    def test_intel_cards_are_projected_not_forwarded_whole(self):
        facts = basanos_status._intel_facts({
            "intel_enabled": True,
            "cards_total": 2,
            "learned_pairs": 1,
            "category_scores": {"reentrancy": 0.8, "junk": "high"},
            "recent_cards": [
                {"id": "GHSA-x", "category": "reentrancy", "source": "ghsa",
                 "severity": "high", "ingested_at": 1_800_000_000.0, "raw": {"blob": "x"}},
                "not-a-dict",
            ],
        })
        assert facts["category_scores"] == {"reentrancy": 0.8}
        assert len(facts["recent_cards"]) == 1
        assert "raw" not in facts["recent_cards"][0]

    def test_junk_is_not_a_payload(self):
        assert basanos_status._health_facts(None) == {}
        assert basanos_status._memo_facts("nope") == {}
        assert basanos_status._intel_facts(3) == {}


class TestPolling:
    def test_health_is_the_liveness_signal(self, monkeypatch):
        """Memos and intel alone cannot tell a live touchstone from a stray 200."""

        class _Resp:
            def __init__(self, code, body):
                self.status_code = code
                self._body = body

            def json(self):
                return self._body

        class _Client:
            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, url, **kw):
                if url.endswith("/health"):
                    return _Resp(503, {})
                return _Resp(200, {"memos_total": 3})

        monkeypatch.setattr(basanos_status.httpx, "Client", _Client)
        assert basanos_status.fetch_basanos_status_sync() is None

    def test_the_scan_endpoint_is_never_called(self):
        """A poller that invoked the agent would bill the operator every tick.

        Checked on the code rather than on a mock: the endpoint is a paid one, and a
        future edit that adds the call would otherwise only be caught in production
        billing. Docstrings are stripped first — they have to be free to name /invoke
        in order to explain why nothing calls it.
        """
        import ast

        tree = ast.parse((_BACKEND / "basanos_status.py").read_text(encoding="utf-8"))
        docstrings = {
            id(scope.body[0].value)
            for scope in ast.walk(tree)
            if isinstance(scope, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and scope.body
            and isinstance(scope.body[0], ast.Expr)
            and isinstance(scope.body[0].value, ast.Constant)
        }
        for node in ast.walk(tree):
            if id(node) in docstrings:
                continue
            if isinstance(node, ast.Call):
                target = ast.unparse(node.func)
                assert not target.endswith((".post", ".put", ".patch", ".delete")), (
                    f"{target} writes to the agent; the monitor only observes"
                )
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert "/invoke" not in node.value, "an /invoke URL is a paid scan"
