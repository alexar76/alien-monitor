"""HISTOR on the map: registered in every place a node must be, and honest about its numbers.

Structural: a node wired only into ``build_topology`` is invisible in UNI mode, which renders
seeded entities. Honesty: every figure the card shows keeps the window HISTOR publishes it under,
an unreachable log shows nothing rather than zeros, and no copy calls a server safe.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import histor_status  # noqa: E402
from ecosystem_layout import NODE_POSITIONS  # noqa: E402
from histor_layers import histor_node_spec, histor_topology_links  # noqa: E402


@pytest.fixture(autouse=True)
def _no_cache():
    if hasattr(histor_status.fetch_histor_status_sync, "cache_clear"):
        histor_status.fetch_histor_status_sync.cache_clear()
    yield


def _status(**over):
    payload = {
        "health": {"ok": True, "service": "histor", "version": "0.1.0", "store": "postgresql",
                   "tree_size": 1234, "crawl_running": False, "last_crawl_error": None},
        "stats": {
            "log": {"treeSize": 1234, "rootHash": "fe3dcf88209e9b0e" + "0" * 48, "sthTimestamp": "2026-09-23T09:13:04Z"},
            "targets": {"pinned": 9000, "block_tier": 4},
            "changes": {"last24h": 1, "last7d": 12, "last30d": 40},
            "lastRun": {"finishedAt": "2026-09-23T10:00:00Z", "registryServers": 21267, "registryEndpoints": 21726,
                        "attempted": 20400, "statuses": {"ok": 9100, "http-401": 8000, "http-403": 300, "timeout": 50}},
        },
    }
    payload.update(over)
    return payload


def test_the_node_is_in_build_topology_with_its_edges():
    import main

    nodes, links = main.build_topology()
    assert "histor" in {n["id"] for n in nodes}
    pairs = {(link["source"], link["target"]) for link in links}
    assert ("warden", "histor") in pairs and ("histor", "hub") in pairs


def test_the_node_is_seeded_in_universe_mode():
    from universe import VirtualUniverse

    u = VirtualUniverse()
    u.seed_entities()
    assert "histor" in u.entities
    assert u.entities["histor"].position == NODE_POSITIONS["histor"]
    links = {(link["source"], link["target"]) for link in u.get_topology_links()}
    assert ("warden", "histor") in links and ("histor", "hub") in links


def test_position_clears_every_other_node():
    here = NODE_POSITIONS["histor"]
    for other, pos in NODE_POSITIONS.items():
        if other == "histor":
            continue
        d = math.sqrt(sum((here[k] - pos[k]) ** 2 for k in ("x", "y", "z")))
        assert d >= 4.5, (other, d)


def test_live_numbers_keep_their_windows():
    nodes = [histor_node_spec()]
    histor_status.apply_histor_to_nodes(nodes, _status())
    node = nodes[0]
    assert node["status"] == "active"
    assert node["metrics"] == {"labels": 1234, "pinned": 9000, "changes_7d": 12, "endpoints": 21726}
    live = node["histor_live"]
    assert live["auth_required"] == 8300 and live["answered_ok"] == 9100
    assert live["changes"] == {"last24h": 1, "last7d": 12, "last30d": 40}
    assert live["root_hash"] == "fe3dcf88209e9b0e"


def test_an_unreachable_log_shows_nothing_not_zeros():
    nodes = [histor_node_spec()]
    histor_status.apply_histor_to_nodes(nodes, None)
    assert nodes[0]["status"] == "offline" and nodes[0]["metrics"] == {} and "histor_live" not in nodes[0]


def test_a_failed_crawl_is_an_error_state():
    nodes = [histor_node_spec()]
    bad = _status(health={"ok": True, "crawl_running": False, "last_crawl_error": "RuntimeError: registry down"})
    histor_status.apply_histor_to_nodes(nodes, bad)
    assert nodes[0]["status"] == "error"


def test_copy_never_claims_safety():
    text = histor_node_spec()["description"].lower() + " ".join(l["label"] for l in histor_topology_links()).lower()
    for word in ("secure", "audited", "certified", "trusted", "verified"):
        assert word not in text
    assert "never a safety rating" in text


def test_an_interrupted_run_stays_an_error_after_histor_restarts():
    """/health forgets after a restart; the run row does not (audit F24)."""
    nodes = [histor_node_spec()]
    payload = _status()
    payload["stats"]["lastRun"] = {"finishedAt": "2026-09-23T10:45:09Z", "statuses": {},
                                   "error": "interrupted: the process restarted before the crawl finished"}
    histor_status.apply_histor_to_nodes(nodes, payload)
    live = nodes[0]["histor_live"]
    assert nodes[0]["status"] == "error" and live["last_run_error"].startswith("interrupted")
    assert live["auth_required"] is None, "a run with no statuses measured nothing (audit F49)"


def test_a_malformed_payload_draws_without_raising():
    nodes = [histor_node_spec()]
    histor_status.apply_histor_to_nodes(nodes, {"health": {"ok": True}, "stats": {"log": [], "lastRun": "x", "targets": 5}})
    assert nodes[0]["status"] in ("idle", "active")


@pytest.mark.parametrize("question", [
    "display the price history of GAIA",
    "show history",
    "show funding history",
    "muéstrame el historial de ARGUS",
    "montre l historique du hub",
    "покажи историю хаба",
])
def test_history_is_not_histor(question):
    from ai_nav_actions import _match_node

    state = {"nodes": [{"id": "histor", "label": "HISTOR"}, {"id": "gaia", "label": "GAIA"}, {"id": "hub", "label": "Hub"}]}
    assert _match_node(question, state) != "histor"


@pytest.mark.parametrize("question", ["show HISTOR", "open histor", "что такое хистор?", "zoom to histor.modelmarket.dev"])
def test_histor_by_name_still_resolves(question):
    from ai_nav_actions import _match_node

    state = {"nodes": [{"id": "histor", "label": "HISTOR"}]}
    assert _match_node(question, state) == "histor"
