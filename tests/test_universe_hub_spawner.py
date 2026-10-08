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


class TestSpawnHonesty:
    """A spawned hub is a FIXTURE, and its node must say so instead of looking polled."""

    def _entity(self):
        vu = _FakeUniverse()
        _spawn(HubSpawner(interval_ticks=10), vu, 100)
        eid = next(k for k in vu.entities if k.startswith("federated_"))
        return vu.entities[eid]

    def test_entity_is_flagged_simulated(self):
        entity = self._entity()
        assert entity.simulated is True
        assert entity.simulated_note
        node = entity.to_node()
        assert node["simulated"] is True
        assert node["simulated_note"] == entity.simulated_note

    def test_no_address_is_advertised(self):
        """Regression: the card printed `http://127.0.0.1:908x` as an internal address.

        Nothing listens on those ports — the announce URL exists only to exercise the real
        hub's federation path — so the entity carries no address at all.
        """
        entity = self._entity()
        assert entity.url is None
        node = entity.to_node()
        assert not node.get("url")
        assert not node.get("url_internal")
        assert not node.get("source_url")

    def test_metrics_carry_no_literals(self):
        """Regression: `peers: 1` and `invocations_24h: 0` were hardcoded, forever.

        `peers` also fed the reputation graph's activity term, so an invented hub earned
        trust from a number nobody measured.
        """
        entity = self._entity()
        assert "peers" not in entity.metrics
        assert "invocations_24h" not in entity.metrics
        # The declared capability count stays: it is the length of the announced list,
        # which is 3 for a themed name and 1 for the generic fallback — never a literal.
        assert list(entity.metrics) == ["capabilities"]
        assert entity.metrics["capabilities"] >= 1

    def test_a_real_entity_is_not_flagged(self):
        """The flag is opt-in — a polled component must not inherit it."""
        node = EcosystemEntity("hub", "Hub", "core", "core").to_node()
        assert "simulated" not in node
        assert "simulated_note" not in node


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
