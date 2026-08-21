"""UNI hub spawner — spawns must register and land on their own ring."""

from __future__ import annotations

import math
import sys
from pathlib import Path
from unittest.mock import patch

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from universe import EcosystemEntity  # noqa: E402
from universe_hub_spawner import HUB_NAMES, HubSpawner  # noqa: E402


def _dist(a: dict, b: dict) -> float:
    return math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"]))


class _FakeUniverse:
    """Just enough of VirtualUniverse for entity materialization."""

    def __init__(self):
        hub = EcosystemEntity("hub", "Hub", "core", "core")
        hub.position = {"x": 0.0, "y": 0.0, "z": 0.0}
        fed = EcosystemEntity("federation", "Federation", "network", "network")
        fed.position = {"x": -2.0, "y": 5.0, "z": 1.0}
        self.entities = {"hub": hub, "federation": fed}


def _spawn(spawner: HubSpawner, vu: _FakeUniverse, tick: int):
    """Run one spawn with the federation announce (network call) stubbed out."""
    with patch.object(HubSpawner, "_announce_to_federation", return_value=None):
        return spawner.tick(tick, vu)


class TestSpawnBookkeeping:
    def test_spawn_is_recorded(self):
        """Regression: the append targeted an attribute that was never created."""
        spawner = HubSpawner(interval_ticks=10)
        vu = _FakeUniverse()
        event = _spawn(spawner, vu, 100)
        assert event is not None
        assert event["type"] == "hub_spawned"
        assert len(spawner.spawned_hubs) == 1
        assert spawner.spawned_hubs[0]["name"] == event["name"]

    def test_federation_phase_gate_can_be_reached(self):
        spawner = HubSpawner(interval_ticks=10)
        vu = _FakeUniverse()
        for i in range(3):
            assert _spawn(spawner, vu, 100 + i * 10) is not None
        assert len(spawner.spawned_hubs) >= 3


class TestSpawnPlacement:
    def test_spawned_hub_is_not_inside_the_hub(self):
        spawner = HubSpawner(interval_ticks=10)
        vu = _FakeUniverse()
        _spawn(spawner, vu, 100)
        spawned = [e for eid, e in vu.entities.items() if eid.startswith("federated_")]
        assert len(spawned) == 1
        pos = spawned[0].position
        assert _dist(pos, vu.entities["hub"].position) >= 6.0

    def test_every_hub_name_gets_its_own_slot(self):
        vu = _FakeUniverse()
        spawner = HubSpawner(interval_ticks=10)
        for i, _ in enumerate(HUB_NAMES):
            assert _spawn(spawner, vu, 100 + i * 10) is not None
        positions = [
            e.position for eid, e in vu.entities.items() if eid.startswith("federated_")
        ]
        assert len(positions) == len(HUB_NAMES)
        for i in range(len(positions)):
            for j in range(i + 1, len(positions)):
                assert _dist(positions[i], positions[j]) >= 3.0

    def test_placement_is_stable_across_respawns(self):
        """Same hub name → same coordinates, instead of a fresh random offset."""
        first = _FakeUniverse()
        second = _FakeUniverse()
        with patch("universe_hub_spawner.random.choice", side_effect=lambda seq: seq[0]):
            _spawn(HubSpawner(interval_ticks=10), first, 100)
            _spawn(HubSpawner(interval_ticks=10), second, 500)
        eid = next(k for k in first.entities if k.startswith("federated_"))
        assert first.entities[eid].position == second.entities[eid].position
