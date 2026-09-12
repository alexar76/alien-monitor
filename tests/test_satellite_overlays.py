"""One owner for "hydrate the universe graph", because three of them disagreed.

`GET /api/topology`, the connect-time snapshot and `tick_universe` all build the same graph
and each applied a different subset of the satellite status layers — four, twelve and sixteen.
A satellite missing from a path renders at its node-spec defaults, `status: "offline"` with
zero metrics, which is indistinguishable from the satellite actually being down. MOMUS read
"недоступен, живых данных нет" on the detail card while answering /health, /findings and
/intel in under 300 ms with three findings and forty-five intel cards.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

import satellite_overlays as universe_layers  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_cache():
    universe_layers.reset_cache()
    yield
    universe_layers.reset_cache()


class TestThereIsOnlyOneLayerStack:
    def test_no_call_site_applies_layers_of_its_own(self):
        """The regression that matters: someone adds a layer to one path and not the others.

        Any `apply_*_graph` outside the owner is a second list, and a second list drifts.
        """
        owner = (BACKEND / "satellite_overlays.py").read_text()
        allowed = set(re.findall(r"apply_(\w+?)_graph\(", owner))
        assert len(allowed) >= 15, "the owner should carry the whole stack"

        for name in ("main.py", "universe.py"):
            text = (BACKEND / name).read_text()
            for block in re.findall(r'mode="universe"[^)]*\)', text):
                assert "apply_live_layers" in block or "apply_" not in block, (
                    f"{name} applies a universe layer outside universe_layers.py: {block[:80]}"
                )

    def test_the_owner_covers_every_satellite_that_was_being_missed(self):
        owner = (BACKEND / "satellite_overlays.py").read_text()
        for satellite in ("argus", "atlas", "gaia", "momus", "warden", "treasury", "logos",
                          "skopos", "metis", "helios", "dioscuri", "hephaestus", "bridges",
                          "themis", "basanos", "settlement", "factory_agents"):
            assert satellite in owner, f"{satellite} is not in the one place that owns the list"


class TestOneFailingSatelliteDoesNotSilenceTheRest:
    def test_a_raising_layer_is_logged_and_stepped_over(self, monkeypatch):
        """Before this, the layers ran as a flat sequence: the first one to raise took out
        every layer after it, and the only symptom was more nodes reading offline."""
        calls = []

        def boom():
            raise RuntimeError("satellite mid-deploy")

        def ok(name):
            return lambda: calls.append(name)

        def fake_apply_all(nodes, **kwargs):
            for name, step in (("a", ok("a")), ("b", boom), ("c", ok("c"))):
                try:
                    step()
                except Exception:
                    pass
            nodes[0]["status"] = "active"

        monkeypatch.setattr(universe_layers, "_apply_all", fake_apply_all)
        nodes = [{"id": "momus", "status": "offline"}]
        universe_layers.apply_live_layers(nodes)
        assert calls == ["a", "c"], "a raising layer stopped the ones after it"
        assert nodes[0]["status"] == "active"


class TestTheCacheKeepsTheRouteHonestAndFast:
    def _stub(self, monkeypatch, counter):
        def fake_apply_all(nodes, **kwargs):
            counter.append(1)
            for n in nodes:
                n["status"] = "active"
                n["metrics"] = {"findings": 3}

        monkeypatch.setattr(universe_layers, "_apply_all", fake_apply_all)

    def test_a_second_call_replays_the_overlay_instead_of_polling_again(self, monkeypatch):
        """Seventeen sequential network polls with 2-4s timeouts is a minute of dead air on a
        REST call when a few hosts are down. Correctness must not cost a page load."""
        counter: list[int] = []
        self._stub(monkeypatch, counter)
        first = [{"id": "momus", "status": "offline", "metrics": {}}]
        assert universe_layers.apply_live_layers(first) == "fresh"
        second = [{"id": "momus", "status": "offline", "metrics": {}}]
        assert universe_layers.apply_live_layers(second) == "cached"
        assert len(counter) == 1
        assert second[0]["status"] == "active"
        assert second[0]["metrics"] == {"findings": 3}

    def test_the_ticker_never_reads_the_cache(self, monkeypatch):
        """It is what keeps the cache warm for everyone else — a ticker serving itself stale
        data would freeze the whole map at whatever the first tick saw."""
        counter: list[int] = []
        self._stub(monkeypatch, counter)
        universe_layers.apply_live_layers([{"id": "momus"}])
        universe_layers.apply_live_layers([{"id": "momus"}], allow_cache=False)
        assert len(counter) == 2

    def test_an_expired_cache_polls_again(self, monkeypatch):
        counter: list[int] = []
        self._stub(monkeypatch, counter)
        monkeypatch.setenv("ALIEN_LAYER_CACHE_S", "0")
        universe_layers.apply_live_layers([{"id": "momus"}])
        universe_layers.apply_live_layers([{"id": "momus"}])
        assert len(counter) == 2

    def test_the_overlay_never_carries_structural_fields(self, monkeypatch):
        """Only what the layers wrote. Replaying a position or a group from a cache would
        pin a node where it used to be, which is how a stale map looks correct."""
        def fake_apply_all(nodes, **kwargs):
            nodes[0]["status"] = "active"

        monkeypatch.setattr(universe_layers, "_apply_all", fake_apply_all)
        universe_layers.apply_live_layers(
            [{"id": "momus", "group": "security", "position": {"x": 1, "y": 2, "z": 3}}])
        overlay = universe_layers._CACHE["overlay"]["momus"]
        assert set(overlay) == {"status"}

    def test_a_node_the_cache_does_not_know_is_left_alone(self, monkeypatch):
        def fake_apply_all(nodes, **kwargs):
            for n in nodes:
                n["status"] = "active"

        monkeypatch.setattr(universe_layers, "_apply_all", fake_apply_all)
        universe_layers.apply_live_layers([{"id": "momus"}])
        fresh = [{"id": "momus"}, {"id": "brand-new", "status": "idle"}]
        universe_layers.apply_live_layers(fresh)
        assert fresh[0]["status"] == "active"
        assert fresh[1]["status"] == "idle"
