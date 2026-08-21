"""The TTL in front of the satellite pollers, and the rules that keep it honest.

Without it, the 1.5 s state tick asked every satellite ~40 times a minute for
numbers that change on a 5-minute cycle. That was waste until LOGOS's 30-per-minute
rate limit turned it into breakage: the monitor exhausted the budget and the card it
was polling for went blank. The dashboard broke itself by asking too eagerly.

The rules worth testing are not "it caches" but where caching must STOP: a blip may
be covered by the last good answer, a real outage may not.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

MONITOR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MONITOR / "backend"))

from poll_cache import ttl_cached  # noqa: E402


class TestItActuallyCaches:
    def test_a_second_call_inside_the_ttl_does_not_hit_the_network(self):
        calls = []

        @ttl_cached(ttl_s=60)
        def poll():
            calls.append(1)
            return {"ok": True}

        assert poll() == {"ok": True}
        assert poll() == {"ok": True}
        assert len(calls) == 1, "the poller was called twice inside its TTL"

    def test_force_refresh_bypasses_it(self):
        calls = []

        @ttl_cached(ttl_s=60)
        def poll():
            calls.append(1)
            return {"n": len(calls)}

        poll()
        assert poll(force_refresh=True) == {"n": 2}
        assert len(calls) == 2

    def test_arguments_are_part_of_the_key(self):
        """Pollers take base_url/timeout; two hosts must not share one entry."""
        calls = []

        @ttl_cached(ttl_s=60)
        def poll(base_url: str = ""):
            calls.append(base_url)
            return {"host": base_url}

        assert poll(base_url="a")["host"] == "a"
        assert poll(base_url="b")["host"] == "b"
        assert poll(base_url="a")["host"] == "a"
        assert calls == ["a", "b"]

    def test_a_zero_ttl_disables_caching(self):
        calls = []

        @ttl_cached(ttl_s=0)
        def poll():
            calls.append(1)
            return {"ok": True}

        poll(); poll()
        assert len(calls) == 2


class TestFailuresDoNotBlankAGoodCard:
    def test_one_failed_read_is_covered_by_the_last_good_value(self):
        """A single timeout or 429 must not erase a card that was correct."""
        state = {"fail": False}

        @ttl_cached(ttl_s=0.05)
        def poll():
            return {} if state["fail"] else {"capabilities": 53}

        assert poll() == {"capabilities": 53}
        state["fail"] = True
        import time

        time.sleep(0.06)                      # TTL expired, so the read is attempted
        assert poll() == {"capabilities": 53}, "a blip blanked the last good answer"

    def test_a_real_outage_eventually_surfaces(self):
        """Past the grace window the failure is passed through. A cache that hides
        a dead satellite forever makes the monitor lie, which is worse than a
        blank card."""
        import time

        state = {"fail": False}

        @ttl_cached(ttl_s=0.05, grace_multiple=2.0)
        def poll():
            return None if state["fail"] else {"capabilities": 53}

        assert poll() == {"capabilities": 53}
        state["fail"] = True
        time.sleep(0.06)
        assert poll() == {"capabilities": 53}   # inside grace
        time.sleep(0.12)                        # past ttl * grace
        assert poll() is None, "the outage never surfaced"

    def test_recovery_replaces_the_stale_value(self):
        import time

        state = {"fail": True}

        @ttl_cached(ttl_s=0.05)
        def poll():
            return {} if state["fail"] else {"capabilities": 7}

        assert poll() == {}
        state["fail"] = False
        time.sleep(0.06)
        assert poll() == {"capabilities": 7}


class TestEveryPollerIsCovered:
    """A new satellite poller that forgets the cache is the bug this file exists
    for, so the check is mechanical rather than a convention to remember."""

    POLLERS = {
        "argus_status": ["fetch_argus_status_sync", "fetch_argus_health_sync"],
        "atlas_status": ["fetch_atlas_status_sync"],
        "bridges_status": ["fetch_bridges_status_sync"],
        "dioscuri_status": ["fetch_dioscuri_health_sync"],
        "gaia_status": ["fetch_gaia_status_sync"],
        "helios_status": ["fetch_helios_health_sync"],
        "logos_status": ["fetch_logos_status_sync"],
        "metis_status": ["fetch_metis_health_sync"],
        "momus_status": ["fetch_momus_status_sync"],
        "hephaestus_status": ["fetch_hephaestus_status_sync"],
        "skopos_status": ["fetch_skopos_status_sync"],
        "treasury_status": ["fetch_treasury_status_sync"],
    }

    @pytest.mark.parametrize("module,functions", sorted(POLLERS.items()))
    def test_the_tick_facing_fetch_is_cached(self, module, functions):
        import importlib

        mod = importlib.import_module(module)
        for name in functions:
            fn = getattr(mod, name, None)
            assert fn is not None, f"{module}.{name} disappeared — update this list"
            assert hasattr(fn, "cache_clear"), (
                f"{module}.{name} is not wrapped in ttl_cached; the 1.5 s state tick "
                "will hammer that satellite ~40 times a minute"
            )

    def test_no_status_module_was_missed(self):
        """Every *_status.py that exposes a sync fetch must appear above."""
        found: dict[str, list[str]] = {}
        for path in sorted((MONITOR / "backend").glob("*_status.py")):
            text = path.read_text(encoding="utf-8")
            names = [
                line.split("def ")[1].split("(")[0]
                for line in text.splitlines()
                if line.startswith("def fetch_") and line.rstrip().endswith(("_sync(", "_sync():"))
                or (line.startswith("def fetch_") and "_sync(" in line)
            ]
            if names:
                found[path.stem] = names
        missing = {
            m: [n for n in names if n not in self.POLLERS.get(m, [])]
            for m, names in found.items()
        }
        unexpected = {m: n for m, n in missing.items() if n}
        # metis exposes an async variant and argus a second health call; anything
        # genuinely new shows up here and has to be decided on, not ignored.
        allowed = {"argus_status", "metis_status", "treasury_status"}
        surprises = {m: n for m, n in unexpected.items() if m not in allowed}
        assert not surprises, f"undecided sync pollers: {surprises}"


class TestADownSatelliteIsNotHammered:
    """HELIOS was refusing connections and still being polled every tick: the cache
    stored the failure but never served it, so a dead satellite got 40 requests a
    minute forever. Being down does not become truer by asking again."""

    def test_a_failure_is_served_from_cache_inside_the_ttl(self):
        calls = []

        @ttl_cached(ttl_s=60)
        def poll():
            calls.append(1)
            return None

        assert poll() is None
        assert poll() is None
        assert len(calls) == 1, "a down satellite was polled twice inside its TTL"

    def test_recovery_is_still_noticed_after_the_ttl(self):
        import time

        state = {"up": False}

        @ttl_cached(ttl_s=0.05)
        def poll():
            return {"ok": True} if state["up"] else None

        assert poll() is None
        state["up"] = True
        assert poll() is None, "served from cache, as designed"
        time.sleep(0.06)
        assert poll() == {"ok": True}, "recovery was never picked up"
