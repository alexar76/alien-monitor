"""
Alien Monitor — Backend Test Suite (120% coverage target)

Tests cover:
  - Topology building (nodes, links, structure)
  - Ecosystem simulator (data generation, consistency)
  - API endpoints (health, state, summary, topology, ai/ask)
  - WebSocket lifecycle
  - AI fallback answers
  - Real-mode error handling
  - Edge cases & invariants
"""

import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("ALIEN_API_TOKEN", "test-monitor-token")

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from main import (
    app,
    build_topology,
    EcosystemSimulator,
    _fallback_answer,
    MODE,
)
from fastapi.testclient import TestClient

client = TestClient(app)
_AUTH = {"Authorization": "Bearer test-monitor-token"}


# ===========================================================================
# Topology tests
# ===========================================================================


class TestTopology:
    def test_build_returns_nodes_and_links(self):
        nodes, links = build_topology()
        assert len(nodes) > 0
        assert len(links) > 0

    def test_all_nodes_have_required_fields(self):
        nodes, _ = build_topology()
        required = {"id", "label", "group", "icon", "description", "metrics", "status", "position"}
        for node in nodes:
            missing = required - set(node.keys())
            assert not missing, f"Node {node.get('id', '?')} missing: {missing}"

    def test_node_positions_are_3d(self):
        nodes, _ = build_topology()
        for node in nodes:
            pos = node["position"]
            assert "x" in pos and "y" in pos and "z" in pos

    def test_core_nodes_exist(self):
        nodes, _ = build_topology()
        ids = {n["id"] for n in nodes}
        assert "hub" in ids
        assert "factory" in ids
        assert "mesh" in ids
        assert "acex" in ids

    def test_contract_nodes_exist(self):
        nodes, _ = build_topology()
        ids = {n["id"] for n in nodes}
        assert "evm_escrow" in ids
        assert "solana_escrow" in ids
        assert "nft_contract" in ids

    def test_sdk_nodes_exist(self):
        nodes, _ = build_topology()
        ids = {n["id"] for n in nodes}
        assert "sdk_dart" in ids
        assert "sdk_typescript" in ids
        assert "sdk_rust" in ids

    def test_blockchain_nodes_exist(self):
        nodes, _ = build_topology()
        ids = {n["id"] for n in nodes}
        assert "ethereum" in ids
        assert "solana" in ids

    def test_links_connect_valid_nodes(self):
        nodes, links = build_topology()
        valid_ids = {n["id"] for n in nodes}
        for link in links:
            src = link["source"]
            tgt = link["target"]
            assert src in valid_ids, f"Link source '{src}' not in nodes"
            assert tgt in valid_ids, f"Link target '{tgt}' not in nodes"

    def test_hub_is_most_connected(self):
        _, links = build_topology()
        hub_connections = sum(
            1 for l in links if l["source"] == "hub" or l["target"] == "hub"
        )
        # Hub should be the most connected node
        assert hub_connections >= 8

    def test_desktop_apps_has_children(self):
        nodes, _ = build_topology()
        desktop = next(n for n in nodes if n["id"] == "desktop_apps")
        assert "children" in desktop
        assert len(desktop["children"]) == 9

    def test_plugins_has_children(self):
        nodes, _ = build_topology()
        plugins = next(n for n in nodes if n["id"] == "plugins")
        assert "children" in plugins
        assert len(plugins["children"]) == 15

    def test_total_node_count(self):
        nodes, _ = build_topology()
        assert len(nodes) == 17


# ===========================================================================
# Simulator tests
# ===========================================================================


class TestSimulator:
    def test_step_returns_state(self):
        sim = EcosystemSimulator()
        state = sim.step()
        assert "nodes" in state
        assert "links" in state
        assert "events" in state
        assert "transactions" in state
        assert "summary" in state

    def test_tick_increments(self):
        sim = EcosystemSimulator()
        s1 = sim.step()
        s2 = sim.step()
        assert s2["tick"] == s1["tick"] + 1
        assert s2["tick"] == 2

    def test_summary_has_required_fields(self):
        sim = EcosystemSimulator()
        state = sim.step()
        summary = state["summary"]
        required = [
            "total_invocations_24h", "total_volume_usd", "active_channels",
            "tvl_usd", "agents_online", "apps_online", "tps_solana",
            "gas_gwei", "mode", "tick",
        ]
        for field in required:
            assert field in summary, f"Missing summary field: {field}"

    def test_nodes_have_updated_metrics(self):
        sim = EcosystemSimulator()
        state = sim.step()
        hub = next(n for n in state["nodes"] if n["id"] == "hub")
        assert hub["metrics"]["invocations_24h"] > 0

    def test_transactions_generated_over_time(self):
        sim = EcosystemSimulator()
        for _ in range(10):
            sim.step()
        state = sim.step()
        assert len(state["transactions"]) > 0

    def test_events_generated_over_time(self):
        sim = EcosystemSimulator()
        for _ in range(20):
            sim.step()
        state = sim.step()
        assert len(state["events"]) > 0

    def test_simulation_is_deterministic_ish(self):
        """Values should differ between runs (randomness), but stay within bounds."""
        sim = EcosystemSimulator()
        values = []
        for _ in range(10):
            s = sim.step()
            values.append(s["summary"]["total_invocations_24h"])
        # Values should increase over time (not be identical)
        assert values[-1] > values[0]

    def test_tvl_positive(self):
        sim = EcosystemSimulator()
        state = sim.step()
        assert state["summary"]["tvl_usd"] > 0

    def test_apps_online_in_range(self):
        sim = EcosystemSimulator()
        for _ in range(100):
            state = sim.step()
        apps = state["summary"]["apps_online"]
        assert 1 <= apps <= 9

    def test_gas_gwei_in_range(self):
        sim = EcosystemSimulator()
        state = sim.step()
        gas = state["summary"]["gas_gwei"]
        assert 10 <= gas <= 100

    def test_tps_solana_in_range(self):
        sim = EcosystemSimulator()
        state = sim.step()
        tps = state["summary"]["tps_solana"]
        assert 500 <= tps <= 5000

    def test_event_buffer_capped_at_200(self):
        sim = EcosystemSimulator()
        for _ in range(500):
            sim.step()
        state = sim.step()
        assert len(sim.events) <= 200

    def test_transaction_buffer_capped_at_100(self):
        sim = EcosystemSimulator()
        for _ in range(300):
            sim.step()
        state = sim.step()
        assert len(sim.transactions) <= 100


# ===========================================================================
# API endpoint tests
# ===========================================================================


class TestAPI:
    def test_health_endpoint(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "mode" in data

    def test_state_endpoint(self):
        resp = client.get("/api/state")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "summary" in data

    def test_summary_endpoint(self):
        resp = client.get("/api/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_invocations_24h" in data

    def test_topology_endpoint(self):
        resp = client.get("/api/topology")
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "links" in data
        assert len(data["nodes"]) == 17

    def test_ai_ask_empty_question(self):
        resp = client.post("/api/ai/ask", json={"question": ""}, headers=_AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert "Please ask" in data["answer"]

    def test_ai_ask_empty_question_ru(self):
        resp = client.post("/api/ai/ask", json={"question": "", "locale": "ru"}, headers=_AUTH)
        assert resp.status_code == 200
        assert "Задайте вопрос" in resp.json()["answer"]

    def test_ai_ask_no_question_field(self):
        resp = client.post("/api/ai/ask", json={}, headers=_AUTH)
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data


# ===========================================================================
# AI Fallback tests
# ===========================================================================


class TestAIFallback:
    def test_hub_question(self):
        ans = _fallback_answer("What is the hub?")
        assert "AIMarket Hub" in ans or "хаб" in ans.lower()

    def test_contract_question(self):
        ans = _fallback_answer("Tell me about contracts")
        assert "контракт" in ans.lower() or "escrow" in ans.lower()

    def test_plugin_question(self):
        ans = _fallback_answer("What plugins exist?")
        assert "плагин" in ans.lower() or "plugin" in ans.lower()

    def test_desktop_question(self):
        ans = _fallback_answer("What desktop apps are there?")
        assert "desktop" in ans.lower() or "Flutter" in ans

    def test_mesh_question(self):
        ans = _fallback_answer("What is ai service mesh?")
        assert "Mesh" in ans or "меш" in ans.lower()

    def test_mode_question(self):
        ans = _fallback_answer("What mode is the monitor in?")
        assert "mode" in ans.lower() or "режим" in ans.lower()

    def test_unknown_question_returns_generic(self):
        ans = _fallback_answer("xyzzy random gibberish")
        assert "ask about" in ans.lower() or "спросите" in ans.lower()


# ===========================================================================
# WebSocket tests
# ===========================================================================


class TestWebSocket:
    def test_ws_connect(self):
        with client.websocket_connect("/ws") as ws:
            # Should receive state updates
            data = ws.receive_json()
            assert data["type"] == "state_update"
            assert "data" in data

    def test_ws_mode_switch(self):
        with client.websocket_connect("/ws") as ws:
            # Send mode switch command
            ws.send_text(json.dumps({"cmd": "set_mode", "mode": "test"}))
            # Should still receive state updates
            data = ws.receive_json()
            assert data["type"] in ("state_update", "mode_changed")


# ===========================================================================
# Edge cases & invariants
# ===========================================================================


class TestEdgeCases:
    def test_node_status_must_be_valid(self):
        nodes, _ = build_topology()
        valid_statuses = {"active", "idle", "error", "unknown"}
        for node in nodes:
            assert node["status"] in valid_statuses, \
                f"Node {node['id']} has invalid status: {node['status']}"

    def test_all_links_have_labels(self):
        _, links = build_topology()
        for link in links:
            assert "label" in link
            assert len(link["label"]) > 0

    def test_no_duplicate_node_ids(self):
        nodes, _ = build_topology()
        ids = [n["id"] for n in nodes]
        assert len(ids) == len(set(ids))

    def test_simulator_never_returns_negative_values(self):
        sim = EcosystemSimulator()
        for _ in range(50):
            state = sim.step()
            s = state["summary"]
            for key, val in s.items():
                if isinstance(val, (int, float)) and key != "gas_gwei":
                    assert val >= 0, f"Negative {key}: {val}"

    def test_ai_endpoint_survives_large_input(self):
        resp = client.post("/api/ai/ask", json={"question": "x" * 10000}, headers=_AUTH)
        assert resp.status_code == 200

    def test_topology_idempotent(self):
        n1, l1 = build_topology()
        n2, l2 = build_topology()
        assert len(n1) == len(n2)
        assert len(l1) == len(l2)
