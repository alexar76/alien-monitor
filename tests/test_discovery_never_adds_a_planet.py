"""Adding a federation seed must never add a planet to the map.

The rule, stated by the owner: *прописывание сида не должно добавлять шаров в алиен монитор*.

That is stronger than the fix it replaces. Folding a discovered peer onto the node the map
already draws used to be driven by three hand-maintained lists — a reserved-id set, a host
table and a URL table — so a satellite that got a seed duplicated as a second violet planet
until somebody remembered to add it. ARGUS, DIOSCURI, HELIOS and WARDEN publish no well-known
today, which is the only reason they had not duplicated yet.

So the rule is now derived from the graph: any discovered peer carrying a URL the map already
draws IS that node. The tables survive only as a spelling fallback for peers whose URL differs
from the node's own (MOMUS' Treasury on a path, the studio, the bridges).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))


@pytest.fixture()
def uni(monkeypatch):
    monkeypatch.setenv("ALIEN_DISCOVERY_ENABLED", "0")
    monkeypatch.setenv("ALIEN_ANVIL_STATE_MAX_MB", "4096")
    import universe as universe_mod

    try:
        u = universe_mod.VirtualUniverse()
        # A bare universe has no entities; the real map is what these tests are about.
        u._ensure_topology_seeded()
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"universe unavailable here: {type(exc).__name__}: {exc}")
    return u


def _add_drawn(uni, node_id, url):
    """A node the map draws — the thing a discovered peer must fold onto, never shadow."""
    import universe as universe_mod

    ent = universe_mod.EcosystemEntity(node_id, node_id.upper(), "core", group="security")
    ent.url = url
    uni.entities[node_id] = ent
    return ent


def _discover(monkeypatch, nodes, links=()):
    import hub_discovery

    monkeypatch.setattr(
        hub_discovery, "discover_cached_sync",
        lambda hub_url, allow_private=False: {
            "nodes": list(nodes), "links": [dict(x) for x in links], "events": [],
        },
    )


def _drawn_with_url(uni, *candidates):
    for eid in candidates:
        ent = uni.entities.get(eid)
        if ent is not None and getattr(ent, "url", ""):
            return eid
    return None


class TestASeedForASatelliteAddsNoPlanet:
    @pytest.mark.parametrize("node_id", ["argus", "dioscuri", "helios", "warden"])
    def test_the_four_that_publish_no_well_known_today(self, uni, monkeypatch, node_id):
        """Named because a colleague's note said these cannot duplicate "until someone adds
        a seed". The point of the fix is that the day someone does, nothing has to change."""
        existing = uni.entities.get(node_id)
        if existing is None or not getattr(existing, "url", ""):
            pytest.skip(f"{node_id} is not a drawn node with a url in this build")
        before = set(uni.entities)
        _discover(monkeypatch, [{
            "id": f"{node_id}---some-long-self-description",
            "label": f"{node_id.upper()} — some long self description",
            "url": existing.url,
            "group": "oracle",
            "metrics": {"capabilities": 7, "trust_score": 0.44},
            "status": "active",
        }])
        uni._apply_discovery("https://hub.example")
        assert set(uni.entities) == before, (
            f"a seed for {node_id} minted a second planet: "
            f"{sorted(set(uni.entities) - before)}"
        )

    def test_the_existing_node_is_enriched_rather_than_shadowed(self, uni, monkeypatch):
        target = _drawn_with_url(uni, "momus", "atlas", "gaia", "skopos")
        if not target:
            pytest.skip("no drawn satellite with a url in this build")
        _discover(monkeypatch, [{
            "id": "stranger-shaped-id", "label": "Some Peer",
            "url": uni.entities[target].url,
            "metrics": {"capabilities": 6}, "status": "active",
        }])
        uni._apply_discovery("https://hub.example")
        ent = uni.entities[target]
        assert ent.status == "active"
        assert ent.metrics.get("capabilities") == 6
        assert ent.metrics.get("live") == 1

    def test_the_url_rule_needs_no_table(self, uni, monkeypatch):
        """A satellite nobody has listed anywhere still folds, purely because the map already
        draws its address. This is the property the hand-maintained lists could not give."""
        import canonical_peers

        made_up = "https://brand-new-satellite.example"
        assert canonical_peers.canonical_node_id_for_peer({"url": made_up}) is None
        _add_drawn(uni, "brand-new-satellite", made_up)
        before = set(uni.entities)
        _discover(monkeypatch, [{"id": "brand-new---long-description", "url": made_up,
                                 "label": "Brand New — long description"}])
        uni._apply_discovery("https://hub.example")
        assert set(uni.entities) == before

    def test_scheme_and_trailing_slash_do_not_make_a_second_planet(self, uni, monkeypatch):
        _add_drawn(uni, "sat", "https://sat.example")
        before = set(uni.entities)
        _discover(monkeypatch, [{"id": "sat---desc", "url": "http://sat.example/",
                                 "label": "SAT — desc"}])
        uni._apply_discovery("https://hub.example")
        assert set(uni.entities) == before


class TestAGenuineStrangerStillGetsOne:
    def test_a_peer_the_map_does_not_draw_is_still_added(self, uni, monkeypatch):
        """The fold must not become a filter: an unknown federation peer is exactly what the
        map is for."""
        before = set(uni.entities)
        _discover(monkeypatch, [{
            "id": "some-stranger-hub", "label": "Stranger", "group": "oracle",
            "url": "https://stranger.example", "status": "active", "metrics": {},
        }])
        uni._apply_discovery("https://hub.example")
        assert "some-stranger-hub" in set(uni.entities) - before


class TestLinksFollowTheFold:
    def test_an_edge_to_a_folded_peer_points_at_the_node_that_survived(self, uni, monkeypatch):
        target = _drawn_with_url(uni, "momus", "atlas", "gaia", "skopos")
        if not target:
            pytest.skip("no drawn satellite with a url in this build")
        _discover(
            monkeypatch,
            [{"id": "peer---long-desc", "url": uni.entities[target].url, "label": "X"}],
            [{"source": "some-hub", "target": "peer---long-desc", "label": "federates"}],
        )
        uni._apply_discovery("https://hub.example")
        targets = [lnk.get("target") for lnk in uni._discovery_links]
        assert "peer---long-desc" not in targets, "an edge points at an id nothing draws"
        assert target in targets

    def test_an_edge_that_folds_onto_itself_is_dropped(self, uni, monkeypatch):
        target = _drawn_with_url(uni, "momus", "atlas", "gaia", "skopos")
        if not target:
            pytest.skip("no drawn satellite with a url in this build")
        url = uni.entities[target].url
        _discover(
            monkeypatch,
            [{"id": "a---desc", "url": url, "label": "A"},
             {"id": "b---desc", "url": url, "label": "B"}],
            [{"source": "a---desc", "target": "b---desc"}],
        )
        uni._apply_discovery("https://hub.example")
        assert not [lnk for lnk in uni._discovery_links
                    if lnk.get("source") == lnk.get("target")], "a node links to itself"
