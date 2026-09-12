"""THEMIS node wiring — permanent gate near Hub."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from themis_layers import (  # noqa: E402
    apply_themis_to_nodes,
    fill_themis_sim_node,
    themis_node_spec,
    themis_topology_links,
)


def test_node_spec_is_security_group_near_hub_contract():
    spec = themis_node_spec()
    assert spec["id"] == "themis"
    assert spec["group"] == "security"
    assert spec["links"]["github"].endswith("/themis")
    assert spec["links"]["landing"].endswith("/themis/")
    assert "tutorials/themis.en.md" in spec["links"]["tutorial"]
    assert "tutorial" in spec["links"]


def test_topology_links_cover_admission_trail():
    links = {(item["source"], item["target"]) for item in themis_topology_links()}
    assert ("factory", "themis") in links
    assert ("themis", "hub") in links
    assert ("themis", "metis") in links
    assert ("themis", "momus") in links


def test_sim_fill_never_claims_live_receipt():
    node = themis_node_spec()
    fill_themis_sim_node(node, tick=4)
    assert node["status"] == "active"
    assert node["themis_live"]["simulated"] is True
    assert node["themis_live"]["latest"]["decision"] in {"approve", "review", "reject"}


def test_apply_hub_telemetry_is_dossier_free_and_offline_without_summary():
    nodes = [themis_node_spec()]
    apply_themis_to_nodes(nodes, None)
    assert nodes[0]["status"] == "offline"
    assert "themis_live" not in nodes[0]
    assert nodes[0]["links"]["landing"].endswith("/themis/")
    assert nodes[0]["links"]["github"].endswith("/themis")

    apply_themis_to_nodes(
        nodes,
        {
            "summary": {
                "supply_chain_admission": {
                    "mode": "enforce",
                    "configured": True,
                    "total": 3,
                    "approved": 1,
                    "review": 1,
                    "rejected": 1,
                    "metis_pending": 1,
                    "latest": {
                        "decision": "review",
                        "score": 70,
                        "risk_tier": "medium",
                        "metis_status": "pending",
                        "capability_id": "invoice.read@v1",
                    },
                    "capability_id": "agent.security.supply-chain.audit@v1",
                }
            },
            "supply_chain_audits": [
                {
                    "audit_id": "a1",
                    "capability_id": "invoice.read@v1",
                    "publisher_id": "vendor",
                    "decision": "review",
                    "score": 70,
                    "metis": {"status": "pending"},
                }
            ],
        },
    )
    live = nodes[0]["themis_live"]
    assert live["simulated"] is False
    assert live["mode"] == "enforce"
    assert live["latest"]["decision"] == "review"
    assert live["recent"][0]["capability_id"] == "invoice.read@v1"
    assert "invoke_url" not in live["recent"][0]
    assert nodes[0]["metrics"]["review"] == 1
    assert nodes[0]["links"]["tutorial"].endswith("themis.en.md")


def test_universe_graph_fills_sim_when_hub_has_no_admission():
    from themis_layers import apply_themis_graph

    nodes = [{"id": "themis", "label": "THEMIS"}]
    apply_themis_graph(nodes, mode="universe", tick=2, hub_payload=None)
    assert nodes[0]["themis_live"]["simulated"] is True
    assert nodes[0]["links"]["landing"].endswith("/themis/")
    assert nodes[0]["status"] == "active"
