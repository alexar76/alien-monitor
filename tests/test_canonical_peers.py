"""Hub-discovered first-party satellites must not mint a second (violet) planet."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
_REPO = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from canonical_peers import _map_node_ids, canonical_node_id_for_peer  # noqa: E402
from oracle_family import merge_discovered_peers, oracle_node_id  # noqa: E402

_SEEDS = _REPO / "aimarket-hub" / "aimarket_hub" / "federation_seeds.json"



def test_momus_hub_seed_maps_to_canonical_security_node():
    peer = {
        "id": "momus-adversarial-audit-satellite",
        "label": "MOMUS — adversarial-audit satellite",
        "url": "https://momus.modelmarket.dev",
        "description": "Runtime red team",
        "group": "oracle",
    }
    assert canonical_node_id_for_peer(peer) == "momus"


def test_momus_treasury_path_is_not_the_red_team_node():
    peer = {
        "id": "treasury",
        "label": "Treasury",
        "url": "https://momus.modelmarket.dev/treasury",
    }
    assert canonical_node_id_for_peer(peer) == "treasury"


def test_gates_stay_distinct_nodes():
    """THEMIS / MOMUS / Treasury never collapse into each other or into an oracle."""
    assert canonical_node_id_for_peer({
        "url": "https://themis.modelmarket.dev",
        "label": "THEMIS supply-chain admission auditor",
    }) == "themis"
    assert canonical_node_id_for_peer({
        "url": "https://momus.modelmarket.dev",
        "label": "MOMUS",
    }) == "momus"
    assert canonical_node_id_for_peer({
        "url": "https://momus.modelmarket.dev/#treasury",
        "label": "Treasury",
    }) == "treasury"
    ids = {
        canonical_node_id_for_peer({"url": "https://themis.modelmarket.dev"}),
        canonical_node_id_for_peer({"url": "https://momus.modelmarket.dev"}),
        canonical_node_id_for_peer({"url": "https://momus.modelmarket.dev/treasury"}),
    }
    assert ids == {"themis", "momus", "treasury"}


def test_every_committed_hub_seed_folds_onto_a_map_node():
    """No hand-written seed→node table here either.

    The seed file carries the operator's own `id` for each entry, and the map is the list
    of nodes that exist. Every seed must land on one of them — and the assertion holds for
    a seed added tomorrow, which a transcribed table could never do (this test broke the
    day four new seeds were committed, which is exactly the failure mode being removed).
    """
    seeds = json.loads(_SEEDS.read_text(encoding="utf-8"))["seeds"]
    assert seeds, "federation_seeds.json must list the live peers"
    known = _map_node_ids()

    for seed in seeds:
        base = str(seed["well_known_url"]).rsplit("/.well-known/", 1)[0]
        declared = str(seed.get("id") or "").strip()
        assert declared, f"seed {seed['name']!r} has no operator id"

        peer = {"id": declared, "label": seed["name"], "url": base,
                "description": seed.get("note", "")}
        nid = canonical_node_id_for_peer(peer)
        assert nid, f"hub seed {seed['name']!r} ({base}) has no canonical map node"
        assert nid in known, f"{seed['name']!r} folds onto {nid!r}, which the map never draws"

        # And with the hub's answer attached — which is how it arrives in production — the
        # fold is the operator's id whenever the map has that node.
        answered = canonical_node_id_for_peer({**peer, "canonical_id": declared})
        assert answered == (declared if declared in known else nid)


def test_remaining_first_party_hosts_fold():
    cases = {
        "https://skopos.modelmarket.dev": "skopos",
        "https://metis.modelmarket.dev": "metis",
        "https://logos.modelmarket.dev": "logos",
        "https://lottery.modelmarket.dev": "lottery",
        "https://gaia.modelmarket.dev": "gaia",
        "https://use.modelmarket.dev": "use_cases",
        "https://modelmarket.dev/studio": "hephaestus",
        "https://modeldev.modelmarket.dev/bridges/": "bridges",
        "https://basanos.modelmarket.dev": "basanos",
        "https://atlas.modelmarket.dev": "atlas",
        "https://iot.modelmarket.dev": "gaia",
    }
    for url, expected in cases.items():
        assert canonical_node_id_for_peer({"url": url, "label": expected}) == expected, url


def test_hephaestus_studio_is_not_the_aestus_oracle():
    """Family slug matching is substring-y; 'hephaestus' contains 'aestus'."""
    assert canonical_node_id_for_peer({
        "url": "https://modelmarket.dev/studio",
        "label": "HEPHAESTUS",
        "id": "hephaestus-studio",
    }) == "hephaestus"


def test_primary_hub_folds_onto_the_seeded_sun():
    """Our own Hub is already the centre. Discovery must not mint a twin."""
    assert canonical_node_id_for_peer({
        "url": "https://modelmarket.dev",
        "label": "AIMarket Hub",
    }) == "hub"


def test_factory_storefront_is_the_one_factory_sun():
    """Well-known name Magic AI-Factory AI Market is the factory ball, not a second hub."""
    assert canonical_node_id_for_peer({
        "url": "https://magic-ai-factory.com",
        "label": "Magic AI-Factory AI Market",
        "id": "magic-ai-factory-ai-market",
    }) == "factory"
    assert canonical_node_id_for_peer({
        "url": "https://magic-ai-factory.com/agents",
        "label": "Factory agents",
    }) == "factory_agents"
    assert canonical_node_id_for_peer({
        "url": "https://magic-ai-factory.com/product/prod-abc",
        "label": "A product",
    }) is None


def test_signal_hunt_and_competing_lab_fold_onto_seeded_suns():
    """Same box, two processes: HTTPS hunt vs :9083. Hyphen ids are discovery slugs."""
    assert canonical_node_id_for_peer({
        "url": "https://hunt.modelmarket.dev",
        "label": "Signal Hunt Hub",
        "id": "signal-hunt-hub",
    }) == "signal_hunt_hub"
    assert canonical_node_id_for_peer({
        "url": "http://hunt.modelmarket.dev:9083",
        "label": "Competing Lab Hub",
        "id": "competing-lab-hub",
    }) == "competing_hub"
    assert canonical_node_id_for_peer({
        "url": "http://108.165.32.182:9083",
        "label": "Competing Lab Hub",
        "id": "competing-lab-hub",
    }) == "competing_hub"
    assert canonical_node_id_for_peer({
        "url": "https://hub.modelmarket.dev",
        "label": "Competing Lab Hub",
    }) == "competing_hub"


def test_foreign_hub_named_like_ours_is_not_folded():
    """A stranger that merely *calls* itself Signal Hunt Hub stays a discovered sun."""
    assert canonical_node_id_for_peer({
        "id": "signal-hunt-hub",
        "label": "Signal Hunt Hub",
        "url": "https://evil.example",
    }) is None


def test_foreign_peer_named_momus_is_not_folded():
    """A stranger that merely *calls* itself MOMUS stays a discovered node."""
    assert canonical_node_id_for_peer({
        "id": "impostor",
        "label": "MOMUS — adversarial-audit satellite",
        "url": "https://evil.example/momus",
    }) is None


def test_family_oracle_still_maps_through_canonical():
    peer = {
        "id": "platon-shadow-oracle",
        "label": "Platon Shadow Oracle",
        "url": "https://oracles.modelmarket.dev",
    }
    assert canonical_node_id_for_peer(peer) == oracle_node_id("platon")


def test_merge_does_not_append_violet_momus_clone():
    nodes = [
        {"id": "momus", "label": "MOMUS", "group": "security", "icon": "eye",
         "metrics": {"findings": 2}, "position": {"x": 0, "y": 0, "z": 0}},
        {"id": "themis", "label": "THEMIS", "group": "security", "icon": "shield",
         "metrics": {"audits_total": 4}, "position": {"x": 1, "y": 0, "z": 0}},
        {"id": "federation", "label": "Federation", "group": "network",
         "metrics": {}, "position": {"x": 0, "y": 0, "z": 0}},
    ]
    links: list[dict] = []
    disc = {
        "nodes": [
            {
                "id": "momus-adversarial-audit-satellite",
                "label": "MOMUS — adversarial-audit satellite",
                "url": "https://momus.modelmarket.dev",
                "group": "oracle",
                "icon": "oracle",
                "metrics": {"trust_score": 0.44, "capabilities": 7},
                "status": "idle",
                "position": {"x": -2, "y": 5, "z": 1},
            },
            {
                "id": "themis-supply-chain",
                "label": "THEMIS supply-chain admission auditor",
                "url": "https://themis.modelmarket.dev",
                "group": "oracle",
                "icon": "oracle",
                "metrics": {"trust_score": 0.9},
                "status": "idle",
                "position": {"x": -1, "y": 5, "z": 1},
            },
        ],
        "links": [
            {"source": "federation", "target": "momus-adversarial-audit-satellite",
             "label": "Federation peer"},
            {"source": "federation", "target": "themis-supply-chain",
             "label": "Federation peer"},
        ],
        "peer_count": 2,
    }
    merge_discovered_peers(nodes, links, disc)
    assert [n["id"] for n in nodes] == ["momus", "themis", "federation"]
    momus = nodes[0]
    themis = nodes[1]
    assert momus["group"] == "security" and momus["icon"] == "eye"
    assert themis["group"] == "security" and themis["icon"] == "shield"
    assert momus["metrics"]["findings"] == 2
    assert themis["metrics"]["audits_total"] == 4
    assert not any("oracle" == n.get("group") for n in nodes if n["id"] in {"momus", "themis"})
    assert not any(
        l.get("target") in {"momus-adversarial-audit-satellite", "themis-supply-chain"}
        for l in links
    )


def test_hyphen_hub_clones_fold_and_keep_their_moons():
    """Discovery used to mint signal-hunt-hub next to signal_hunt_hub."""
    from ecosystem_layout import node_position, peer_hub_child_position

    sun_pos = node_position("signal_hunt_hub")
    nodes = [
        {
            "id": "signal_hunt_hub",
            "label": "Signal Hunt Hub",
            "group": "network",
            "icon": "hub",
            "role": "hub",
            "metrics": {"peers": 0},
            "position": dict(sun_pos),
        },
        {
            "id": "competing_hub",
            "label": "Competing Lab Hub",
            "group": "network",
            "icon": "hub",
            "role": "hub",
            "metrics": {"peers": 0},
            "position": node_position("competing_hub"),
        },
        {"id": "federation", "label": "Federation", "group": "network",
         "metrics": {}, "position": {"x": 0, "y": 0, "z": 0}},
    ]
    links: list[dict] = [
        {"source": "federation", "target": "signal_hunt_hub", "label": "Federated peer"},
    ]
    moon = {
        "id": "fedchild:https://their-oracle.example",
        "label": "Their oracle",
        "group": "peer_hub_node",
        "url": "https://their-oracle.example",
        "parent_id": "signal-hunt-hub",
        "metrics": {},
        "status": "idle",
        "position": {"x": 99, "y": 99, "z": 99},
    }
    disc = {
        "nodes": [
            {
                "id": "signal-hunt-hub",
                "label": "Signal Hunt Hub",
                "url": "https://hunt.modelmarket.dev",
                "group": "peer_hub",
                "icon": "hub",
                "role": "hub",
                "metrics": {"peers": 3, "trust_score": 0.4},
                "status": "active",
                "position": {"x": -8, "y": 5, "z": 1},
            },
            {
                "id": "competing-lab-hub",
                "label": "Competing Lab Hub",
                "url": "http://hunt.modelmarket.dev:9083",
                "group": "peer_hub",
                "icon": "hub",
                "role": "hub",
                "metrics": {"peers": 2},
                "status": "active",
                "position": {"x": 8, "y": 5, "z": 1},
            },
            moon,
            {
                "id": "hub:stranger",
                "label": "Somebody Else's Hub",
                "url": "https://stranger.example",
                "group": "peer_hub",
                "icon": "hub",
                "role": "hub",
                "metrics": {"peers": 1},
                "status": "active",
                "position": {"x": 4, "y": 2, "z": -3},
            },
            {
                "id": "fedchild:https://stranger-moon.example",
                "label": "Stranger moon",
                "group": "peer_hub_node",
                "url": "https://stranger-moon.example",
                "parent_id": "hub:stranger",
                "metrics": {},
                "status": "idle",
                "position": {"x": 5, "y": 2, "z": -3},
            },
        ],
        "links": [
            {"source": "federation", "target": "signal-hunt-hub", "label": "Federation peer"},
            {"source": "signal-hunt-hub", "target": "fedchild:https://their-oracle.example",
             "label": "its peer"},
            {"source": "hub:stranger", "target": "fedchild:https://stranger-moon.example",
             "label": "its peer"},
        ],
        "peer_count": 2,
    }
    merge_discovered_peers(nodes, links, disc)
    ids = [n["id"] for n in nodes]
    assert ids.count("signal_hunt_hub") == 1
    assert "signal-hunt-hub" not in ids
    assert "competing-lab-hub" not in ids
    assert ids.count("competing_hub") == 1
    assert "hub:stranger" in ids
    assert "fedchild:https://their-oracle.example" in ids
    assert "fedchild:https://stranger-moon.example" in ids
    hunt = next(n for n in nodes if n["id"] == "signal_hunt_hub")
    assert hunt["metrics"]["peers"] == 3
    moon_node = next(n for n in nodes if n["id"].startswith("fedchild:https://their-oracle"))
    assert moon_node["parent_id"] == "signal_hunt_hub"
    assert moon_node["position"] == peer_hub_child_position(sun_pos, 0, 1)
    assert any(
        l.get("source") == "signal_hunt_hub"
        and l.get("target") == "fedchild:https://their-oracle.example"
        for l in links
    )
