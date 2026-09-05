"""Hub affiliation stamps every monitor node with its owning federation Hub."""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from hub_affiliation import apply_hub_affiliation  # noqa: E402


def test_hub_node_url_is_rewritten_to_public_edge():
    nodes = [
        {"id": "hub", "label": "AIMarket Hub", "url": "http://127.0.0.1:9083"},
    ]
    apply_hub_affiliation(nodes, primary_hub_url="https://modelmarket.dev")
    assert nodes[0]["url"] == "https://modelmarket.dev"
    assert nodes[0]["hub"]["url"] == "https://modelmarket.dev"


def test_primary_nodes_belong_to_aimarket_hub():
    nodes = [
        {"id": "hub", "label": "AIMarket Hub", "url": "https://modelmarket.dev"},
        {"id": "factory", "label": "AI-Factory"},
        {"id": "gaia", "label": "GAIA", "url": "https://iot.modelmarket.dev"},
    ]
    apply_hub_affiliation(nodes, primary_hub_url="https://modelmarket.dev")
    assert nodes[0]["hub"]["id"] == "hub"
    assert nodes[0]["hub"]["url"] == "https://modelmarket.dev"
    assert nodes[1]["hub"]["id"] == "hub"
    assert nodes[1]["hub"]["label"] == "AIMarket Hub"
    assert nodes[2]["hub"]["id"] == "hub"


def test_hub_public_url_defaults_to_modelmarket_not_loopback(monkeypatch):
    from hub_affiliation import hub_public_url

    monkeypatch.delenv("ALIEN_MODE", raising=False)
    monkeypatch.delenv("ALIEN_UNI_HUB_URL", raising=False)
    monkeypatch.delenv("ALIEN_PUBLIC_HUB_URL", raising=False)
    monkeypatch.delenv("HUB_PUBLIC_URL", raising=False)
    monkeypatch.delenv("AIMARKET_PUBLIC_HUB_URL", raising=False)
    monkeypatch.setenv("HUB_URL", "http://127.0.0.1:9083")
    assert hub_public_url() == "https://modelmarket.dev"
    assert ":9083" not in hub_public_url()
    assert "127.0.0.1" not in hub_public_url()


def test_universe_card_uses_the_bubble_hub_not_the_live_one(monkeypatch):
    """A UNI card that links to modelmarket.dev is how bubble dollars get read as revenue."""
    from hub_affiliation import hub_public_url

    monkeypatch.setenv("ALIEN_MODE", "universe")
    monkeypatch.setenv("ALIEN_UNI_HUB_URL", "https://uni.example.dev")
    monkeypatch.setenv("ALIEN_PUBLIC_HUB_URL", "https://modelmarket.dev")
    assert hub_public_url() == "https://uni.example.dev"


def test_live_card_never_inherits_the_bubble_hub(monkeypatch):
    from hub_affiliation import hub_public_url

    monkeypatch.setenv("ALIEN_MODE", "real")
    monkeypatch.setenv("ALIEN_UNI_HUB_URL", "https://uni.example.dev")
    monkeypatch.setenv("ALIEN_PUBLIC_HUB_URL", "https://modelmarket.dev")
    assert hub_public_url() == "https://modelmarket.dev"


def test_affiliation_defaults_away_from_docker_api_url(monkeypatch):
    """Cards must not inherit HUB_URL=127.0.0.1:9083 when public edge is unset."""
    from hub_affiliation import apply_hub_affiliation

    monkeypatch.delenv("ALIEN_MODE", raising=False)
    monkeypatch.delenv("ALIEN_UNI_HUB_URL", raising=False)
    monkeypatch.delenv("ALIEN_PUBLIC_HUB_URL", raising=False)
    monkeypatch.delenv("HUB_PUBLIC_URL", raising=False)
    monkeypatch.delenv("AIMARKET_PUBLIC_HUB_URL", raising=False)
    nodes = [{"id": "factory", "label": "AI-Factory"}]
    apply_hub_affiliation(nodes)  # primary_hub_url omitted → hub_public_url()
    assert nodes[0]["hub"]["url"] == "https://modelmarket.dev"


def test_competing_galaxy_affiliation():
    nodes = [
        {"id": "competing_hub", "label": "Competing Lab Hub", "url": "https://hunt.modelmarket.dev", "galaxy": "competing"},
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
    assert "127.0.0.1" not in nodes[3]["hub"].get("url", "")
    assert "hunt.modelmarket.dev" in nodes[3]["hub"].get("url", "")


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


def test_uni_layer_polls_the_bubble_not_live_loopback(monkeypatch):
    """UNI header numbers used to be the live hub's 24h stats because HUB_URL is :9083."""
    import universe_layers as ul

    monkeypatch.setenv("HUB_URL", "http://127.0.0.1:9083")
    monkeypatch.delenv("ALIEN_UNIVERSE_HUB_URL", raising=False)
    monkeypatch.setenv("ALIEN_UNI_HUB_URL", "https://uni.example.dev")
    assert ul.layer_urls()["hub"] == "https://uni.example.dev"


def test_explicit_universe_hub_url_wins(monkeypatch):
    import universe_layers as ul

    monkeypatch.setenv("ALIEN_UNIVERSE_HUB_URL", "http://127.0.0.1:9183")
    monkeypatch.setenv("ALIEN_UNI_HUB_URL", "https://uni.example.dev")
    monkeypatch.setenv("HUB_URL", "http://127.0.0.1:9083")
    assert ul.layer_urls()["hub"] == "http://127.0.0.1:9183"
