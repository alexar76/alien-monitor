"""DOLOS on the map: registered in every place a node must be, and honest about the last scan.

Pins the same structural defect the touchstone test does — "four places or the node silently
vanishes" (build_topology, seed_entities, the reseed path, and get_topology_links) — plus the
honesty rule specific to a red team: the node is `idle` before any scan and only turns `alert` for
a REAL (sandbox, non-by-design) exploit, never for merely having answered.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import dolos_status  # noqa: E402
from dolos_layers import dolos_node_spec, dolos_topology_links  # noqa: E402
from ecosystem_layout import NODE_POSITIONS, ring_position  # noqa: E402


def _dist(a, b):
    return math.sqrt((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2 + (a["z"] - b["z"]) ** 2)


class TestRegisteredInEveryPlace:
    def test_the_node_is_in_build_topology_with_its_edges(self):
        import main

        nodes, links = main.build_topology()
        assert "dolos" in {n["id"] for n in nodes}
        pairs = {(link["source"], link["target"]) for link in links}
        assert ("acex", "dolos") in pairs, "forks & attacks the ACEX contracts"
        assert ("dolos", "basanos") in pairs, "confirms/refutes the static layer"
        assert ("dolos", "skopos") in pairs, "a confirmed finding feeds the healing loop"

    def test_the_node_is_seeded_in_universe_mode(self):
        from universe import VirtualUniverse

        u = VirtualUniverse()
        u.seed_entities()
        assert "dolos" in u.entities
        assert u.entities["dolos"].position == NODE_POSITIONS["dolos"]

    def test_the_node_survives_the_topology_reseed_path(self):
        from universe import VirtualUniverse

        u = VirtualUniverse()
        u.seed_entities()
        u.entities.pop("dolos", None)
        u._ensure_topology_seeded()
        assert "dolos" in u.entities

    def test_universe_topology_links_include_it(self):
        from universe import VirtualUniverse

        u = VirtualUniverse()
        u.seed_entities()
        pairs = {(link["source"], link["target"]) for link in u.get_topology_links()}
        assert ("acex", "dolos") in pairs
        assert ("lottery", "dolos") in pairs

    def test_every_edge_ends_on_a_node_that_exists(self):
        import main

        nodes, _links = main.build_topology()
        ids = {n["id"] for n in nodes}
        for link in dolos_topology_links():
            assert link["source"] in ids, f"dangling source {link['source']}"
            assert link["target"] in ids, f"dangling target {link['target']}"


class TestPositionAndSpec:
    def test_it_keeps_its_distance_from_everything_else(self):
        position = NODE_POSITIONS["dolos"]
        for node_id, other in NODE_POSITIONS.items():
            if node_id == "dolos" or not isinstance(other, dict) or "x" not in other:
                continue
            assert _dist(position, other) >= 4.5, f"too close to {node_id}"
        total = 17
        for i in range(total):
            assert _dist(position, ring_position(i, total)) >= 4.5, f"too close to oracle[{i}]"

    def test_the_spec_starts_idle_with_no_invented_verdict(self):
        spec = dolos_node_spec()
        assert spec["status"] == "idle"
        assert spec["group"] == "security"
        assert spec["metrics"].get("exploited") == 0

    def test_the_description_carries_the_safety_boundary_and_siblings(self):
        d = dolos_node_spec()["description"]
        assert "BASANOS" in d and "MOMUS" in d
        assert "advisory" in d.lower()
        for word in ("fork", "sandbox"):
            assert word in d.lower(), f"description must state it is {word}-bounded"


class TestApplyToNodes:
    def test_idle_before_any_scan(self):
        nodes = [dolos_node_spec()]
        dolos_status.apply_dolos_to_nodes(nodes, {"ran": False, "attacks": 3})
        assert nodes[0]["status"] == "idle"

    def test_active_when_the_contracts_held(self):
        nodes = [dolos_node_spec()]
        dolos_status.apply_dolos_to_nodes(
            nodes, {"ran": True, "attacks": 3, "held": 3, "exploited": 0, "real_exploits": 0})
        assert nodes[0]["status"] == "active"

    def test_alert_only_for_a_real_exploit(self):
        nodes = [dolos_node_spec()]
        dolos_status.apply_dolos_to_nodes(
            nodes, {"ran": True, "attacks": 3, "held": 2, "exploited": 1, "real_exploits": 1})
        assert nodes[0]["status"] == "alert"

    def test_a_by_design_exploit_does_not_raise_alert(self):
        """A finding tagged [BY DESIGN] / [ADVISORY] is not counted as a real exploit, so the
        node stays green — the honesty rule the red team must not break."""
        nodes = [dolos_node_spec()]
        status = dolos_status.fetch_dolos_status_sync.__wrapped__ if hasattr(
            dolos_status.fetch_dolos_status_sync, "__wrapped__") else None
        _ = status
        # real_exploits already excludes by-design; simulate the status a by-design-only scan yields
        dolos_status.apply_dolos_to_nodes(
            nodes, {"ran": True, "attacks": 3, "held": 2, "exploited": 1, "real_exploits": 0})
        assert nodes[0]["status"] == "active"
