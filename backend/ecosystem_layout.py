"""Shared 3D anchors for the Alien Monitor ecosystem graph.

Keeps static nodes and the oracle ring in separate sectors so pulsing
coronas do not overlap (e.g. Colony vs Desktop Apps).
"""

from __future__ import annotations

import hashlib
import math

# Federation + discovered peer mini-ring
FEDERATION_ANCHOR = (0.0, 8.0, 2.0)
FEDERATION_PEER_RADIUS = 4.0

# Oracle family — far east sector (+X), away from client shelf (-X)
ORACLE_RING_CENTER = (17.0, 0.0, 1.0)
ORACLE_RING_RADIUS = 7.5
ORACLE_RING_Y_AMPLITUDE = 1.5

# Competing lab galaxy — far from the primary hub (0,0,0) and clear of the oracle ring.
# Host: hunt.modelmarket.dev · public peer :9083 · hunt.modelmarket.dev · use.modelmarket.dev
COMPETING_GALAXY_ANCHOR = (30.0, 12.0, -20.0)
COMPETING_GALAXY_RADIUS = 4.0

# A hub is drawn as a SUN — its own sphere plus orbit belts, a corona, a gravity well and a
# point light, roughly two units of glow around the centre. Two of them need both footprints
# and a gap wide enough to read a label through; the 2.5 that separates ordinary shelf nodes
# leaves their belts interlocked. Mirrors HUB_MIN_GAP in the frontend's federationLayout.ts,
# which spaces the hubs the browser adds when a peer's neighbourhood is expanded.
HUB_SUN_MIN_GAP = 4.6

#: Static nodes the scene draws as suns (frontend `isHubRole`). Everything else on the shelf
#: is a planet and lives under the smaller _STATIC_MIN_GAP.
SUN_IDS = ("hub", "factory", "competing_hub", "signal_hunt_hub")

# ~1.3× baseline spacing — hub stays at origin
NODE_POSITIONS: dict[str, dict[str, float]] = {
    "hub": {"x": 0.0, "y": 0.0, "z": 0.0},
    "factory": {"x": 5.0, "y": 2.5, "z": -2.5},
    "mesh": {"x": -5.0, "y": -1.5, "z": 2.5},
    "acex": {"x": 2.5, "y": -4.0, "z": 5.0},
    "evm_escrow": {"x": 6.0, "y": 6.0, "z": -2.0},
    # On the line from the hub to the escrow: an authorisation goes one way, a debit the
    # other, and the node is what happens in between. Kept at t=0.42 along that line rather
    # than the middle: at t≈0.55 it sat 2.28 from the factory, and two coronas that size
    # read as one object. test_static_nodes_keep_their_distance enforces the floor now,
    # test_settlement_sits_on_the_hub_escrow_line the meaning.
    "settlement": {"x": 2.52, "y": 2.52, "z": -0.84},
    "solana_escrow": {"x": 4.5, "y": -3.5, "z": -5.5},
    "nft_contract": {"x": 6.5, "y": 0.5, "z": -5.0},
    "desktop_apps": {"x": -7.5, "y": 5.5, "z": -7.0},
    "plugins": {"x": 0.0, "y": -6.5, "z": -4.0},
    # Publish-time trust gate: close to Hub, but outside its corona and clear of
    # Factory/contract nodes.  The links read candidate → audit → admission.
    "themis": {"x": 0.0, "y": 4.0, "z": -4.0},
    # The Solidity touchstone sits on the contract side (+X, -Y), between ACEX and the
    # escrow/NFT trees it scans, and deliberately away from the western security sector:
    # MOMUS probes running services, BASANOS reads source at a pinned commit, and drawing
    # them as neighbours would suggest one is a stage of the other. Nearest neighbour is
    # the forge at 6.18 and the oracle ring stays 6.13 out, both clear of the 4.5 the
    # separation tests enforce.
    "basanos": {"x": 8.5, "y": -6.0, "z": 2.0},
    "sdk_dart": {"x": -6.5, "y": 1.5, "z": 6.5},
    "sdk_typescript": {"x": -7.5, "y": -1.5, "z": 5.0},
    "sdk_rust": {"x": -6.5, "y": 2.5, "z": -6.5},
    "federation": {"x": FEDERATION_ANCHOR[0], "y": FEDERATION_ANCHOR[1], "z": FEDERATION_ANCHOR[2]},
    "widget": {"x": -5.0, "y": 7.0, "z": -4.5},
    "ethereum": {"x": 3.5, "y": 6.5, "z": 5.5},
    "solana": {"x": 4.0, "y": -6.5, "z": 7.0},
    "cli": {"x": -6.5, "y": -5.5, "z": 6.5},
    "argus": {"x": -8.0, "y": 2.5, "z": 2.0},
    # The forge sits between the hub whose catalogue it reads and the factory whose
    # pipeline executor it submits to — the two edges that describe what it is. Nearest
    # neighbour 4.95, oracle ring 5.44, both above the 4.8 the separation tests enforce.
    "hephaestus": {"x": 4.5, "y": -2.0, "z": -0.5},
    # Agents the factory built and shipped — sit on the factory/contract shelf
    # (south-back of hub), not under Federation's high-Y corona. UNI used to seed
    # Federation at (-2,5,1) with Agents at (-2.5,4,1); coronas stacked on screen.
    "factory_agents": {"x": 1.0, "y": 1.5, "z": -8.5},
    "dioscuri": {"x": -9.5, "y": 5.5, "z": -2.0},
    "helios": {"x": -8.5, "y": 7.5, "z": -5.0},
    "metis": {"x": -10.5, "y": 0.0, "z": 4.5},
    "skopos": {"x": -11.5, "y": -3.5, "z": 1.5},
    "gaia": {"x": -6.5, "y": 8.5, "z": -6.5},
    "atlas": {"x": -4.5, "y": 9.0, "z": -8.0},
    # Cognition sector: LOGOS watches the whole federation, so it sits back from the
    # hub with a clear line to Metis (understanding), MOMUS (findings) and the
    # Treasury (balance) — the three it actually polls. Keeps the ≥4.5 separation the
    # ring test enforces from metis (-10.5,0,4.5) and skopos (-11.5,-3.5,1.5).
    "logos": {"x": -14.5, "y": -2.0, "z": 5.5},
    # Security sector (west, near ARGUS): the red team and its separate purse.
    # WARDEN sits between MOMUS (which signs its feed) and ARGUS (which enforces it)
    # — deliberately close to ARGUS, because it runs inside it rather than beside it.
    "warden": {"x": -10.0, "y": 3.6, "z": 0.0},
    "momus": {"x": -12.5, "y": 3.0, "z": -3.0},
    "treasury": {"x": -13.5, "y": 1.0, "z": -1.0},
    # Third paid invoke channel — front-south, on the client side of the hub between ACEX and
    # the SDK/CLI shelf, so the billed edge into the hub reads as inbound traffic rather than as
    # another core service sitting beside it. Nearest neighbour is ACEX at 4.5, the same gap the
    # oracle-ring separation test enforces.
    "bridges": {"x": -1.5, "y": -4.5, "z": 7.0},
    # Competing lab galaxy — far SE/back, clear of the primary cloud and the oracle ring (+X≈17).
    # Anchor ≈30 units from hub origin so the Monitor reads as two galaxies, not one crowded ring.
    "competing_hub": {
        "x": COMPETING_GALAXY_ANCHOR[0],
        "y": COMPETING_GALAXY_ANCHOR[1],
        "z": COMPETING_GALAXY_ANCHOR[2],
    },
    # Federation Hub process behind hunt.modelmarket.dev (peer sun).
    # Two SUNS, not two planets: the Monitor draws a hub with orbit belts, a corona, a
    # gravity well and its own point light, so the 2.5 the static shelf gets is not enough.
    # At the old +3.0/+1.5/-2.5 these two sat 4.18 apart and their belts interlocked into
    # one lit knot — see HUB_SUN_MIN_GAP.
    "signal_hunt_hub": {
        "x": COMPETING_GALAXY_ANCHOR[0] + 4.4,
        "y": COMPETING_GALAXY_ANCHOR[1] + 2.0,
        "z": COMPETING_GALAXY_ANCHOR[2] - 3.4,
    },
    # Game / app surface — separate ball, orbits its own Hub. Moved out with it, so it
    # stays that hub's moon rather than landing inside it.
    "signal_hunt": {
        "x": COMPETING_GALAXY_ANCHOR[0] + 7.6,
        "y": COMPETING_GALAXY_ANCHOR[1] + 3.2,
        "z": COMPETING_GALAXY_ANCHOR[2] - 6.0,
    },
    "use_cases": {
        "x": COMPETING_GALAXY_ANCHOR[0] - 2.5,
        "y": COMPETING_GALAXY_ANCHOR[1] - 1.0,
        "z": COMPETING_GALAXY_ANCHOR[2] + 3.0,
    },
}


# Mesh-registered agents — a small shell hanging off the AI Service Mesh node,
# offset down and back from the SDK/CLI shelf. Kept as an offset (not an absolute
# anchor) because the two graph modes seed the mesh at slightly different
# coordinates, and the swarm has to follow whichever one is in play. Without this
# every agent kept EcosystemEntity's default (0, 0, 0) and piled up inside the hub.
MESH_AGENT_OFFSET = (0.5, -5.0, -1.5)
MESH_AGENT_RADIUS = 2.4
MESH_AGENT_SLOTS = 24  # matches the agent cap in sync_agent_entities()
# Slots are handed out with a stride coprime to the slot count, so the common case
# (a handful of agents) spreads over the whole shell instead of crowding one cap.
MESH_AGENT_STRIDE = 7

_GOLDEN_ANGLE = math.pi * (1.0 + math.sqrt(5.0))


def mesh_agent_position(
    index: int, *, mesh_pos: dict[str, float] | None = None
) -> dict[str, float]:
    """Fibonacci-shell slot for the index-th mesh agent.

    Slots are laid out against a fixed capacity rather than the current agent
    count, so a newly registered agent takes a free slot instead of nudging
    every agent already on screen.
    """
    slot = (int(index) * MESH_AGENT_STRIDE) % MESH_AGENT_SLOTS
    y = 1.0 - (2.0 * slot + 1.0) / MESH_AGENT_SLOTS
    r = math.sqrt(max(0.0, 1.0 - y * y))
    ang = _GOLDEN_ANGLE * slot
    base = mesh_pos if mesh_pos is not None else NODE_POSITIONS["mesh"]
    ox, oy, oz = MESH_AGENT_OFFSET
    return {
        "x": round(float(base["x"]) + ox + MESH_AGENT_RADIUS * r * math.cos(ang), 3),
        "y": round(float(base["y"]) + oy + MESH_AGENT_RADIUS * y, 3),
        "z": round(float(base["z"]) + oz + MESH_AGENT_RADIUS * r * math.sin(ang), 3),
    }


# UNI-spawned federated hubs — an outer ring above the federation node, wider than
# the discovered-peer ring (hub_discovery uses 3.2 around the same anchor) so the two
# federation clouds stay readable as separate rings. They used to be scattered with
# random.uniform(-4, 4) per axis around the hub, which could drop one inside the hub
# sphere and moved them on every respawn.
FEDERATED_HUB_OFFSET = (0.0, 4.5, -1.0)
FEDERATED_HUB_RADIUS = 5.0
FEDERATED_HUB_SLOTS = 12  # matches HUB_NAMES in universe_hub_spawner
FEDERATED_HUB_STRIDE = 5  # coprime with the slot count — early spawns spread out
FEDERATED_HUB_Y_TILT = 0.8


# Discovered EXTERNAL hubs and their own ecosystems — an EXPANDING universe.
#
# A fixed ring cannot hold this. Ecosystems grow: a hub with four peers today can have forty,
# and the moment two clusters are wider than the gap between their slots they overlap. So the
# geometry is a function of what is actually out there — hubs are spaced evenly by how many
# there are, the ring is sized by the widest ecosystem, and everything outside moves with it.
# Adding a hub recomputes the map rather than squeezing it, which is the honest behaviour for
# a universe that is still being discovered.
#
# Reading outward from the PRIMARY hub: discovered peers (around the Federation service) ->
# UNI-spawned hubs -> external hub systems (computed) -> unapproved strangers (computed,
# outside everything).  An independent hub is a sun, not another planet in the primary
# federation cloud, so every external system has an explicit minimum centre-to-centre gap.
PEER_HUB_MIN_CENTER_GAP = 18.0
# A tenth-unit guard absorbs the three-decimal coordinate rounding while keeping the public
# contract a clean 18-unit minimum.
PEER_HUB_MIN_RADIUS = PEER_HUB_MIN_CENTER_GAP + 0.1
PEER_HUB_PHASE = math.pi / 16.0    # so a two-hub federation is not axis-aligned
PEER_HUB_Y_TILT = 1.1
PEER_HUB_CLUSTER_MARGIN = 1.4      # empty space between two neighbouring ecosystems
PEER_HUB_CHILD_RADIUS = 2.2        # first shell; leaves room for coronas and labels
PEER_HUB_CHILD_SHELL_STEP = 1.6    # each further shell
PEER_HUB_CHILDREN_PER_SHELL = 8
PEER_HUB_CHILD_Y = 0.42
PENDING_HUB_MARGIN = 2.0
PENDING_HUB_RADIUS_MIN = 9.5
PENDING_HUB_Y_DROP = -1.6
PRIMARY_HUB_CHILD_RADIUS = 12.0
PRIMARY_HUB_CHILD_Y_TILT = 1.4

#: Innermost ring: first-hop discovered peers. Slots replace a hash of the node id — a hash
#: spreads nodes without separating them (the live federation's closest pair was 0.836).
DISCOVERED_PEER_RADIUS = 3.2
DISCOVERED_PEER_SLOTS = 12
DISCOVERED_PEER_STRIDE = 5  # coprime with the slot count
DISCOVERED_PEER_Y_TILT = 0.75


def discovered_peer_position(
    slot_index: int, anchor: tuple[float, float, float]
) -> dict[str, float]:
    """Ring slot for the index-th first-hop peer, around the federation anchor."""
    slot = (int(slot_index) * DISCOVERED_PEER_STRIDE) % DISCOVERED_PEER_SLOTS
    ang = (2.0 * math.pi * slot) / DISCOVERED_PEER_SLOTS
    ax, ay, az = anchor
    return {
        "x": round(ax + DISCOVERED_PEER_RADIUS * math.cos(ang), 3),
        "y": round(ay + DISCOVERED_PEER_Y_TILT * math.sin(ang * 3.0), 3),
        "z": round(az + DISCOVERED_PEER_RADIUS * math.sin(ang), 3),
    }


def primary_hub_child_position(index: int, total: int = 1) -> dict[str, float]:
    """Place an owned provider in the primary hub's star system.

    This orbit is deliberately wider than the dense built-in service shelf.  KOVA and AEGIS
    remain recognisably attached to the central Hub without landing inside Factory, escrow,
    SDK or oracle coronas.
    """
    count = max(1, int(total))
    ang = (2.0 * math.pi * (int(index) % count)) / count + math.pi / 4.0
    base = NODE_POSITIONS["hub"]
    return {
        "x": round(float(base["x"]) + PRIMARY_HUB_CHILD_RADIUS * math.cos(ang), 3),
        "y": round(float(base["y"]) + PRIMARY_HUB_CHILD_Y_TILT * (-1 if index % 2 else 1), 3),
        "z": round(float(base["z"]) + PRIMARY_HUB_CHILD_RADIUS * math.sin(ang), 3),
    }


def peer_hub_cluster_radius(child_count: int) -> float:
    """How much space one hub's ecosystem occupies.

    Children sit on concentric shells rather than one circle: a single circle of forty nodes
    either overlaps itself or needs a radius that shoves the neighbouring hub off the map.
    """
    count = max(0, int(child_count))
    if count == 0:
        return 0.0
    shells = 1 + (count - 1) // PEER_HUB_CHILDREN_PER_SHELL
    return PEER_HUB_CHILD_RADIUS + (shells - 1) * PEER_HUB_CHILD_SHELL_STEP


# A CIRCLE cannot hold a federation. Spacing N hubs evenly on one ring needs
# R = gap / (2·sin(π/N)), which is linear in N: ten hubs at an 18-unit gap need radius 29,
# a hundred need 287, a thousand need 2866. The camera tops out well before that, and the
# map becomes a thin hoop with nothing in the middle of it.
#
# A BALL is the right shape for something that grows. Hubs go on concentric shells, each
# shell holding as many as its surface can at the required gap, and the outer radius then
# grows with the CUBE root: a hundred hubs land inside ~46, a thousand inside ~109. Same
# rule as before — space is a function of how many there are and how fat their ecosystems
# are — applied to a volume instead of a line.

#: Nearest-neighbour separation of a Fibonacci lattice of n points on a UNIT sphere is
#: k/sqrt(n), and k is flat at 3.086 from n=5 up to at least n=800 (measured, not assumed —
#: the hexagonal bound of 3.809 is a limit no golden-spiral shell reaches, and using it puts
#: nine hubs on a shell that holds nine and a tenth one inside somebody's halo).
_LATTICE_SEPARATION_K = 3.08

_GOLDEN_RATIO_ANGLE = math.pi * (1.0 + math.sqrt(5.0))


#: The seeded competing galaxy is somebody else's system that happens to have a hand-written
#: anchor. It already sits outside the hub shell and must not drag the shell out with it.
_REMOTE_GALAXY_IDS = frozenset({"competing_hub", "signal_hunt_hub", "signal_hunt", "use_cases"})

#: Empty space between the last thing this deployment runs and the first foreign hub. Wide
#: enough for a hub's own footprint (~2) and a readable gap on top.
LOCAL_ECOSYSTEM_CLEARANCE = 4.0


def local_ecosystem_radius() -> float:
    """How far this deployment's OWN map reaches out from the hub.

    The first hub shell was a constant, 18.1, chosen against the dense service cloud. The
    oracle ring reaches 24.5 and Platon's cave 26.2, so on our own map that shell ran
    straight THROUGH the oracles: a federated peer landing near +X was drawn inside the
    ring, and its whole constellation with it — the live UNI map put independentai's hub
    between Lumen and Colony with KOVA and AEGIS among the oracles.

    Measured rather than hard-coded, because the answer differs per deployment: a Monitor
    pointed at somebody else's hub draws two nodes and a provider orbit, and pushing its
    federation out to thirty for a shelf it does not have would leave its map hollow.
    """
    from deployment_profile import owns_builtin_shelf

    def magnitude(pos: dict[str, float]) -> float:
        return math.sqrt(pos["x"] ** 2 + pos["y"] ** 2 + pos["z"] ** 2)

    # The hub's own provider orbit exists in every profile.
    far = PRIMARY_HUB_CHILD_RADIUS
    if not owns_builtin_shelf():
        return far
    for node_id, pos in NODE_POSITIONS.items():
        if node_id in _REMOTE_GALAXY_IDS:
            continue
        far = max(far, magnitude(pos))
    try:  # the oracle ring and the cave are generated, not tabulated
        from oracle_family import build_oracle_family_nodes

        for node in build_oracle_family_nodes():
            far = max(far, magnitude(node["position"]))
    except Exception:  # pragma: no cover - layout must not depend on the family loading
        pass
    return far


def peer_hub_gap(max_cluster_radius: float = 0.0) -> float:
    """Centre-to-centre distance two hub systems need.

    Either the flat minimum, or — once ecosystems are wide enough to touch — twice the
    widest cluster plus a margin of empty space between them.
    """
    return max(
        PEER_HUB_MIN_CENTER_GAP,
        2.0 * max(0.0, float(max_cluster_radius)) + PEER_HUB_CLUSTER_MARGIN,
    )


def _shell_capacity(radius: float, gap: float) -> int:
    """How many hubs fit on a shell of this radius without sharing a halo.

    Inverts the lattice separation: n points are k*radius/sqrt(n) apart, so the largest n
    that still clears `gap` is (k*radius/gap)^2.
    """
    if gap <= 0:
        return 1
    return max(1, int((_LATTICE_SEPARATION_K * float(radius) / float(gap)) ** 2))


def peer_hub_shells(
    hub_count: int, gap: float, max_cluster_radius: float = 0.0
) -> list[tuple[float, int]]:
    """(radius, occupancy) per shell, inner first, covering `hub_count` hubs.

    The first shell is the compact one a quiet federation keeps sitting on; each further
    shell is one gap further out, so a hub never lands between two rings of somebody else.

    `max_cluster_radius` widens the innermost shell by the reach of a hub's own system: the
    clearance has to hold for the whole constellation, not for the sun at its centre. A
    provider hangs 2.2 out from its hub and can swing inward, which is how KOVA ended up
    3.4 from Platon's cave after the centres alone had been given four units of room.
    """
    remaining = max(1, int(hub_count))
    shells: list[tuple[float, int]] = []
    step = 0
    # The innermost shell clears whatever this deployment itself draws — see
    # local_ecosystem_radius(). Everything further out follows from it.
    inner = max(
        PEER_HUB_MIN_RADIUS,
        local_ecosystem_radius()
        + LOCAL_ECOSYSTEM_CLEARANCE
        + max(0.0, float(max_cluster_radius)),
    )
    while remaining > 0:
        radius = inner + step * gap
        take = min(remaining, _shell_capacity(radius, gap))
        shells.append((radius, take))
        remaining -= take
        step += 1
    return shells


def peer_hub_ring_radius(hub_count: int, max_cluster_radius: float = 0.0) -> float:
    """Outermost radius the hub ball reaches — what everything outside it must clear."""
    gap = peer_hub_gap(max_cluster_radius)
    return peer_hub_shells(hub_count, gap, max_cluster_radius)[-1][0]


def _shell_slot(index: int, count: int, radius: float) -> tuple[float, float, float]:
    """Unit-sphere slot `index` of `count`, as (x, y, z) scaled to `radius`.

    A Fibonacci lattice rather than a ring: it is the even spread on a sphere, and slots are
    handed out in order so the same federation always produces the same map.
    """
    n = max(1, int(count))
    i = max(0, int(index)) % n
    y = 1.0 - (2.0 * i + 1.0) / n
    r = math.sqrt(max(0.0, 1.0 - y * y))
    ang = _GOLDEN_RATIO_ANGLE * i + PEER_HUB_PHASE
    return (radius * r * math.cos(ang), radius * y, radius * r * math.sin(ang))


def peer_hub_position(
    index: int,
    total: int = 1,
    *,
    federation_pos: dict[str, float] | None = None,
    radius: float | None = None,
    max_cluster_radius: float = 0.0,
) -> dict[str, float]:
    """Slot for one discovered external hub, in the ball of hubs around our own.

    `radius` pins every hub to one shell — kept for callers that computed the radius
    themselves, and for a federation small enough to fit on the first shell anyway.
    """
    count = max(1, int(total))
    slot = max(0, int(index)) % count
    gap = peer_hub_gap(max_cluster_radius)
    if radius is not None:
        shells = [(float(radius), count)]
    else:
        shells = peer_hub_shells(count, gap, max_cluster_radius)
    for shell_radius, occupancy in shells:
        if slot < occupancy:
            x, y, z = _shell_slot(slot, occupancy, shell_radius)
            break
        slot -= occupancy
    else:  # pragma: no cover - the plan always covers `count`
        x, y, z = _shell_slot(0, 1, shells[-1][0])
    # `federation_pos` is retained as a compatibility/override argument, but the default
    # origin is the deployment's own hub.  Hanging somebody else's hub off our Federation
    # service put two independent galaxies in the same neighbourhood.
    base = federation_pos if federation_pos is not None else NODE_POSITIONS["hub"]
    return {
        "x": round(float(base["x"]) + x, 3),
        "y": round(float(base["y"]) + y, 3),
        "z": round(float(base["z"]) + z, 3),
    }


def peer_hub_child_position(
    hub_pos: dict[str, float], child_index: int, child_count: int
) -> dict[str, float]:
    """One of a hub's own peers, in orbit around THAT hub.

    Evenly spaced within its shell rather than hashed: a hash gives two of the same hub's four
    peers the same angle often enough to matter, and inside a one-unit orbit that reads as one
    planet. Shells keep a large ecosystem compact instead of letting one circle grow until it
    reaches the neighbouring hub.
    """
    index = max(0, int(child_index))
    count = max(1, int(child_count))
    shell = index // PEER_HUB_CHILDREN_PER_SHELL
    in_shell = index % PEER_HUB_CHILDREN_PER_SHELL
    remaining = count - shell * PEER_HUB_CHILDREN_PER_SHELL
    per_shell = max(1, min(PEER_HUB_CHILDREN_PER_SHELL, remaining))
    radius = PEER_HUB_CHILD_RADIUS + shell * PEER_HUB_CHILD_SHELL_STEP
    ang = (2.0 * math.pi * in_shell) / per_shell + (math.pi / per_shell) * (shell % 2)
    tier = PEER_HUB_CHILD_Y * (1 if index % 2 == 0 else -1)
    return {
        "x": round(float(hub_pos["x"]) + radius * math.cos(ang), 3),
        "y": round(float(hub_pos["y"]) + tier, 3),
        "z": round(float(hub_pos["z"]) + radius * math.sin(ang), 3),
    }


def pending_hub_ring_radius(
    hub_ring_radius: float, max_cluster_radius: float = 0.0
) -> float:
    """Outside every approved ring, whatever the approved rings grew to."""
    return max(
        PENDING_HUB_RADIUS_MIN,
        float(hub_ring_radius) + float(max_cluster_radius) + PENDING_HUB_MARGIN,
    )


def pending_hub_position(
    index: int,
    total: int = 1,
    *,
    federation_pos: dict[str, float] | None = None,
    radius: float | None = None,
) -> dict[str, float]:
    """Slot for an unapproved stranger — outside and below every approved ring."""
    count = max(1, int(total))
    ang = (2.0 * math.pi * (int(index) % count)) / count + PEER_HUB_PHASE + math.pi / count
    r = PENDING_HUB_RADIUS_MIN if radius is None else float(radius)
    base = federation_pos if federation_pos is not None else NODE_POSITIONS["hub"]
    return {
        "x": round(float(base["x"]) + r * math.cos(ang), 3),
        "y": round(float(base["y"]) + PENDING_HUB_Y_DROP, 3),
        "z": round(float(base["z"]) + r * math.sin(ang), 3),
    }


def federated_hub_position(
    index: int, *, federation_pos: dict[str, float] | None = None
) -> dict[str, float]:
    """Ring slot for the index-th UNI-spawned federated hub."""
    slot = (int(index) * FEDERATED_HUB_STRIDE) % FEDERATED_HUB_SLOTS
    ang = (2.0 * math.pi * slot) / FEDERATED_HUB_SLOTS
    base = federation_pos if federation_pos is not None else NODE_POSITIONS["federation"]
    ox, oy, oz = FEDERATED_HUB_OFFSET
    tilt = FEDERATED_HUB_Y_TILT if slot % 2 == 0 else -FEDERATED_HUB_Y_TILT
    return {
        "x": round(float(base["x"]) + ox + FEDERATED_HUB_RADIUS * math.cos(ang), 3),
        "y": round(float(base["y"]) + oy + tilt, 3),
        "z": round(float(base["z"]) + oz + FEDERATED_HUB_RADIUS * math.sin(ang), 3),
    }



# ── A place for a node nobody placed ─────────────────────────────────────────
# A hand-written coordinate is a STATEMENT: settlement sits on the hub→escrow line because
# that is what it does, WARDEN sits by ARGUS because it runs inside it, BASANOS sits away
# from MOMUS so the map does not imply one is a stage of the other. Those must stay
# hand-written. Everything else only needs somewhere sensible to stand — and until now the
# answer for an unplaced node was (0, 0, 0), i.e. inside the hub, invisible. The mesh
# agents had exactly that bug and got their own fix; this is the general one.
_AUTO_SHELL_RADIUS = 9.5
_AUTO_ATTEMPTS = 64  # golden-angle walk away from the derived point until it is clear
_AUTO_MIN_GAP = 2.6  # a shade above the static floor the separation test enforces


def _auto_point(angle: float, height: float) -> dict[str, float]:
    """A point on the shell from a CONTINUOUS angle and height.

    Continuous on purpose. A discrete slot table looks tidier and gives two nodes the same
    spot the moment their hashes agree modulo the table size — with 233 slots that happens
    among twenty-five ids about as often as not, and it did: `satellite-5` and
    `satellite-14` landed on the same coordinate. Here a clash needs the hashes themselves
    to agree.
    """
    y = max(-0.92, min(0.92, height))
    r = math.sqrt(max(0.0, 1.0 - y * y))
    return {
        "x": round(_AUTO_SHELL_RADIUS * r * math.cos(angle), 3),
        # Flattened: the map reads as a disc, and a full sphere would put nodes directly
        # above and below the hub where nothing else lives and labels overlap the corona.
        "y": round(_AUTO_SHELL_RADIUS * y * 0.55, 3),
        "z": round(_AUTO_SHELL_RADIUS * r * math.sin(angle), 3),
    }


def _auto_slot_is_clear(p: dict[str, float]) -> bool:
    for placed in NODE_POSITIONS.values():
        if _distance(p, placed) < _AUTO_MIN_GAP:
            return False
    total = 17
    for i in range(total):
        if _distance(p, ring_position(i, total)) < 3.0:
            return False
    cx, cy, cz = ORACLE_RING_CENTER
    if _distance(p, {"x": cx, "y": cy, "z": cz}) < ORACLE_RING_RADIUS + 1.5:
        return False
    gx, gy, gz = COMPETING_GALAXY_ANCHOR
    if _distance(p, {"x": gx, "y": gy, "z": gz}) < COMPETING_GALAXY_RADIUS + 4.0:
        return False
    return _distance(p, {"x": 0.0, "y": 0.0, "z": 0.0}) >= 4.0


def auto_node_position(node_id: str) -> dict[str, float]:
    """A stable, unoccupied place for a node with no hand-written coordinate.

    Derived from the id, so the same node stands in the same place across restarts and
    across the two maps — a node that jumps every deploy is a node nobody can point at.
    Collisions are avoided at the source rather than shuffled afterwards, and whatever is
    left over is still swept by space_map.enforce_spacing, which runs over everything.
    """
    digest = hashlib.sha256((node_id or "node").encode("utf-8")).hexdigest()
    angle = (int(digest[:8], 16) / 0xFFFFFFFF) * 2.0 * math.pi
    height = (int(digest[8:16], 16) / 0xFFFFFFFF) * 2.0 - 1.0
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for attempt in range(_AUTO_ATTEMPTS):
        candidate = _auto_point(angle + golden * attempt, height + 0.11 * attempt)
        if _auto_slot_is_clear(candidate):
            return candidate
    return _auto_point(angle, height)


def _distance(a: dict[str, float], b: dict[str, float]) -> float:
    return math.dist(
        (float(a["x"]), float(a["y"]), float(a["z"])),
        (float(b["x"]), float(b["y"]), float(b["z"])),
    )


def node_position(node_id: str, *, fallback: dict[str, float] | None = None) -> dict[str, float]:
    """Where a node stands: the operator's coordinate, the caller's, or one derived.

    The old last resort was the origin — which is the hub, so an unplaced node did not
    land somewhere unfortunate, it disappeared inside another one.
    """
    pos = NODE_POSITIONS.get(node_id)
    if pos is not None:
        return dict(pos)
    if fallback is not None:
        return dict(fallback)
    return auto_node_position(node_id)


def ring_position(index: int, total: int) -> dict[str, float]:
    """Place oracle nodes on a ring in the east sector."""
    ang = (2.0 * math.pi * index) / max(1, total)
    cx, cy, cz = ORACLE_RING_CENTER
    return {
        "x": round(cx + ORACLE_RING_RADIUS * math.cos(ang), 3),
        "y": round(cy + ORACLE_RING_Y_AMPLITUDE * math.sin(ang), 3),
        "z": round(cz + ORACLE_RING_RADIUS * 0.65 * math.sin(ang), 3),
    }


def federation_peer_position(node_id: str) -> dict[str, float]:
    h = sum(ord(ch) for ch in node_id) or 1
    ang = (h % 360) * math.pi / 180.0
    ax, ay, az = FEDERATION_ANCHOR
    return {
        "x": round(ax + FEDERATION_PEER_RADIUS * math.cos(ang), 3),
        "y": round(ay + ((h % 5) - 2) * 0.7, 3),
        "z": round(az + FEDERATION_PEER_RADIUS * math.sin(ang), 3),
    }
