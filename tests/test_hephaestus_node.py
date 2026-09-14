"""The forge on the map: registered everywhere, and honest about what it shows.

Two classes of defect are pinned here.

The first is structural, and this repository has been bitten by it: a satellite wired only
into ``build_topology`` is invisible in UNI mode, because universe mode builds its graph
from seeded entities and the ``apply_*_graph`` helpers only decorate a node that already
exists. Four places or the node silently vanishes.

The second is about honesty. This panel exists to show what actually ran and how much of
the catalogue can actually be built with — so a reachable-but-idle node must not read as
active, an unreachable one must not keep serving yesterday's numbers, and "composable" must
mean a row that can genuinely be wired rather than one that merely has the keys present.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import hephaestus_status  # noqa: E402
from ecosystem_layout import NODE_POSITIONS, ring_position  # noqa: E402
from hephaestus_layers import hephaestus_node_spec, hephaestus_topology_links  # noqa: E402


@pytest.fixture(autouse=True)
def _no_cache():
    if hasattr(hephaestus_status.fetch_hephaestus_status_sync, "cache_clear"):
        hephaestus_status.fetch_hephaestus_status_sync.cache_clear()
    yield


def _dist(a, b):
    return math.sqrt((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2 + (a["z"] - b["z"]) ** 2)


def _trace(**over):
    row = {
        "trace_id": "tr_abc123abc123",
        "completed_at": 1_800_000_000.0,
        "duration_ms": 412,
        "total_usd": 0.006,
        "hops": 2,
        "failed": False,
        "signed": True,
        "trace_path": "/ai-market/pipelines/tr_abc123abc123",
        "steps": [
            {"id": "s", "product_id": "prod-mcp", "capability_id": "web.search@v1",
             "status_code": 200, "success": True, "price_usd": 0.002},
            {"id": "v", "product_id": "prod-metis", "capability_id": "metis.verify@v1",
             "status_code": 200, "success": True, "price_usd": 0.004},
        ],
        "blame": None,
    }
    row.update(over)
    return row


def _manifest(tools, **over):
    body = {
        "generated_at": "2026-08-21T00:00:00Z",
        "tools": tools,
        "by_hub": {"local": {}, "https://atlas.modelmarket.dev": {}},
        "signature": {"algorithm": "ed25519", "value": "sig"},
    }
    body.update(over)
    return body


class TestRegisteredInEveryPlace:
    def test_the_node_is_in_build_topology_with_its_edges(self):
        import main

        nodes, links = main.build_topology()
        ids = {n["id"] for n in nodes}
        assert "hephaestus" in ids

        pairs = {(link["source"], link["target"]) for link in links}
        assert ("hephaestus", "hub") in pairs, "reads the catalogue"
        assert ("hephaestus", "factory") in pairs, "submits pipelines"
        assert ("factory", "hephaestus") in pairs, "gets the signed BoM back"

    def test_the_node_is_seeded_in_universe_mode(self):
        """Registered only in build_topology means invisible here — the known trap."""
        from universe import VirtualUniverse

        u = VirtualUniverse()
        u.seed_entities()
        assert "hephaestus" in u.entities

        entity = u.entities["hephaestus"]
        assert entity.position == NODE_POSITIONS["hephaestus"]
        assert entity.url

    def test_the_node_survives_the_topology_reseed_path(self):
        """`_ensure_topology_seeded()` runs when the UNI bootstrap partially failed; a
        satellite added only to `seed_entities()` vanishes on that path."""
        from universe import VirtualUniverse

        u = VirtualUniverse()
        u.seed_entities()
        u.entities.pop("hephaestus", None)
        u._ensure_topology_seeded()
        assert "hephaestus" in u.entities

    def test_universe_topology_links_include_it(self):
        from universe import VirtualUniverse

        u = VirtualUniverse()
        u.seed_entities()
        pairs = {(link["source"], link["target"]) for link in u.get_topology_links()}
        assert ("hephaestus", "hub") in pairs
        assert ("factory", "hephaestus") in pairs

    def test_it_keeps_its_distance_from_everything_else(self):
        position = NODE_POSITIONS["hephaestus"]
        for node_id, other in NODE_POSITIONS.items():
            if node_id == "hephaestus" or not isinstance(other, dict) or "x" not in other:
                continue
            assert _dist(position, other) >= 4.5, f"too close to {node_id}"
        total = 17
        for i in range(total):
            assert _dist(position, ring_position(i, total)) >= 4.5, f"too close to oracle[{i}]"

    def test_the_spec_starts_offline_with_no_invented_numbers(self):
        spec = hephaestus_node_spec()
        assert spec["status"] == "offline"
        assert spec["metrics"] == {"runs": 0, "spend_usd": 0, "capabilities": 0}
        assert "hephaestus" in spec["links"]["docs"]

    def test_the_links_are_directed_as_the_data_flows(self):
        labels = {(l["source"], l["target"]): l["label"] for l in hephaestus_topology_links()}
        assert labels[("hephaestus", "hub")].startswith("Catalogue")
        assert labels[("factory", "hephaestus")] == "Signed BoM"


class TestCatalogueReadiness:
    def test_composable_needs_declared_input_fields_and_an_output_schema(self):
        tools = [
            {  # wireable both ways
                "capability_id": "good@v1", "price_per_call_usd": 0.01,
                "input_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
                "output_schema": {"type": "object", "properties": {"r": {"type": "string"}}},
            },
            {  # takes nothing, but SAYS so — still composable
                "capability_id": "inputless@v1", "price_per_call_usd": 0.001,
                "input_schema": {"type": "object", "properties": {}},
                "output_schema": {"type": "object"},
            },
            {  # never declared what it returns — nothing downstream can use it
                "capability_id": "no-output@v1", "price_per_call_usd": 0.02,
                "input_schema": {"type": "object", "properties": {}},
                "output_schema": {},
            },
            {  # never declared its fields — cannot be filled in
                "capability_id": "no-input@v1", "price_per_call_usd": 0.02,
                "input_schema": {}, "output_schema": {"type": "object"},
            },
        ]
        readiness = hephaestus_status._catalogue_readiness(_manifest(tools))
        assert readiness["capabilities"] == 4
        assert readiness["priced"] == 4
        assert readiness["composable"] == 2
        assert readiness["hubs"] == 2
        assert readiness["signed"] is True

    def test_measured_comes_from_the_hubs_marker_not_from_the_number(self):
        """A 0.5 with no observations behind it is a placeholder; only the hub knows."""
        tools = [
            {"capability_id": "a@v1", "success_rate_30d": 0.5, "reputation_basis": "unobserved",
             "input_schema": {"properties": {}}, "output_schema": {"type": "object"}},
            {"capability_id": "b@v1", "success_rate_30d": 0.5, "reputation_basis": "measured",
             "input_schema": {"properties": {}}, "output_schema": {"type": "object"}},
            {"capability_id": "c@v1", "success_rate_30d": 0.99,
             "input_schema": {"properties": {}}, "output_schema": {"type": "object"}},
        ]
        readiness = hephaestus_status._catalogue_readiness(_manifest(tools))
        assert readiness["measured"] == 1

    def test_a_free_capability_is_not_counted_as_priced(self):
        tools = [{"capability_id": "free@v1", "price_per_call_usd": 0.0,
                  "input_schema": {"properties": {}}, "output_schema": {"type": "object"}}]
        assert hephaestus_status._catalogue_readiness(_manifest(tools))["priced"] == 0

    def test_junk_is_not_a_catalogue(self):
        assert hephaestus_status._catalogue_readiness(None) == {}
        assert hephaestus_status._catalogue_readiness({"tools": "nope"}) == {}
        assert hephaestus_status._catalogue_readiness(_manifest(["not-a-dict"]))["capabilities"] == 0


class TestTotals:
    def test_small_prices_add_up_exactly(self):
        traces = [_trace(total_usd=0.001), _trace(total_usd=0.001), _trace(total_usd=0.005)]
        totals = hephaestus_status._totals(traces)
        assert totals["spend_usd"] == 0.007
        assert totals["runs"] == 3
        assert totals["hops"] == 6

    def test_failures_are_counted_separately(self):
        totals = hephaestus_status._totals([_trace(), _trace(failed=True)])
        assert totals["failed"] == 1

    def test_a_missing_total_does_not_poison_the_sum(self):
        totals = hephaestus_status._totals([_trace(total_usd=None), _trace(total_usd=0.004)])
        assert totals["spend_usd"] == 0.004


class TestApplyToNodes:
    def test_runs_make_it_active(self):
        nodes = [hephaestus_node_spec()]
        hephaestus_status.apply_hephaestus_to_nodes(
            nodes, {"traces": [_trace()], "catalogue": {"capabilities": 76}}
        )
        node = nodes[0]
        assert node["status"] == "active"
        assert node["metrics"] == {"runs": 1, "spend_usd": 0.006, "capabilities": 76}
        assert node["hephaestus_live"]["traces"][0]["trace_id"] == "tr_abc123abc123"

    def test_reachable_but_never_used_is_idle_not_active(self):
        """A studio nobody has run anything through is exactly what the map should say."""
        nodes = [hephaestus_node_spec()]
        hephaestus_status.apply_hephaestus_to_nodes(nodes, {"traces": [], "catalogue": {"capabilities": 76}})
        assert nodes[0]["status"] == "idle"
        assert nodes[0]["metrics"]["runs"] == 0

    def test_going_offline_clears_the_last_good_payload(self):
        """Stale numbers under an offline badge are worse than no numbers."""
        nodes = [hephaestus_node_spec()]
        hephaestus_status.apply_hephaestus_to_nodes(nodes, {"traces": [_trace()], "catalogue": {}})
        assert "hephaestus_live" in nodes[0]

        hephaestus_status.apply_hephaestus_to_nodes(nodes, None)
        assert nodes[0]["status"] == "offline"
        assert "hephaestus_live" not in nodes[0]
        assert nodes[0]["metrics"] == {"runs": 0, "spend_usd": 0, "capabilities": 0}

    def test_a_missing_node_is_not_an_error(self):
        nodes = [{"id": "hub"}]
        hephaestus_status.apply_hephaestus_to_nodes(nodes, {"traces": [_trace()]})
        assert nodes == [{"id": "hub"}]


class TestTraceSanitising:
    def test_only_projection_fields_survive(self):
        raw = [dict(_trace(), channel_id="ch_secret", signature="sig")]
        cleaned = hephaestus_status._sanitize_traces(raw)
        assert "channel_id" not in cleaned[0]
        assert "signature" not in cleaned[0]
        assert cleaned[0]["steps"][0]["capability_id"] == "web.search@v1"

    def test_blame_keeps_the_named_hop_and_the_cleared_ones(self):
        raw = [_trace(failed=True, blame={
            "policy": "hop-level",
            "at_fault": {"id": "v", "capability_id": "metis.verify@v1", "status_code": 500},
            "not_at_fault": ["s"],
            "not_executed": [],
        })]
        cleaned = hephaestus_status._sanitize_traces(raw)
        assert cleaned[0]["blame"]["at_fault"]["capability_id"] == "metis.verify@v1"
        assert cleaned[0]["blame"]["not_at_fault"] == ["s"]

    def test_junk_rows_are_dropped(self):
        assert hephaestus_status._sanitize_traces(None) == []
        assert hephaestus_status._sanitize_traces(["nope", 3]) == []
        assert hephaestus_status._sanitize_traces([{"trace_id": "tr_x"}])[0]["steps"] == []
