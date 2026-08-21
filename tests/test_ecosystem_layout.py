"""3D layout spacing — oracle ring must not crowd static nodes."""

from __future__ import annotations

import math
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from ecosystem_layout import (  # noqa: E402
    FEDERATED_HUB_SLOTS,
    MESH_AGENT_SLOTS,
    NODE_POSITIONS,
    ORACLE_RING_CENTER,
    ORACLE_RING_RADIUS,
    federated_hub_position,
    mesh_agent_position,
    ring_position,
)
from oracle_family import ORACLE_FAMILY  # noqa: E402


def _dist(a: dict[str, float], b: dict[str, float]) -> float:
    return math.sqrt(
        (a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2 + (a["z"] - b["z"]) ** 2
    )


def test_competing_galaxy_far_from_primary_hub():
    hub = NODE_POSITIONS["hub"]
    for nid in ("competing_hub", "signal_hunt_hub", "signal_hunt", "use_cases"):
        assert _dist(hub, NODE_POSITIONS[nid]) >= 28.0, nid


def test_competing_galaxy_clear_of_oracle_ring():
    from ecosystem_layout import COMPETING_GALAXY_ANCHOR, ORACLE_RING_CENTER

    ax, ay, az = COMPETING_GALAXY_ANCHOR
    cx, cy, cz = ORACLE_RING_CENTER
    d = math.sqrt((ax - cx) ** 2 + (ay - cy) ** 2 + (az - cz) ** 2)
    assert d >= 20.0


def test_colony_far_from_desktop_apps():
    desktop = NODE_POSITIONS["desktop_apps"]
    colony = ring_position(5, len(ORACLE_FAMILY))
    assert _dist(desktop, colony) >= 12.0


def test_oracle_ring_nodes_separated_from_static_nodes():
    total = len(ORACLE_FAMILY)
    static = list(NODE_POSITIONS.values())
    min_gap = 4.5
    for i in range(total):
        oracle = ring_position(i, total)
        for pos in static:
            assert _dist(oracle, pos) >= min_gap, f"oracle[{i}] too close to static node"


def test_oracle_ring_center_in_east_sector():
    cx, _, _ = ORACLE_RING_CENTER
    assert cx >= ORACLE_RING_RADIUS


# The UNI graph seeds the mesh a little tighter than NODE_POSITIONS does; agents
# must stay clear of the static shelf under either anchor.
_MESH_ANCHORS = [None, {"x": -4.0, "y": -1.0, "z": 2.0}]


def test_mesh_agents_are_not_at_the_origin():
    """Regression: every agent used to inherit (0,0,0) and hide inside the hub."""
    for anchor in _MESH_ANCHORS:
        for i in range(MESH_AGENT_SLOTS):
            pos = mesh_agent_position(i, mesh_pos=anchor)
            assert _dist(pos, NODE_POSITIONS["hub"]) >= 4.0, f"agent[{i}] sits on the hub"


def test_mesh_agent_slots_separated_from_static_nodes():
    for anchor in _MESH_ANCHORS:
        for i in range(MESH_AGENT_SLOTS):
            pos = mesh_agent_position(i, mesh_pos=anchor)
            for nid, static in NODE_POSITIONS.items():
                assert _dist(pos, static) >= 2.5, f"agent[{i}] too close to {nid}"


def test_mesh_agent_slots_do_not_collide():
    positions = [mesh_agent_position(i) for i in range(MESH_AGENT_SLOTS)]
    for i in range(len(positions)):
        for j in range(i + 1, len(positions)):
            assert _dist(positions[i], positions[j]) >= 1.4, f"agents {i}/{j} overlap"


def test_first_agents_spread_over_the_shell():
    """The common case is a handful of agents — they must not crowd one cap."""
    for i in range(3):
        for j in range(i + 1, 3):
            assert _dist(mesh_agent_position(i), mesh_agent_position(j)) >= 2.0


_FED_ANCHORS = [None, {"x": -2.0, "y": 5.0, "z": 1.0}]


def test_federated_hubs_are_not_inside_the_hub():
    """Regression: random.uniform(-4, 4) per axis could drop a hub inside the hub."""
    for anchor in _FED_ANCHORS:
        for i in range(FEDERATED_HUB_SLOTS):
            pos = federated_hub_position(i, federation_pos=anchor)
            assert _dist(pos, NODE_POSITIONS["hub"]) >= 6.0, f"federated[{i}] sits on the hub"


def test_federated_hub_slots_clear_the_static_shelf():
    for anchor in _FED_ANCHORS:
        for i in range(FEDERATED_HUB_SLOTS):
            pos = federated_hub_position(i, federation_pos=anchor)
            for nid, static in NODE_POSITIONS.items():
                if nid == "federation":
                    continue  # its own anchor — the ring is hung off it on purpose
                assert _dist(pos, static) >= 2.5, f"federated[{i}] too close to {nid}"


def test_federated_hub_ring_clears_the_discovered_peer_ring():
    """hub_discovery puts live peers on a 3.2 ring around the same anchor."""
    from hub_discovery import _FED_ANCHOR, _position_for

    anchor = {"x": _FED_ANCHOR[0], "y": _FED_ANCHOR[1], "z": _FED_ANCHOR[2]}
    peers = [_position_for(f"peer-{i}") for i in range(24)]
    for i in range(FEDERATED_HUB_SLOTS):
        pos = federated_hub_position(i, federation_pos=anchor)
        for peer in peers:
            assert _dist(pos, peer) >= 2.0, f"federated[{i}] lands on a discovered peer"


def test_federated_hub_slot_is_stable_across_respawns():
    """Keyed by the hub's slot, not re-rolled — a respawned hub returns to its place."""
    assert federated_hub_position(3) == federated_hub_position(3)
    assert federated_hub_position(3 + FEDERATED_HUB_SLOTS) == federated_hub_position(3)


def test_first_federated_hubs_spread_around_the_ring():
    for i in range(3):
        for j in range(i + 1, 3):
            assert _dist(federated_hub_position(i), federated_hub_position(j)) >= 3.0


def test_mesh_agent_slot_is_stable_as_the_swarm_grows():
    """Slot depends on the agent's index alone, so registering one never moves the rest."""
    before = mesh_agent_position(1)
    assert mesh_agent_position(1) == before
    assert mesh_agent_position(1 + MESH_AGENT_SLOTS) == before
