"""The two maps must be navigable from each other — and the bubble must stay sealed.

The ecosystem runs a universe map and a live map as separate processes behind separate
paths. Neither used to admit the other existed. These tests pin what the fix may and may
not do: it may tell an operator standing on the observation deck where the other world is;
it may not put that door anywhere an inhabitant of the bubble could read it.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from realm_links import realm_links, session_tick_mode  # noqa: E402


class TestWhatEachModeIsTold:
    def test_the_universe_map_points_at_the_live_map(self, monkeypatch):
        monkeypatch.delenv("ALIEN_LIVE_MAP_URL", raising=False)
        monkeypatch.delenv("ALIEN_UNI_HUB_URL", raising=False)
        links = realm_links("universe")
        assert links["realm"] == "uni"
        assert links["other"] == {"realm": "live", "map_url": "/monitor-live/"}

    def test_the_live_map_points_back_at_the_universe_map(self, monkeypatch):
        monkeypatch.delenv("ALIEN_UNIVERSE_MAP_URL", raising=False)
        links = realm_links("real")
        assert links["realm"] == "live"
        assert links["other"] == {"realm": "uni", "map_url": "/monitor/"}

    def test_test_mode_is_told_nothing(self):
        """Test mode simulates the whole ecosystem rather than one of the two realms, so
        "the other realm" has no referent and a link would invent one."""
        assert realm_links("test") == {}
        assert realm_links("") == {}
        assert realm_links(None) == {}  # type: ignore[arg-type]


class TestTheBubbleHubLink:
    def test_it_appears_only_where_it_is_configured(self, monkeypatch):
        monkeypatch.delenv("ALIEN_UNI_HUB_URL", raising=False)
        assert "hub_url" not in realm_links("universe")
        monkeypatch.setenv("ALIEN_UNI_HUB_URL", "https://uni.example.dev/")
        assert realm_links("universe")["hub_url"] == "https://uni.example.dev"

    def test_the_live_map_is_never_handed_the_bubble_hub(self, monkeypatch):
        """The live map reports real money. A link from it to a hub whose dollars are
        simulated is exactly how a virtual balance gets read as revenue."""
        monkeypatch.setenv("ALIEN_UNI_HUB_URL", "https://uni.example.dev")
        assert "hub_url" not in realm_links("real")


class TestThisProcessMayNotTickTheOtherRealm:
    def test_a_universe_monitor_does_not_honor_live(self):
        """Clicking LIVE on /monitor/ used to poll the bubble hub and label it real money."""
        assert session_tick_mode("real", "universe") == "universe"
        assert session_tick_mode("universe", "universe") == "universe"

    def test_a_live_monitor_does_not_honor_universe(self):
        assert session_tick_mode("universe", "real") == "real"
        assert session_tick_mode("real", "real") == "real"

    def test_test_overlay_still_runs_on_either_map(self):
        assert session_tick_mode("test", "universe") == "test"
        assert session_tick_mode("test", "real") == "test"

    def test_a_test_process_may_still_switch_in_process(self):
        assert session_tick_mode("real", "test") == "real"
        assert session_tick_mode("universe", "test") == "universe"


class TestDefaultsAreSafeToInherit:
    def test_no_deployment_inherits_our_hostnames(self, monkeypatch):
        """Someone else's monitor must not link into our infrastructure. Map defaults are
        relative paths; the bubble hub has no default at all."""
        for name in ("ALIEN_UNIVERSE_MAP_URL", "ALIEN_LIVE_MAP_URL", "ALIEN_UNI_HUB_URL"):
            monkeypatch.delenv(name, raising=False)
        for mode in ("universe", "real"):
            rendered = repr(realm_links(mode))
            assert "modelmarket.dev" not in rendered
            assert "://" not in rendered

    def test_an_operator_can_move_either_map(self, monkeypatch):
        monkeypatch.setenv("ALIEN_LIVE_MAP_URL", "https://ops.example/live")
        monkeypatch.setenv("ALIEN_UNIVERSE_MAP_URL", "https://ops.example/uni")
        assert realm_links("universe")["other"]["map_url"] == "https://ops.example/live"
        assert realm_links("real")["other"]["map_url"] == "https://ops.example/uni"
