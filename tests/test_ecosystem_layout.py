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


def test_agents_clear_of_federation_corona():
    """Regression: UNI used to stack Agents on Federation (~1 unit apart)."""
    agents = NODE_POSITIONS["factory_agents"]
    federation = NODE_POSITIONS["federation"]
    assert _dist(agents, federation) >= 8.0


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


# ── The shelf must not crowd itself ──────────────────────────────────────────
# Every separation rule here guarded a MOVING thing — oracle ring, mesh agents,
# federated hubs — against the static shelf. Nothing guarded the shelf against
# itself, so it drifted together: the factory sat 2.06 from the escrow and 2.28
# from settlement, and at those sizes two coronas read as one object.

_STATIC_MIN_GAP = 2.5


def test_static_nodes_keep_their_distance():
    items = list(NODE_POSITIONS.items())
    for i, (a_id, a) in enumerate(items):
        for b_id, b in items[i + 1:]:
            assert _dist(a, b) >= _STATIC_MIN_GAP, (
                f"{a_id} and {b_id} are {_dist(a, b):.2f} apart — closer than "
                f"{_STATIC_MIN_GAP}, which reads as one object on the map"
            )


def test_two_suns_never_share_a_halo():
    """A hub is not a shelf node.

    The scene gives it orbit belts, a corona, a gravity well and its own point light —
    about two units of glow — so two hubs need both footprints plus room for a label.
    Competing Lab Hub and Signal Hunt Hub used to sit 4.18 apart, and on the live map
    their belts read as one object with two names.
    """
    from ecosystem_layout import HUB_SUN_MIN_GAP, SUN_IDS

    for i, a_id in enumerate(SUN_IDS):
        for b_id in SUN_IDS[i + 1:]:
            gap = _dist(NODE_POSITIONS[a_id], NODE_POSITIONS[b_id])
            assert gap >= HUB_SUN_MIN_GAP, (
                f"{a_id} and {b_id} are {gap:.2f} apart — two suns inside "
                f"{HUB_SUN_MIN_GAP} share a halo"
            )


def test_a_hub_keeps_its_own_moons_and_no_others():
    """Spread apart, but still grouped: Signal Hunt orbits the hub that serves it, and
    moving that hub off Competing Lab must not leave its game behind."""
    from ecosystem_layout import HUB_SUN_MIN_GAP

    hub = NODE_POSITIONS["signal_hunt_hub"]
    assert _dist(NODE_POSITIONS["signal_hunt"], hub) < HUB_SUN_MIN_GAP + 1.5
    assert _dist(NODE_POSITIONS["signal_hunt"], hub) < _dist(
        NODE_POSITIONS["signal_hunt"], NODE_POSITIONS["competing_hub"]
    ), "the game drifted closer to the other hub than to its own"


def test_the_factory_has_room_around_it():
    """It carries the most neighbours: escrow, settlement, NFT, the forge, and two
    pinned product moons."""
    factory = NODE_POSITIONS["factory"]
    for nid in ("evm_escrow", "settlement", "nft_contract"):
        assert _dist(NODE_POSITIONS[nid], factory) >= 2.9, f"{nid} crowds the factory"


def test_settlement_sits_on_the_hub_escrow_line():
    """The placement is the explanation: an authorisation goes one way, a debit the
    other, and the node is what happens in between. Moving it off that line to make
    room would keep the distance and lose the meaning.
    """
    hub = NODE_POSITIONS["hub"]
    escrow = NODE_POSITIONS["evm_escrow"]
    node = NODE_POSITIONS["settlement"]

    span = {k: escrow[k] - hub[k] for k in ("x", "y", "z")}
    t = (node["x"] - hub["x"]) / span["x"]
    assert 0.2 < t < 0.8, f"settlement should sit between the two, t={t:.2f}"
    projected = {k: hub[k] + t * span[k] for k in ("x", "y", "z")}
    assert _dist(node, projected) < 0.05, "settlement drifted off the hub→escrow line"


def test_the_product_nebula_stays_out_of_the_oracle_ring():
    """It went missing by being drawn inside it.

    Measured live: at the old offset the catalogue's nearest neighbours were three
    oracles at 3.5-4.2, so nineteen products read as one more small ball among eighteen
    bright ones. Being a moon of the factory is the point; being lost in somebody else's
    constellation is not.
    """
    import math

    from ecosystem_layout import ORACLE_RING_CENTER, ORACLE_RING_RADIUS, ring_position
    from factory_products import build_product_clusters

    factory = NODE_POSITIONS["factory"]
    nodes, _links = build_product_clusters(
        [{"id": f"p{i}", "name": f"P{i}", "category": "saas"} for i in range(19)],
        existing_ids=set(),
        factory_position=factory,
    )
    nebula = nodes[0]["position"]

    cx, cy, cz = ORACLE_RING_CENTER
    to_centre = _dist(nebula, {"x": cx, "y": cy, "z": cz})
    assert to_centre > ORACLE_RING_RADIUS + 2.0, (
        f"the catalogue sits {to_centre:.1f} from the ring centre — inside the oracles"
    )

    total = len(ORACLE_FAMILY)
    for i in range(total):
        assert _dist(nebula, ring_position(i, total)) >= 3.0, "an oracle crowds the catalogue"

    for nid, static in NODE_POSITIONS.items():
        assert _dist(nebula, static) >= 2.5, f"the catalogue crowds {nid}"

    # Still the factory's own moon, not a distant object with a long thin edge.
    assert 3.0 <= _dist(nebula, factory) <= 6.0


# ── A node nobody placed ─────────────────────────────────────────────────────
# The last resort used to be (0, 0, 0) — the hub — so an unplaced node did not land
# somewhere unfortunate, it vanished inside another one. Adding a satellite should not
# require picking a coordinate by hand; only a coordinate that MEANS something should.


def test_an_unplaced_node_does_not_land_inside_the_hub():
    from ecosystem_layout import auto_node_position, node_position

    for nid in ("praxis", "kova", "aegis", "some-new-hub", "a-satellite-shipped-tomorrow"):
        p = node_position(nid)
        assert p == auto_node_position(nid)
        assert _dist(p, NODE_POSITIONS["hub"]) >= 4.0, f"{nid} sits on the hub"


def test_an_auto_position_is_stable_for_the_same_node():
    """A node that jumps every deploy is a node nobody can point at."""
    from ecosystem_layout import auto_node_position

    for nid in ("praxis", "kova"):
        assert auto_node_position(nid) == auto_node_position(nid)


def test_auto_positions_keep_clear_of_everything_already_drawn():
    from ecosystem_layout import ORACLE_RING_CENTER, ORACLE_RING_RADIUS, auto_node_position

    centre = {"x": ORACLE_RING_CENTER[0], "y": ORACLE_RING_CENTER[1], "z": ORACLE_RING_CENTER[2]}
    for i in range(40):
        p = auto_node_position(f"satellite-{i}")
        for nid, static in NODE_POSITIONS.items():
            assert _dist(p, static) >= 2.5, f"satellite-{i} crowds {nid}"
        assert _dist(p, centre) >= ORACLE_RING_RADIUS, f"satellite-{i} is inside the oracle ring"
        for j in range(len(ORACLE_FAMILY)):
            assert _dist(p, ring_position(j, len(ORACLE_FAMILY))) >= 2.5


def test_auto_positions_are_distinct_and_survive_the_spacing_sweep():
    """Two nodes placed independently CAN land near each other — the derivation knows
    nothing about anyone else, deliberately, so a node keeps its place when its
    neighbours change. What guarantees the map is space_map.enforce_spacing, which runs
    last over the whole assembled graph; this asserts the pair actually works.
    """
    from ecosystem_layout import auto_node_position
    from space_map import MIN_SEPARATION, enforce_spacing

    points = [auto_node_position(f"satellite-{i}") for i in range(25)]
    assert len({(p["x"], p["y"], p["z"]) for p in points}) == len(points), (
        "two nodes derived the very same coordinate"
    )

    graph = [
        {"id": nid, "group": "core", "position": dict(pos)}
        for nid, pos in NODE_POSITIONS.items()
    ] + [
        {"id": f"satellite-{i}", "group": "oracle", "position": dict(p)}
        for i, p in enumerate(points)
    ]
    enforce_spacing(graph)
    for i, a in enumerate(graph):
        for b in graph[i + 1:]:
            assert _dist(a["position"], b["position"]) >= MIN_SEPARATION - 1e-6, (
                f"{a['id']} and {b['id']} still overlap after the sweep"
            )


def test_a_hand_written_coordinate_still_wins():
    """Because it is a statement, not a slot — settlement's line, WARDEN beside ARGUS."""
    from ecosystem_layout import node_position

    assert node_position("settlement") == NODE_POSITIONS["settlement"]
    assert node_position("factory") == NODE_POSITIONS["factory"]
