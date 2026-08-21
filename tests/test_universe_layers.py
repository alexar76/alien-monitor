"""Tests for UNI mode live layer polling."""

import math
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from universe import EcosystemEntity
from universe_layers import (
    apply_layers_to_entities,
    build_universe_summary,
    sync_agent_entities,
)


def _dist(a: dict, b: dict) -> float:
    return math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"]))


class TestApplyLayers:
    def test_hub_mesh_factory_from_live_data(self):
        entities = {
            "hub": EcosystemEntity("hub", "Hub", "core", "core"),
            "mesh": EcosystemEntity("mesh", "Mesh", "core", "core"),
            "factory": EcosystemEntity("factory", "Factory", "core", "core"),
            "ethereum": EcosystemEntity("ethereum", "EVM", "chain", "chain"),
        }
        layers = {
            "hub_hints": {"invocations_24h": 42, "channels_open": 3, "capabilities": 15},
            "mesh": {"agents": 5, "tasks": 10, "activity": 2},
            "factory": {"status": "ok"},
            "prometheus": {"data": {"result": [{"value": [None, "25"]}]}},
            "chain": {
                "evm": {"connected": True, "chain_id": 31337, "block": 100, "gas_gwei": 1.2, "rpc": "http://127.0.0.1:8545"},
            },
        }
        apply_layers_to_entities(entities, layers)
        assert entities["hub"].status == "active"
        assert entities["hub"].metrics["invocations_24h"] == 42
        assert entities["mesh"].metrics["agents"] == 5
        assert entities["factory"].metrics["tasks_done"] == 25
        assert entities["ethereum"].metrics["block"] == 100


class TestSyncAgents:
    def test_replaces_agent_placeholders(self):
        entities = {
            "hub": EcosystemEntity("hub", "Hub", "core", "core"),
            "agent_old": EcosystemEntity("agent_old", "Old", "agent", "agent"),
        }
        registry: list[dict] = []
        agents = [{"id": "a1", "name": "Agent One", "verified": True, "invocations": 7}]
        sync_agent_entities(entities, agents, registry)
        assert "agent_old" not in entities
        assert any(k.startswith("agent_") for k in entities)
        assert len(registry) == 1
        assert registry[0]["name"] == "Agent One"

    def test_agents_orbit_the_mesh_not_the_hub(self):
        """They used to keep the default (0,0,0) and render inside the hub sphere."""
        mesh = EcosystemEntity("mesh", "Mesh", "core", "core")
        mesh.position = {"x": -4.0, "y": -1.0, "z": 2.0}
        entities = {
            "hub": EcosystemEntity("hub", "Hub", "core", "core"),
            "mesh": mesh,
        }
        agents = [
            {"id": "a1", "name": "Research Scout"},
            {"id": "a2", "name": "Oracle Relay"},
            {"id": "a3", "name": "Escrow Notary"},
        ]
        sync_agent_entities(entities, agents, [])
        placed = [e for eid, e in entities.items() if eid.startswith("agent_")]
        assert len(placed) == 3
        seen: set[tuple[float, float, float]] = set()
        for ent in placed:
            pos = ent.position
            assert (pos["x"], pos["y"], pos["z"]) != (0.0, 0.0, 0.0)
            assert ent.parent_id == "mesh"
            # Closer to its registrar than to the hub it used to sit on.
            to_mesh = _dist(pos, mesh.position)
            to_hub = _dist(pos, entities["hub"].position)
            assert to_mesh < to_hub
            assert to_mesh >= 2.0
            seen.add((pos["x"], pos["y"], pos["z"]))
        assert len(seen) == 3

    def test_agent_keeps_its_slot_when_the_swarm_grows(self):
        mesh = EcosystemEntity("mesh", "Mesh", "core", "core")
        mesh.position = {"x": -4.0, "y": -1.0, "z": 2.0}
        first = [{"id": "a1", "name": "One"}]
        entities = {"mesh": mesh}
        sync_agent_entities(entities, first, [])
        before = dict(entities["agent_a1"].position)
        sync_agent_entities(entities, first + [{"id": "a2", "name": "Two"}], [])
        assert entities["agent_a1"].position == before


class TestUniverseSummary:
    def test_summary_mode_is_universe(self):
        summary = build_universe_summary(
            tick=1,
            layers={"hub_hints": {}, "chain": {"evm": {"connected": True}}},
            agents_count=2,
            products_count=1,
            onchain_tx_count=3,
        )
        assert summary["mode"] == "universe"
        assert summary["agents_online"] == 2
        assert summary["blockchain_ready"] is True
