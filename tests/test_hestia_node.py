"""The hearth on the map: registered everywhere, and honest about what it hosts.

Two classes of defect are pinned here.

The first is structural: a satellite wired only into ``build_topology`` is
invisible in UNI mode, because universe mode builds its graph from seeded
entities and the ``apply_*_graph`` helpers only decorate a node that already
exists.

The second is about what this particular node may claim. Agents appear only
after an explicit signed deploy onto the hearth. An empty roster is idle, not
an empty market, and the monitor never calls the paid ``POST /invoke``.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import hestia_status  # noqa: E402
from ecosystem_layout import NODE_POSITIONS, ring_position  # noqa: E402
from hestia_layers import hestia_node_spec, hestia_topology_links  # noqa: E402


@pytest.fixture(autouse=True)
def _no_cache():
    if hasattr(hestia_status.fetch_hestia_status_sync, "cache_clear"):
        hestia_status.fetch_hestia_status_sync.cache_clear()
    yield


def _dist(a, b):
    return math.sqrt((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2 + (a["z"] - b["z"]) ** 2)


def _status(**over):
    payload = {
        "health": {
            "ok": True,
            "service": "hestia",
            "version": "0.1.0",
            "runtime": "stub",
            "tenants": 1,
        },
        "hearth": {
            "hearth": "https://hestia.modelmarket.dev",
            "tenants": [
                {
                    "slug": "weather-bot",
                    "status": "running",
                    "capability_id": "weather.read@v1",
                    "name": "Weather",
                    "public_url": "https://hestia.modelmarket.dev/t/weather-bot",
                    "announced": True,
                }
            ],
            "roster_size": 1,
            "announced": 1,
        },
    }
    payload.update(over)
    return payload


class TestRegisteredInEveryPlace:
    def test_the_node_is_in_build_topology_with_its_edges(self):
        import main

        nodes, links = main.build_topology()
        assert "hestia" in {n["id"] for n in nodes}

        pairs = {(link["source"], link["target"]) for link in links}
        assert ("factory", "hestia") in pairs, "factory scaffolds; hearth hosts"
        assert ("themis", "hestia") in pairs, "optional admit before a start"
        assert ("hestia", "hub") in pairs, "announce is a knock, not a listing"

    def test_the_node_is_seeded_in_universe_mode(self):
        """Registered only in build_topology means invisible here — the known trap."""
        from universe import VirtualUniverse

        u = VirtualUniverse()
        u.seed_entities()
        assert "hestia" in u.entities

        entity = u.entities["hestia"]
        assert entity.position == NODE_POSITIONS["hestia"]
        assert entity.url
        assert entity.color == "#ff9a3c"

    def test_the_node_survives_the_topology_reseed_path(self):
        from universe import VirtualUniverse

        u = VirtualUniverse()
        u.seed_entities()
        u.entities.pop("hestia", None)
        u._ensure_topology_seeded()
        assert "hestia" in u.entities

    def test_universe_topology_links_include_it(self):
        from universe import VirtualUniverse

        u = VirtualUniverse()
        u.seed_entities()
        pairs = {(link["source"], link["target"]) for link in u.get_topology_links()}
        assert ("factory", "hestia") in pairs
        assert ("hestia", "hub") in pairs

    def test_it_keeps_its_distance_from_everything_else(self):
        position = NODE_POSITIONS["hestia"]
        for node_id, other in NODE_POSITIONS.items():
            if node_id == "hestia" or not isinstance(other, dict) or "x" not in other:
                continue
            assert _dist(position, other) >= 4.5, f"too close to {node_id}"
        total = 17
        for i in range(total):
            assert _dist(position, ring_position(i, total)) >= 4.5, f"too close to oracle[{i}]"

    def test_the_spec_starts_offline_with_no_invented_numbers(self):
        spec = hestia_node_spec()
        assert spec["status"] == "offline"
        assert spec["metrics"] == {"tenants": 0, "announced": 0}
        assert spec["group"] == "infra"
        assert spec["color"] == "#ff9a3c"
        assert spec["links"]["console"].endswith("/ui/")

    def test_the_description_keeps_the_disclaimers_the_map_needs(self):
        description = hestia_node_spec()["description"]
        for other in ("Hub", "Factory", "job board", "THEMIS"):
            assert other in description

    def test_every_edge_ends_on_a_node_that_exists(self):
        import main

        nodes, _links = main.build_topology()
        ids = {n["id"] for n in nodes}
        for link in hestia_topology_links():
            assert link["source"] in ids, f"dangling source {link['source']}"
            assert link["target"] in ids, f"dangling target {link['target']}"

    def test_the_outgoing_edge_says_announce_not_listing(self):
        labels = {(l["source"], l["target"]): l["label"] for l in hestia_topology_links()}
        assert "announce" in labels[("hestia", "hub")].lower()


class TestApplyToNodes:
    def test_a_hosted_tenant_is_active(self):
        nodes = [hestia_node_spec()]
        hestia_status.apply_hestia_to_nodes(nodes, _status())
        node = nodes[0]
        assert node["status"] == "active"
        assert node["metrics"] == {"tenants": 1, "announced": 1}
        assert node["hestia_live"]["runtime"] == "stub"
        assert node["hestia_live"]["tenants"][0]["slug"] == "weather-bot"

    def test_reachable_but_empty_roster_is_idle_not_active(self):
        """An empty hearth is idle. That is not an empty market."""
        nodes = [hestia_node_spec()]
        hestia_status.apply_hestia_to_nodes(
            nodes,
            _status(
                health={"ok": True, "service": "hestia", "version": "0.1.0",
                        "runtime": "stub", "tenants": 0},
                hearth={"hearth": "https://hestia.modelmarket.dev",
                        "tenants": [], "roster_size": 0, "announced": 0},
            ),
        )
        assert nodes[0]["status"] == "idle"
        assert nodes[0]["metrics"] == {"tenants": 0, "announced": 0}

    def test_a_health_probe_that_is_not_ok_is_an_error_not_active(self):
        nodes = [hestia_node_spec()]
        hestia_status.apply_hestia_to_nodes(nodes, _status(health={"ok": False}))
        assert nodes[0]["status"] == "error"

    def test_going_offline_clears_the_last_good_payload(self):
        nodes = [hestia_node_spec()]
        hestia_status.apply_hestia_to_nodes(nodes, _status())
        assert "hestia_live" in nodes[0]

        hestia_status.apply_hestia_to_nodes(nodes, None)
        assert nodes[0]["status"] == "offline"
        assert "hestia_live" not in nodes[0]
        assert nodes[0]["metrics"] == {"tenants": 0, "announced": 0}
        assert nodes[0]["links"]["console"], "an offline node still has a console to open"

    def test_a_missing_node_is_not_an_error(self):
        nodes = [{"id": "hub"}]
        hestia_status.apply_hestia_to_nodes(nodes, _status())
        assert nodes == [{"id": "hub"}]


class TestFactSanitising:
    def test_only_known_health_fields_survive(self):
        facts = hestia_status._health_facts({
            "ok": True,
            "version": "0.1.0",
            "runtime": "stub",
            "tenants": 2,
            "secret": "do-not-carry-this",
        })
        assert "secret" not in facts
        assert facts["tenants"] == 2

    def test_roster_rows_are_projected_not_forwarded_whole(self):
        facts = hestia_status._hearth_facts({
            "hearth": "https://hestia.modelmarket.dev",
            "tenants": [
                {"slug": "a", "status": "running", "capability_id": "x@v1",
                 "name": "A", "public_url": "https://h/t/a", "announced": True,
                 "owner_pubkey": "drop-me", "listen_url": "http://127.0.0.1:9"},
                "not-a-dict",
            ],
        })
        assert facts["roster_size"] == 2
        assert facts["announced"] == 1
        assert "owner_pubkey" not in facts["tenants"][0]
        assert "listen_url" not in facts["tenants"][0]

    def test_junk_is_not_a_payload(self):
        assert hestia_status._health_facts(None) == {}
        assert hestia_status._hearth_facts("nope") == {}


class TestPolling:
    def test_health_is_the_liveness_signal(self, monkeypatch):
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
                return _Resp(200, {"ok": True, "tenants": []})

        monkeypatch.setattr(hestia_status.httpx, "Client", _Client)
        assert hestia_status.fetch_hestia_status_sync() is None

    def test_the_invoke_endpoint_is_never_called(self):
        """A poller that invoked the agent would bill the operator every tick."""
        import ast

        tree = ast.parse((_BACKEND / "hestia_status.py").read_text(encoding="utf-8"))
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
                assert "/invoke" not in node.value, "an /invoke URL is a paid call"
