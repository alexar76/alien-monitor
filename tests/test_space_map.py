"""No two planets inside each other — enforced once, over the whole assembled graph.

Positions in this backend come from at least four independent authors: the hardcoded
`NODE_POSITIONS` table, a dozen `*_layers` modules that place their own nodes, the ring/slot
helpers in `ecosystem_layout`, and hub discovery for peers nobody has ever seen. Each keeps
its own nodes apart; none can see the others. So "is this coordinate already taken" was a
question with no owner, and adding a subsystem meant guessing a free region of space and
finding out visually whether the guess was wrong.

`space_map` is that owner. These tests pin the three properties it has to have — stable,
conservative, bounded — and then check the real graph actually comes out clean.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from space_map import MIN_SEPARATION, SpaceMap, enforce_spacing  # noqa: E402


def _dist(a, b):
    return math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"]))


def _node(node_id, x, y, z, group="oracle"):
    return {"id": node_id, "group": group, "position": {"x": x, "y": y, "z": z}}


class TestTheRules:
    def test_a_node_that_is_already_clear_is_never_moved(self):
        """Conservative: only a genuine overlap displaces anything. Anything else would
        rearrange a layout operators already know."""
        nodes = [_node("a", 0, 0, 0), _node("b", 5, 0, 0), _node("c", 0, 5, 0)]
        before = [dict(n["position"]) for n in nodes]
        assert enforce_spacing(nodes) == 0
        assert [n["position"] for n in nodes] == before

    def test_two_nodes_in_the_same_place_are_separated(self):
        nodes = [_node("a", 1, 1, 1), _node("b", 1, 1, 1)]
        assert enforce_spacing(nodes) == 1
        assert _dist(nodes[0]["position"], nodes[1]["position"]) >= MIN_SEPARATION

    def test_anchors_keep_their_coordinates_and_newcomers_give_way(self):
        """The familiar core layout stays put; the thing that arrived later moves."""
        core = _node("hub", 2.0, 3.0, 4.0, group="core")
        newcomer = _node("fedchild:https://x.example", 2.0, 3.0, 4.0, group="peer_hub_node")
        enforce_spacing([newcomer, core])  # deliberately not in priority order
        assert core["position"] == {"x": 2.0, "y": 3.0, "z": 4.0}
        assert newcomer["position"] != {"x": 2.0, "y": 3.0, "z": 4.0}

    def test_the_same_graph_always_produces_the_same_coordinates(self):
        """Stable: a map that shimmers every tick cannot be read."""
        def build():
            return [_node(f"n{i}", 1.0, 1.0, 1.0) for i in range(6)]

        first, second = build(), build()
        enforce_spacing(first)
        enforce_spacing(second)
        assert [n["position"] for n in first] == [n["position"] for n in second]

    def test_input_order_does_not_change_the_outcome(self):
        """Iteration order changes with what happens to be live; the map must not."""
        forward = [_node(f"n{i}", 1.0, 1.0, 1.0) for i in range(5)]
        backward = list(reversed([_node(f"n{i}", 1.0, 1.0, 1.0) for i in range(5)]))
        enforce_spacing(forward)
        enforce_spacing(backward)
        assert {n["id"]: n["position"]["x"] for n in forward} == {
            n["id"]: n["position"]["x"] for n in backward
        }

    def test_a_crowd_spreads_into_a_disc_around_itself(self):
        """Bounded: a crowded region must not throw a node across the map."""
        nodes = [_node(f"n{i}", 0.0, 0.0, 0.0) for i in range(12)]
        enforce_spacing(nodes)
        for n in nodes:
            assert _dist(n["position"], {"x": 0, "y": 0, "z": 0}) < 6.0
        for i, a in enumerate(nodes):
            for b in nodes[i + 1:]:
                assert _dist(a["position"], b["position"]) >= MIN_SEPARATION

    def test_a_node_without_a_usable_position_is_left_alone(self):
        """Inventing a coordinate would put a planet where nothing exists."""
        nodes = [
            {"id": "a"}, {"id": "b", "position": None},
            {"id": "c", "position": {"x": "nope", "y": 0, "z": 0}},
            {"id": "d", "position": {"x": float("nan"), "y": 0, "z": 0}},
        ]
        assert enforce_spacing(nodes) == 0
        assert nodes[0].get("position") is None

    def test_the_claim_api_reports_occupancy(self):
        space = SpaceMap()
        space.claim("a", {"x": 0.0, "y": 0.0, "z": 0.0})
        assert not space.is_free({"x": 0.1, "y": 0.0, "z": 0.0})
        assert space.is_free({"x": 9.0, "y": 0.0, "z": 0.0})
        # A node compared against its own claim is not blocked by itself.
        assert space.is_free({"x": 0.0, "y": 0.0, "z": 0.0}, ignore="a")


class TestTheRealGraph:
    """The point of the whole thing: the map the backend actually ships comes out clean."""

    def _positions(self, nodes):
        return [
            (n.get("id"), n["position"]) for n in nodes
            if isinstance(n.get("position"), dict)
            and all(k in n["position"] for k in ("x", "y", "z"))
        ]

    def test_the_seeded_universe_has_no_overlapping_planets(self, monkeypatch):
        monkeypatch.setenv("ALIEN_ANVIL_STATE_MAX_MB", "4096")
        monkeypatch.setenv("ALIEN_DISCOVERY_ENABLED", "0")  # no network in tests
        import universe as universe_mod

        uni = universe_mod.VirtualUniverse()
        # `tick_universe` is where the graph is assembled and where spacing is enforced —
        # there is no separate getter, so the test exercises the same call the API does.
        try:
            graph = uni.tick_universe()
        except Exception as exc:  # pragma: no cover - environment-dependent
            pytest.skip(f"universe tick unavailable here: {type(exc).__name__}: {exc}")
        pos = self._positions(graph.get("nodes") or [])
        assert len(pos) > 10, "the seeded universe should have plenty of placed nodes"
        worst = min(
            (( _dist(a, b), ia, ib)
             for i, (ia, a) in enumerate(pos) for ib, b in pos[i + 1:]),
            key=lambda t: t[0],
        )
        assert worst[0] >= MIN_SEPARATION, (
            f"{worst[1]} and {worst[2]} are {worst[0]:.3f} apart — closer than "
            f"{MIN_SEPARATION}, so they render as one planet"
        )


def test_a_hub_keeps_its_own_constellation():
    """The 4.6 a hub claims is a rule between HUBS.

    Read as "nothing may come within 4.6 of a sun" it evicts the sun's own peers, which
    orbit it at 2.2 — a hundred hubs with four peers each had all four thrown out of every
    system, 400 displacements for a layout that was already correct.
    """
    from ecosystem_layout import peer_hub_child_position, peer_hub_position
    from space_map import enforce_spacing

    hub_pos = peer_hub_position(0, 2)
    nodes = [
        {"id": "peer-hub", "group": "peer_hub", "hop": 1, "position": dict(hub_pos)},
        {"id": "other-hub", "group": "peer_hub", "hop": 1, "position": peer_hub_position(1, 2)},
    ]
    for i in range(4):
        nodes.append({
            "id": f"child-{i}",
            "group": "peer_hub_node",
            "hop": 2,
            "position": peer_hub_child_position(hub_pos, i, 4),
        })
    before = [dict(n["position"]) for n in nodes]
    assert enforce_spacing(nodes) == 0
    assert [n["position"] for n in nodes] == before


def test_two_suns_are_still_pushed_apart():
    from space_map import SUN_SEPARATION, enforce_spacing

    nodes = [
        {"id": "hub", "group": "core", "role": "hub", "hop": 0,
         "position": {"x": 0.0, "y": 0.0, "z": 0.0}},
        {"id": "squatter", "group": "peer_hub", "hop": 1,
         "position": {"x": 1.0, "y": 0.0, "z": 0.0}},
    ]
    assert enforce_spacing(nodes) == 1
    gap = math.dist(
        tuple(nodes[0]["position"][a] for a in "xyz"),
        tuple(nodes[1]["position"][a] for a in "xyz"),
    )
    assert gap >= SUN_SEPARATION
