"""Hub affiliation stamps every monitor node with its owning federation Hub."""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from hub_affiliation import apply_hub_affiliation  # noqa: E402


def test_primary_nodes_belong_to_aimarket_hub():
    nodes = [
        {"id": "hub", "label": "AIMarket Hub", "url": "https://modelmarket.dev"},
        {"id": "factory", "label": "AI-Factory"},
        {"id": "gaia", "label": "GAIA", "url": "https://iot.modelmarket.dev"},
    ]
    apply_hub_affiliation(nodes, primary_hub_url="https://modelmarket.dev")
    assert nodes[0]["hub"]["id"] == "hub"
    assert nodes[1]["hub"]["id"] == "hub"
    assert nodes[1]["hub"]["label"] == "AIMarket Hub"
    assert nodes[2]["hub"]["id"] == "hub"


def test_competing_galaxy_affiliation():
    nodes = [
        {"id": "competing_hub", "label": "Competing Lab Hub", "url": "http://hunt.modelmarket.dev:9083", "galaxy": "competing"},
        {"id": "signal_hunt_hub", "label": "Signal Hunt Hub", "url": "https://hunt.modelmarket.dev", "galaxy": "competing"},
        {"id": "signal_hunt", "label": "Signal Hunt", "url": "https://hunt.modelmarket.dev", "galaxy": "competing"},
        {"id": "use_cases", "label": "Use Cases Portal", "url": "https://use.modelmarket.dev", "galaxy": "competing"},
    ]
    apply_hub_affiliation(nodes, primary_hub_url="https://modelmarket.dev")
    assert nodes[0]["hub"]["id"] == "competing_hub"
    assert nodes[1]["hub"]["id"] == "signal_hunt_hub"
    assert nodes[2]["hub"]["id"] == "signal_hunt_hub"
    assert nodes[2]["hub"]["label"] == "Signal Hunt Hub"
    assert nodes[3]["hub"]["id"] == "competing_hub"


def test_discovered_peer_is_its_own_hub():
    nodes = [
        {
            "id": "peer_oracles",
            "label": "Oracle Family",
            "url": "https://oracles.modelmarket.dev/family",
            "discovered": True,
        }
    ]
    apply_hub_affiliation(nodes, primary_hub_url="https://modelmarket.dev")
    assert nodes[0]["hub"]["id"] == "peer_oracles"
    assert nodes[0]["hub"]["url"] == "https://oracles.modelmarket.dev/family"
