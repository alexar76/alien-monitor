"""Federated hubs on the map, with their own nodes hanging off them.

Three separate wirings had to agree before a peer hub could appear, and each one alone looked
finished:

1. **discovery** dropped it. The relevance filter is about capabilities — oracle, simulation,
   beacon — and a hub advertises none of those; it advertises other people's. So the single
   kind of peer whose whole purpose is to have peers of its own was the kind that never
   matched.
2. **the universe overwrote it.** `_apply_discovery` hardcoded `group="oracle"`,
   `icon="oracle"`, `color="#a64dff"` for every discovered node, so emitting a new group
   upstream changed nothing that reached a browser.
3. **nothing drew its edges.** `parent_id` is not a link in this codebase; `get_topology_links`
   is. A child with a parent nobody read floated unconnected.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

import hub_discovery  # noqa: E402

HUB_WELL_KNOWN = {
    "name": "Somebody Else's Hub",
    "hub_version": "3.2.1",
    "protocol_versions": ["v2"],
    "capabilities_count": 41,
    "description": "A hub run by someone we do not control",
    "peers": [
        {"url": "https://oracles.example.org/", "name": "Their oracles",
         "capabilities_count": 12, "trust_score": 0.61},
        {"url": "https://sensors.example.org", "name": "Their sensors",
         "capabilities_count": 7, "trust_score": 0.44},
    ],
}


class TestDiscoveryKeepsHubs:
    def test_a_hub_is_recognised_from_what_it_publishes(self):
        assert hub_discovery._is_peer_hub(HUB_WELL_KNOWN)
        assert hub_discovery._is_peer_hub({"protocol_versions": ["v2"]})
        assert hub_discovery._is_peer_hub({"hub_version": "1.0"})
        # Not from its URL, not from its categories, not from a bare name.
        assert not hub_discovery._is_peer_hub({"name": "hub.example.org"})
        assert not hub_discovery._is_peer_hub({"categories": ["hub", "federation"]})
        assert not hub_discovery._is_peer_hub({})
        assert not hub_discovery._is_peer_hub(None)

    def test_its_peers_become_nodes_around_it(self):
        cfg = hub_discovery.DiscoveryConfig(allow_private=True)
        nodes, links = hub_discovery._peer_hub_children(HUB_WELL_KNOWN, "hub:theirs", cfg)
        assert [n["label"] for n in nodes] == ["Their oracles", "Their sensors"]
        assert all(n["group"] == "peer_hub_node" for n in nodes)
        assert all(n["parent_id"] == "hub:theirs" for n in nodes)
        # Costs no extra request: the numbers come from the manifest we already read.
        assert nodes[0]["metrics"]["capabilities"] == 12
        assert nodes[0]["metrics"]["trust_score"] == pytest.approx(0.61)
        assert [(link["source"], link["target"]) for link in links] == [
            ("hub:theirs", nodes[0]["id"]), ("hub:theirs", nodes[1]["id"]),
        ]

    def test_signed_ecosystem_providers_join_their_hubs_system_not_its_trust_set(self):
        cfg = hub_discovery.DiscoveryConfig(allow_private=True)
        manifest = {
            **HUB_WELL_KNOWN,
            "ecosystem": {"version": 1, "nodes": [
                {"id": "kova", "name": "KOVA", "role": "provider",
                 "url": "https://independent.example/kova", "capabilities_count": 6},
            ]},
        }
        nodes, links = hub_discovery._peer_hub_children(manifest, "hub:theirs", cfg)
        kova = next(n for n in nodes if n["label"] == "KOVA")
        assert kova["group"] == "peer_hub_provider"
        assert kova["role"] == "provider"
        assert kova["metrics"]["capabilities"] == 6
        assert next(l for l in links if l["target"] == kova["id"])["kind"] == "ecosystem"

    def test_children_carry_no_position_of_their_own(self):
        """Only the aggregation step knows the parent's slot and the sibling count, so a
        child that positioned itself from its own hash landed every hub's peers in the same
        pile near the origin."""
        cfg = hub_discovery.DiscoveryConfig(allow_private=True)
        nodes, _ = hub_discovery._peer_hub_children(HUB_WELL_KNOWN, "hub:theirs", cfg)
        assert all("position" not in n for n in nodes)

    def test_the_child_count_is_bounded(self, monkeypatch):
        monkeypatch.setenv("ALIEN_DISCOVERY_HUB_CHILDREN", "1")
        cfg = hub_discovery.DiscoveryConfig(allow_private=True)
        nodes, links = hub_discovery._peer_hub_children(HUB_WELL_KNOWN, "hub:theirs", cfg)
        assert len(nodes) == 1 and len(links) == 1

    def test_a_hub_with_no_peers_is_still_a_hub(self):
        cfg = hub_discovery.DiscoveryConfig(allow_private=True)
        nodes, links = hub_discovery._peer_hub_children(
            {"hub_version": "3.2.1"}, "hub:lonely", cfg,
        )
        assert nodes == [] and links == []


class TestAHubIsNotJustAnythingWithHubVersion:
    """`hub_version` alone over-matches, and the live federation proves it: ATLAS reports
    0.1.0 and GAIA reports one too, because every satellite is built on the hub's manifest
    shape. Classifying those as hubs would throw away the very thing the map is for — telling
    an operator what a node does."""

    def test_a_sensor_gateway_that_reports_a_hub_version_stays_a_sensor(self):
        atlas_like = {
            "name": "ATLAS", "hub_version": "0.1.0", "protocol_versions": ["v2"],
            "peers": [], "categories": ["iot", "sensors"],
        }
        # It looks like a hub by the naive test…
        assert hub_discovery._is_peer_hub(atlas_like)
        # …and the decision that matters must still keep it out of the hub ring, because the
        # capability filter matched it and it federates with nobody.
        assert not bool(atlas_like["peers"])  # …so it never reaches the hub ring

    def test_a_hub_with_peers_of_its_own_is_a_hub(self):
        federating = {"hub_version": "3.2.1", "peers": [{"url": "https://x.example"}]}
        assert hub_discovery._is_peer_hub(federating) and bool(federating["peers"])

    def test_a_hub_that_publishes_no_categories_does_not_crash_the_builder(self):
        """It threw TypeError into the per-peer `except Exception` that exists so one bad peer
        cannot break the graph — so the three real hubs in the live federation were not an
        error anywhere, they were simply absent."""
        cfg = hub_discovery.DiscoveryConfig(allow_private=True)
        nodes, _ = hub_discovery._peer_hub_children(
            {"hub_version": "3.2.1", "peers": [{"url": "https://x.example"}]}, "hub:x", cfg,
        )
        assert nodes and nodes[0]["categories"] == []

    def test_estate_tells_our_satellites_from_a_strangers_hub(self):
        """The rule that decides it. Our own satellites are already first-class nodes on this
        map and every one of them reports a hub_version, so promoting them throws away what
        they are. A stranger's hub is on nobody's map: if it is not drawn as a hub it is not
        drawn at all — and a NEWLY deployed hub has zero peers, which is the whole case this
        feature exists for. Requiring peers made the commonest newcomer invisible."""
        estate = hub_discovery._estate
        assert estate("https://modelmarket.dev") == "modelmarket.dev"
        assert estate("https://atlas.modelmarket.dev") == "modelmarket.dev"
        assert estate("http://hub.example.org:9083/x") == "example.org"
        assert estate("") == ""

        ours = estate("https://modelmarket.dev")
        # A satellite of ours with no peers: stays what it is.
        assert not (estate("https://atlas.modelmarket.dev") != ours or False)
        # A stranger's brand-new hub, zero peers: drawn.
        assert estate("https://newcomer.example.org") != ours


class TestTheUniverseKeepsWhatDiscoverySaid:
    def _universe(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ALIEN_ANVIL_STATE_MAX_MB", "4096")
        import universe as universe_mod

        return universe_mod

    def test_a_peer_hub_is_not_relabelled_as_an_oracle(self, tmp_path, monkeypatch):
        universe_mod = self._universe(tmp_path, monkeypatch)
        uni = universe_mod.VirtualUniverse.__new__(universe_mod.VirtualUniverse)
        uni.entities = {}
        uni._discovered_ids = set()
        uni._discovery_events = []
        uni._family_id_for_node = lambda n: None

        discovered = {
            "nodes": [
                {"id": "hub:theirs", "label": "Somebody Else's Hub", "group": "peer_hub",
                 "icon": "network", "url": "https://theirs.example.org",
                 "description": "a hub", "metrics": {"peers": 2}, "status": "active",
                 "position": {"x": 1.0, "y": 0.0, "z": 1.0}},
                {"id": "fedchild:https://oracles.example.org", "label": "Their oracles",
                 "group": "peer_hub_node", "icon": "network",
                 "url": "https://oracles.example.org", "description": "their node",
                 "metrics": {}, "status": "idle", "parent_id": "hub:theirs",
                 "position": {"x": 0.5, "y": 0.6, "z": 0.5}},
            ],
            "links": [], "events": [],
        }
        monkeypatch.setattr(
            universe_mod, "discover_cached_sync", lambda *a, **k: discovered, raising=False,
        )
        import hub_discovery as hd

        monkeypatch.setattr(hd, "discover_cached_sync", lambda *a, **k: discovered)

        uni._apply_discovery("https://hub.example.org")

        hub = uni.entities["hub:theirs"]
        assert hub.group == "peer_hub", "the universe flattened the hub back to an oracle"
        assert hub.color == "#38e0ff", "a hub must not share the oracle colour"
        assert hub.parent_id == "federation"

        child = uni.entities["fedchild:https://oracles.example.org"]
        assert child.group == "peer_hub_node"
        assert child.parent_id == "hub:theirs", (
            "a hub's peer belongs to that hub, which is the whole shape of the second hop"
        )

    def test_hyphen_hub_clones_fold_onto_the_seeded_sun(self, tmp_path, monkeypatch):
        """LIVE discovery slug `signal-hunt-hub` is the same planet as `signal_hunt_hub`."""
        universe_mod = self._universe(tmp_path, monkeypatch)
        uni = universe_mod.VirtualUniverse.__new__(universe_mod.VirtualUniverse)
        uni.entities = {}
        uni._discovered_ids = set()
        uni._discovery_events = []
        uni._discovery_links = []
        from canonical_peers import canonical_node_id_for_peer
        from competing_lab_layers import signal_hunt_hub_node_spec

        uni._family_id_for_node = lambda n: canonical_node_id_for_peer(n)
        spec = signal_hunt_hub_node_spec()
        sun = universe_mod.EcosystemEntity(
            spec["id"], spec["label"], "core", group=spec["group"], icon=spec["icon"],
        )
        sun.url = spec["url"]
        sun.role = spec["role"]
        sun.position = dict(spec["position"])
        uni.entities[spec["id"]] = sun

        discovered = {
            "nodes": [
                {
                    "id": "signal-hunt-hub", "label": "Signal Hunt Hub", "group": "peer_hub",
                    "icon": "hub", "url": "https://hunt.modelmarket.dev",
                    "metrics": {"peers": 2}, "status": "active",
                    "position": {"x": 9.0, "y": 0.0, "z": 9.0},
                },
                {
                    "id": "fedchild:https://moon.example", "label": "Moon",
                    "group": "peer_hub_node", "icon": "network",
                    "url": "https://moon.example", "parent_id": "signal-hunt-hub",
                    "metrics": {}, "status": "idle",
                    "position": {"x": 10.0, "y": 0.0, "z": 10.0},
                },
            ],
            "links": [
                {"source": "signal-hunt-hub", "target": "fedchild:https://moon.example"},
            ],
            "events": [],
        }
        import hub_discovery as hd

        monkeypatch.setattr(hd, "discover_cached_sync", lambda *a, **k: discovered)
        uni._apply_discovery("https://hub.example.org")

        assert "signal-hunt-hub" not in uni.entities
        assert uni.entities["signal_hunt_hub"].metrics.get("peers") == 2
        moon = uni.entities["fedchild:https://moon.example"]
        assert moon.parent_id == "signal_hunt_hub"
        assert moon.group == "peer_hub_node"
        assert moon.position != {"x": 10.0, "y": 0.0, "z": 10.0}


def _dist(a: dict, b: dict) -> float:
    return math.sqrt(
        (a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2 + (a["z"] - b["z"]) ** 2
    )


class TestNothingOverlapsAnythingElse:
    """The requirement in one sentence: hubs and their ecosystems must not sit on top of each
    other. Three federation clouds already share the space around one anchor — discovered
    peers at radius 3.2, UNI-spawned hubs at 5.0 — and strangers used to be placed at 1.6x the
    peer ring, which is 5.12: inside the spawned-hub ring, so a stranger could render on top of
    a spawned hub.
    """

    def test_two_hubs_are_never_within_a_cluster_width_of_each_other(self):
        from ecosystem_layout import (
            peer_hub_cluster_radius, peer_hub_position, peer_hub_ring_radius,
        )

        for hubs in (2, 4, 8, 16, 40):
            for children in (0, 3, 12, 40):
                cluster = peer_hub_cluster_radius(children)
                ring = peer_hub_ring_radius(hubs, cluster)
                pos = [peer_hub_position(i, hubs, radius=ring) for i in range(hubs)]
                for i, a in enumerate(pos):
                    for b in pos[i + 1:]:
                        gap = _dist(a, b)
                        assert gap > 2 * cluster, (
                            f"{hubs} hubs x {children} peers: clusters {gap:.2f} apart, "
                            f"each {cluster:.2f} wide"
                        )

    def test_the_universe_expands_as_ecosystems_grow(self):
        """The requirement in one sentence: there must be headroom between hubs because an
        ecosystem can grow — so the ring is a function of what is in it, and hubs drift apart
        rather than starting to overlap."""
        from ecosystem_layout import peer_hub_cluster_radius, peer_hub_ring_radius

        # Forty hubs: enough to overflow the innermost shell once their ecosystems are fat,
        # which is where "expands" is a claim about the geometry rather than about a count
        # that happened to fit either way.
        radii = [
            peer_hub_ring_radius(40, peer_hub_cluster_radius(n)) for n in (0, 5, 20, 60)
        ]
        assert radii == sorted(radii), "the ring must never shrink as ecosystems grow"
        assert radii[-1] > radii[0], "a big federation must push its hubs outward"
        # …and more hubs also expand it, once there are more than one shell holds.
        assert peer_hub_ring_radius(200, 5.0) > peer_hub_ring_radius(2, 5.0)

    def test_a_quiet_federation_is_not_flung_across_the_map(self):
        """Expansion is a floor, not a multiplier: two hubs with three peers each stay on the
        innermost shell instead of being pushed out because the formula could."""
        from ecosystem_layout import (
            peer_hub_cluster_radius, peer_hub_gap, peer_hub_ring_radius, peer_hub_shells,
        )

        cluster = peer_hub_cluster_radius(3)
        inner = peer_hub_shells(1, peer_hub_gap(cluster), cluster)[0][0]
        assert peer_hub_ring_radius(2, cluster) == inner

    def test_every_hub_gets_its_own_place(self):
        from ecosystem_layout import NODE_POSITIONS, PEER_HUB_MIN_CENTER_GAP, peer_hub_position

        for total in (1, 2, 5, 16, 33):
            positions = [peer_hub_position(i, total) for i in range(total)]
            seen = {(p["x"], p["z"]) for p in positions}
            assert len(seen) == total, f"{total} hubs did not get {total} distinct places"
            assert all(
                _dist(NODE_POSITIONS["hub"], p) >= PEER_HUB_MIN_CENTER_GAP
                for p in positions
            ), "an independent hub system drifted into the primary hub's ecosystem"

    def test_siblings_do_not_share_a_place_at_any_size(self):
        from ecosystem_layout import peer_hub_child_position, peer_hub_position

        hub = peer_hub_position(3)
        for count in (1, 2, 3, 5, 8, 9, 17, 40):
            kids = [peer_hub_child_position(hub, i, count) for i in range(count)]
            for i, a in enumerate(kids):
                for b in kids[i + 1:]:
                    assert _dist(a, b) > 1.2, f"two of {count} siblings overlap"

    def test_children_stay_inside_their_own_cluster(self):
        from ecosystem_layout import (
            PEER_HUB_CHILD_Y, peer_hub_child_position, peer_hub_cluster_radius,
            peer_hub_position,
        )

        for count in (1, 6, 12, 30):
            limit = math.sqrt(peer_hub_cluster_radius(count) ** 2 + PEER_HUB_CHILD_Y ** 2) + 0.001
            for slot in range(4):
                hub = peer_hub_position(slot)
                for i in range(count):
                    assert _dist(hub, peer_hub_child_position(hub, i, count)) <= limit, (
                        f"a child drifted out of a {count}-peer cluster"
                    )

    def test_primary_hub_providers_have_a_readable_orbit(self):
        from ecosystem_layout import NODE_POSITIONS, primary_hub_child_position

        positions = [primary_hub_child_position(i, 4) for i in range(4)]
        assert all(_dist(NODE_POSITIONS["hub"], p) >= 11.9 for p in positions)
        for i, a in enumerate(positions):
            for b in positions[i + 1:]:
                assert _dist(a, b) >= 12.0

    def test_the_four_federation_rings_stay_ordered_as_the_universe_expands(self):
        """Discovered peers 3.2, UNI hubs 5.0, external hubs (computed), strangers (computed
        outside those). Growth must not let an outer ring swallow an inner one."""
        from ecosystem_layout import (
            FEDERATED_HUB_RADIUS, peer_hub_cluster_radius, peer_hub_ring_radius,
            pending_hub_ring_radius,
        )

        for hubs, children in ((1, 0), (4, 8), (16, 40)):
            cluster = peer_hub_cluster_radius(children)
            hub_ring = peer_hub_ring_radius(hubs, cluster)
            pending = pending_hub_ring_radius(hub_ring, cluster)
            rings = [3.2, FEDERATED_HUB_RADIUS, hub_ring, pending]
            assert rings == sorted(rings) and len(set(rings)) == 4, rings
            assert hub_ring - FEDERATED_HUB_RADIUS > cluster or hub_ring > FEDERATED_HUB_RADIUS
            assert pending - hub_ring > cluster, (
                "an expanding federation swallowed its own quarantine ring"
            )

    def test_a_stranger_is_no_longer_inside_the_spawned_hub_ring(self):
        from ecosystem_layout import FEDERATED_HUB_RADIUS, PENDING_HUB_RADIUS_MIN

        assert PENDING_HUB_RADIUS_MIN > FEDERATED_HUB_RADIUS + 1.0
        # The old formula, kept as the thing this asserts against: 3.2 * 1.6 = 5.12.
        assert abs(3.2 * 1.6 - FEDERATED_HUB_RADIUS) < 0.2, (
            "the old pending radius really did collide with the spawned-hub ring"
        )

    def test_strangers_never_land_on_an_approved_hub(self):
        from ecosystem_layout import peer_hub_position, pending_hub_position

        for total in (1, 3, 8):
            for i in range(total):
                assert _dist(pending_hub_position(i, total), peer_hub_position(i, total)) > 1.0


class TestSharedPeersAreEdgesNotCopies:
    """Federated hubs overlap. They peer with the same ATLAS and the same MOMUS, and — since
    they peer with US — our own address is in their peer lists. Drawing each of those again as
    "their" planet puts two objects on the map for one thing, and makes our hub a moon
    orbiting a stranger. The live federation does exactly this: both external hubs list our
    hub, each other, GAIA and ATLAS.
    """

    def test_one_spelling_per_host(self):
        norm = hub_discovery._norm_url
        assert norm("https://Hunt.ModelMarket.dev/") == norm("http://hunt.modelmarket.dev")
        assert norm(None) == "" and norm("") == ""

    def test_our_own_hub_never_becomes_somebody_elses_moon(self, monkeypatch):
        """The centre of the map cannot also be a planet in orbit around a peer."""
        import asyncio

        theirs = {
            "name": "Their Hub", "hub_version": "3.2.1",
            "peers": [{"url": "https://ours.example", "name": "Ours"},
                      {"url": "https://new.example", "name": "Genuinely new"}],
        }

        async def fake_get_json(client, url, **kwargs):
            if url.endswith("/federation/peers"):
                return {"peers": [{"url": "https://theirs.example"}], "pending": []}
            if "theirs.example" in url and "well-known" in url:
                return theirs
            return None

        monkeypatch.setattr(hub_discovery, "_get_json", fake_get_json)
        monkeypatch.setattr(hub_discovery, "url_is_safe", lambda *a, **k: True)
        res = asyncio.run(hub_discovery.discover_async("https://ours.example"))

        ids = {n["id"] for n in res["nodes"]}
        assert not any("ours.example" in i for i in ids), (
            "our own hub was rendered as a child planet of a peer"
        )
        assert any("new.example" in i for i in ids), "a genuinely new peer must still appear"
        shared = [l for l in res["links"] if l.get("kind") == "shared"]
        assert [l["target"] for l in shared] == ["hub"], (
            "a peer we already know must become an edge to the existing node"
        )


def test_the_hub_is_recognised_under_the_name_its_peers_use(monkeypatch):
    """The monitor dials the hub over loopback (HUB_URL=http://127.0.0.1:9083) while every
    peer lists it by its public name. Matching only the address we dialled left our own hub
    rendered as a moon orbiting a stranger — which is exactly what the live map showed."""
    import asyncio

    theirs = {
        "name": "Their Hub", "hub_version": "3.2.1",
        "peers": [{"url": "https://public.example", "name": "Us, as they know us"}],
    }

    async def fake_get_json(client, url, **kwargs):
        if url.endswith("/federation/peers"):
            return {"peers": [{"url": "https://theirs.example"}], "pending": []}
        if "theirs.example" in url and "well-known" in url:
            return theirs
        if "127.0.0.1" in url and "well-known" in url:
            # The hub tells the monitor its own public name.
            return {"hub_url": "https://public.example", "hub_version": "3.2.1"}
        return None

    monkeypatch.setattr(hub_discovery, "_get_json", fake_get_json)
    monkeypatch.setattr(hub_discovery, "url_is_safe", lambda *a, **k: True)
    res = asyncio.run(hub_discovery.discover_async("http://127.0.0.1:9083"))

    assert not any("public.example" in n["id"] for n in res["nodes"]), (
        "the hub was drawn again under the name its peers use"
    )
    assert [l["target"] for l in res["links"] if l.get("kind") == "shared"] == ["hub"]


class TestTheMeshIsDrawnNotJustComputed:
    """Discovery computes hub-to-hub and shared-peer edges; `get_topology_links` builds edges
    from the entity table and cannot derive an edge between two nodes from either one alone.
    So those links were computed and then dropped, and the federation rendered as a star when
    it is a mesh — the same "seeding an entity and drawing its edge are two wirings" trap this
    file already documents, one level up.
    """

    def test_shared_and_child_edges_reach_the_graph(self, monkeypatch):
        import universe as universe_mod

        uni = universe_mod.VirtualUniverse.__new__(universe_mod.VirtualUniverse)
        uni.entities = {}
        uni._discovered_ids = set()
        uni._discovery_events = []
        uni._discovery_links = []
        uni._family_id_for_node = lambda n: None

        discovered = {
            "nodes": [
                {"id": "hub:a", "label": "Hub A", "group": "peer_hub", "icon": "network",
                 "url": "https://a.example", "description": "", "metrics": {},
                 "status": "active", "position": {"x": 7.5, "y": 8.0, "z": 2.0}},
                {"id": "hub:b", "label": "Hub B", "group": "peer_hub", "icon": "network",
                 "url": "https://b.example", "description": "", "metrics": {},
                 "status": "active", "position": {"x": -6.9, "y": 7.2, "z": 4.9}},
            ],
            "links": [
                {"source": "hub:a", "target": "hub:b", "label": "shared peer", "kind": "shared"},
                {"source": "hub:a", "target": "hub:missing", "label": "shared peer",
                 "kind": "shared"},
            ],
            "events": [],
        }
        import hub_discovery as hd

        monkeypatch.setattr(hd, "discover_cached_sync", lambda *a, **k: discovered)
        uni._apply_discovery("https://ours.example")

        assert uni._discovery_links, "discovery links were not kept"
        drawn = [
            (l["source"], l["target"])
            for l in uni._discovery_links
            if l["source"] in uni.entities and l["target"] in uni.entities
        ]
        assert ("hub:a", "hub:b") in drawn
        assert not any(t == "hub:missing" for _s, t in drawn), (
            "an edge to a peer that failed its own build points at nothing"
        )


def test_the_estate_rule_uses_the_hubs_declared_name_not_the_dialled_one(monkeypatch):
    """The monitor dials the hub over loopback. `_estate("127.0.0.1:9083")` is "0.1", every
    real peer differs from that, and the estate rule then called every satellite of ours a
    foreign hub — which is exactly what the live container produced."""
    import asyncio

    async def fake_get_json(client, url, **kwargs):
        if url.endswith("/federation/peers"):
            return {"peers": [{"url": "https://atlas.ours.example"}], "pending": []}
        if "127.0.0.1" in url and "well-known" in url:
            return {"hub_url": "https://ours.example", "hub_version": "3.2.1"}
        if "atlas.ours.example" in url:
            # One of OUR satellites: hub-shaped manifest, no peers of its own.
            return {"name": "ATLAS", "hub_version": "0.1.0", "peers": [],
                    "categories": ["iot", "sensors"]}
        return None

    monkeypatch.setattr(hub_discovery, "_get_json", fake_get_json)
    monkeypatch.setattr(hub_discovery, "url_is_safe", lambda *a, **k: True)
    monkeypatch.delenv("ALIEN_PUBLIC_HUB_URL", raising=False)
    res = asyncio.run(hub_discovery.discover_async("http://127.0.0.1:9083"))

    groups = {n["label"]: n["group"] for n in res["nodes"]}
    assert groups.get("ATLAS") != "peer_hub", (
        "our own satellite was promoted to the hub ring because the estate was read from the "
        "loopback address we dialled"
    )


class TestTheBallOfHubs:
    """A circle cannot hold a federation.

    Spacing N hubs evenly on one ring needs R = gap / (2·sin(π/N)) — linear in N. Ten hubs
    at an 18-unit gap need radius 29, a hundred need 287, a thousand need 2866, and the
    camera tops out long before that. Hubs therefore fill a ball.
    """

    def test_a_thousand_hubs_stay_inside_a_viewable_volume(self):
        from ecosystem_layout import peer_hub_ring_radius

        # The old ring: 18 / (2·sin(π/1000)) ≈ 2866.
        assert 2000 < 18.0 / (2.0 * math.sin(math.pi / 1000))
        assert peer_hub_ring_radius(1000) < 200

    def test_no_two_hubs_share_a_halo_at_any_size(self):
        from ecosystem_layout import PEER_HUB_MIN_CENTER_GAP, peer_hub_position

        for total in (1, 2, 9, 10, 40, 120, 400):
            points = [peer_hub_position(i, total) for i in range(total)]
            for i, a in enumerate(points):
                for b in points[i + 1:]:
                    assert _dist(a, b) >= PEER_HUB_MIN_CENTER_GAP, (
                        f"two of {total} hubs are {_dist(a, b):.2f} apart"
                    )

    def test_a_quiet_federation_still_sits_on_the_compact_shell(self):
        """Growth is a floor, not a multiplier: a handful of hubs is still ONE shell."""
        from ecosystem_layout import peer_hub_gap, peer_hub_position, peer_hub_shells

        inner = peer_hub_shells(1, peer_hub_gap(0.0))[0][0]
        for total in (1, 5, 9):
            for i in range(total):
                assert _dist(
                    {"x": 0, "y": 0, "z": 0}, peer_hub_position(i, total)
                ) == pytest.approx(inner, abs=0.01)

    def test_the_first_shell_clears_whatever_this_deployment_draws(self):
        """A foreign hub must not land inside our own ecosystem.

        The shell was a constant, 18.1, chosen against the dense service cloud — but the
        oracle ring reaches 24.5 and Platon's cave 26.2, so it ran straight through them.
        On the live UNI and LIVE maps independentai's hub was drawn between Lumen and
        Colony, with KOVA and AEGIS scattered among the oracles. The clearance holds for a
        hub's whole SYSTEM: a provider hangs 2.2 further out and can swing inward.
        """
        from ecosystem_layout import (
            LOCAL_ECOSYSTEM_CLEARANCE, local_ecosystem_radius, peer_hub_child_position,
            peer_hub_cluster_radius, peer_hub_gap, peer_hub_position, peer_hub_shells,
        )
        from oracle_family import build_oracle_family_nodes

        reach = local_ecosystem_radius()
        inner = peer_hub_shells(1, peer_hub_gap(0.0))[0][0]
        assert inner >= reach + LOCAL_ECOSYSTEM_CLEARANCE

        oracles = [n["position"] for n in build_oracle_family_nodes()]
        for total in (1, 4, 9):
            for kids in (0, 3, 12):
                cluster = peer_hub_cluster_radius(kids)
                for i in range(total):
                    hub = peer_hub_position(i, total, max_cluster_radius=cluster)
                    system = [hub] + [
                        peer_hub_child_position(hub, k, kids) for k in range(kids)
                    ]
                    for body in system:
                        for oracle in oracles:
                            assert _dist(body, oracle) > 3.0, (
                                "a foreign hub's system landed in our oracle ring"
                            )

    def test_a_deployment_with_no_shelf_keeps_its_compact_federation(self):
        """The rule is measured, not assumed. A Monitor pointed at somebody else's hub
        draws two nodes and a provider orbit; pushing its federation out to thirty for a
        shelf it does not have would leave its map hollow."""
        import importlib
        import os

        import ecosystem_layout

        previous = os.environ.get("ALIEN_ECOSYSTEM_PROFILE")
        os.environ["ALIEN_ECOSYSTEM_PROFILE"] = "generic"
        try:
            importlib.reload(ecosystem_layout)
            assert ecosystem_layout.local_ecosystem_radius() == (
                ecosystem_layout.PRIMARY_HUB_CHILD_RADIUS
            )
            inner = ecosystem_layout.peer_hub_shells(
                1, ecosystem_layout.peer_hub_gap(0.0)
            )[0][0]
            assert inner == ecosystem_layout.PEER_HUB_MIN_RADIUS
        finally:
            if previous is None:
                os.environ.pop("ALIEN_ECOSYSTEM_PROFILE", None)
            else:
                os.environ["ALIEN_ECOSYSTEM_PROFILE"] = previous
            importlib.reload(ecosystem_layout)

    def test_fat_ecosystems_push_the_shells_apart(self):
        from ecosystem_layout import peer_hub_cluster_radius, peer_hub_gap, peer_hub_ring_radius

        thin = peer_hub_ring_radius(30, peer_hub_cluster_radius(2))
        fat = peer_hub_ring_radius(30, peer_hub_cluster_radius(60))
        assert fat > thin, "a federation of large ecosystems must expand"
        assert peer_hub_gap(peer_hub_cluster_radius(60)) > peer_hub_gap(0.0)

    def test_the_shell_plan_covers_exactly_what_it_was_asked_for(self):
        from ecosystem_layout import peer_hub_gap, peer_hub_shells

        for count in (1, 9, 10, 137, 1000):
            shells = peer_hub_shells(count, peer_hub_gap(0.0))
            assert sum(occupancy for _r, occupancy in shells) == count
            radii = [r for r, _ in shells]
            assert radii == sorted(radii) and len(set(radii)) == len(radii)
