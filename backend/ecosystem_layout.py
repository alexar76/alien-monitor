"""Shared 3D anchors for the Alien Monitor ecosystem graph.

Keeps static nodes and the oracle ring in separate sectors so pulsing
coronas do not overlap (e.g. Colony vs Desktop Apps).
"""

from __future__ import annotations

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

# ~1.3× baseline spacing — hub stays at origin
NODE_POSITIONS: dict[str, dict[str, float]] = {
    "hub": {"x": 0.0, "y": 0.0, "z": 0.0},
    "factory": {"x": 5.0, "y": 2.5, "z": -2.5},
    "mesh": {"x": -5.0, "y": -1.5, "z": 2.5},
    "acex": {"x": 2.5, "y": -4.0, "z": 5.0},
    "evm_escrow": {"x": 5.5, "y": 4.5, "z": -2.5},
    "solana_escrow": {"x": 4.5, "y": -3.5, "z": -5.5},
    "nft_contract": {"x": 6.5, "y": 0.5, "z": -5.0},
    "desktop_apps": {"x": -7.5, "y": 5.5, "z": -7.0},
    "plugins": {"x": 0.0, "y": -6.5, "z": -4.0},
    # Publish-time trust gate: close to Hub, but outside its corona and clear of
    # Factory/contract nodes.  The links read candidate → audit → admission.
    "themis": {"x": 0.0, "y": 4.0, "z": -4.0},
    "sdk_dart": {"x": -6.5, "y": 1.5, "z": 6.5},
    "sdk_typescript": {"x": -7.5, "y": -1.5, "z": 5.0},
    "sdk_rust": {"x": -6.5, "y": 2.5, "z": -6.5},
    "federation": {"x": FEDERATION_ANCHOR[0], "y": FEDERATION_ANCHOR[1], "z": FEDERATION_ANCHOR[2]},
    "widget": {"x": -5.0, "y": 7.0, "z": -4.5},
    "ethereum": {"x": 3.5, "y": 6.5, "z": 5.5},
    "solana": {"x": 3.5, "y": -5.5, "z": 6.0},
    "cli": {"x": -6.5, "y": -5.5, "z": 6.5},
    "argus": {"x": -8.0, "y": 2.5, "z": 2.0},
    # The forge sits between the hub whose catalogue it reads and the factory whose
    # pipeline executor it submits to — the two edges that describe what it is. Nearest
    # neighbour 4.95, oracle ring 5.44, both above the 4.8 the separation tests enforce.
    "hephaestus": {"x": 4.5, "y": -2.0, "z": -0.5},
    # Agents the factory itself built and shipped. They sit between the factory that
    # produced them (5.0, 2.5, -2.5) and ARGUS, the reference agent they behave like —
    # demand side, not core service. Nearest neighbour ≥4.8, clear of the oracle ring.
    "factory_agents": {"x": -2.5, "y": 4.0, "z": 1.0},
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
    "signal_hunt_hub": {
        "x": COMPETING_GALAXY_ANCHOR[0] + 3.0,
        "y": COMPETING_GALAXY_ANCHOR[1] + 1.5,
        "z": COMPETING_GALAXY_ANCHOR[2] - 2.5,
    },
    # Game / app surface — separate ball, orbits its own Hub.
    "signal_hunt": {
        "x": COMPETING_GALAXY_ANCHOR[0] + 5.4,
        "y": COMPETING_GALAXY_ANCHOR[1] + 2.4,
        "z": COMPETING_GALAXY_ANCHOR[2] - 4.2,
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


def node_position(node_id: str, *, fallback: dict[str, float] | None = None) -> dict[str, float]:
    pos = NODE_POSITIONS.get(node_id)
    if pos is not None:
        return dict(pos)
    if fallback is not None:
        return dict(fallback)
    return {"x": 0.0, "y": 0.0, "z": 0.0}


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
