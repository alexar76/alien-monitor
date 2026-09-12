"""The ``bridges`` node: present in every mode, decorating only, and honest about having no figures.

aimarket-bridges is the ecosystem's third paid invoke channel and the only one nothing counts —
it is a client library running inside the buyer's process, so no aggregate ever reaches the
monitor. That makes this node's correctness almost entirely about what it does NOT render.

Two failure modes are checked harder than the presence ones, because they are the ones that would
mislead a viewer rather than merely disappoint one:

  * a zeroed metric on a billed channel. ``{"paid_invokes": 0}`` states that we measured the
    traffic and there was none. The truth is that nobody measures it. This is the same defect as
    calling an unreachable probe target a pass (momus/docs/found-and-fixed.md).
  * a money figure without its settlement label. UNI settlement moves nothing, so a balance shown
    without that word invites the reader to believe money moved.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import bridges_status  # noqa: E402
from bridges_layers import bridges_node_spec, bridges_topology_links  # noqa: E402
from bridges_status import (  # noqa: E402
    BILLED_COUNTERS,
    REASON_NO_COUNTERS,
    REASON_NO_ENDPOINT,
    REASON_UNREACHABLE,
    apply_bridges_to_nodes,
    fetch_bridges_status_sync,
    fill_bridges_sim_node,
)


@pytest.fixture(autouse=True)
def _no_telemetry_env(monkeypatch):
    """Default every test to the real-world state: no telemetry endpoint configured anywhere."""
    for var in ("ALIEN_BRIDGES_URL", "BRIDGES_URL"):
        monkeypatch.delenv(var, raising=False)


# ── present in all three modes ────────────────────────────────────────────────


def test_bridges_is_in_the_static_topology():
    """TEST and LIVE both render build_topology()."""
    from main import build_topology

    nodes, _links = build_topology()
    assert "bridges" in {n.get("id") for n in nodes}


def test_bridges_is_in_the_universe_simulator():
    """UNI renders u.entities, not build_topology() — the gap that made MOMUS invisible."""
    from universe import VirtualUniverse

    u = VirtualUniverse()
    u.seed_entities()
    assert "bridges" in u.entities


def test_bridges_survives_the_topology_reseed_path():
    """_ensure_topology_seeded() runs when the UNI bootstrap partially failed; a satellite added
    only to seed_entities() would vanish on that path."""
    from universe import VirtualUniverse

    u = VirtualUniverse()
    u.seed_entities()
    u.entities.pop("bridges", None)
    u._ensure_topology_seeded()
    assert "bridges" in u.entities


def test_bridges_links_to_the_hub_as_billed_traffic():
    """The edge is the claim that this is a channel, not decoration."""
    links = bridges_topology_links()
    hub_edges = [e for e in links if e["source"] == "bridges" and e["target"] == "hub"]
    assert hub_edges, "bridges must be drawn as a source of traffic into the hub"
    assert "invoke" in hub_edges[0]["label"].lower()


def test_bridges_is_linked_to_the_hub_in_every_mode():
    """The edge must be DRAWN, not merely available from the helper.

    Seeding the entity and drawing its edge are two separate wirings in UNI mode, and the first
    one alone looks complete in a diff — the node renders, just floating, with the single claim
    it exists to make (billed channel INTO the hub) silently missing. This caught exactly that.
    """
    from main import build_topology
    from universe import VirtualUniverse

    def hub_edge(links):
        return [
            e for e in links
            if {e["source"], e["target"]} == {"bridges", "hub"}
        ]

    _nodes, static_links = build_topology()
    assert hub_edge(static_links), "TEST/LIVE topology is missing the bridges→hub edge"

    u = VirtualUniverse()
    u.seed_entities()
    assert hub_edge(u.get_topology_links()), "UNI topology is missing the bridges→hub edge"


def test_bridges_position_does_not_collide():
    import math

    from ecosystem_layout import NODE_POSITIONS, ring_position
    from oracle_family import ORACLE_FAMILY

    pos = NODE_POSITIONS["bridges"]

    def dist(a, b):
        return math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"]))

    for nid, other in NODE_POSITIONS.items():
        if nid == "bridges":
            continue
        assert dist(pos, other) >= 4.0, f"bridges sits on top of {nid}"
    total = len(ORACLE_FAMILY)
    for i in range(total):
        assert dist(pos, ring_position(i, total)) >= 4.5


# ── decorates only ────────────────────────────────────────────────────────────


def test_apply_returns_quietly_when_the_node_is_absent():
    """apply_* must never CREATE the node — that is the topology's job, in each mode separately.
    A helper that created it would hide exactly the wiring gap this file exists to catch."""
    nodes: list[dict] = [{"id": "hub"}]
    apply_bridges_to_nodes(nodes, None)
    assert [n["id"] for n in nodes] == ["hub"]
    assert "bridges_live" not in nodes[0]


def test_apply_on_an_empty_graph_does_not_crash():
    nodes: list[dict] = []
    apply_bridges_to_nodes(nodes, {"health": {"status": "ok"}, "metrics": {}})
    assert nodes == []


def test_apply_touches_only_the_bridges_node():
    nodes = [{"id": "hub", "metrics": {"peers": 3}}, dict(bridges_node_spec())]
    apply_bridges_to_nodes(nodes, None)
    assert nodes[0]["metrics"] == {"peers": 3}


# ── offline renders no figures ────────────────────────────────────────────────


def test_offline_renders_no_figures_at_all():
    node = dict(bridges_node_spec())
    apply_bridges_to_nodes([node], None)

    assert node["status"] == "offline"
    # `{}`, not zeros. This assertion is the whole point of the node.
    assert node["metrics"] == {}
    live = node["bridges_live"]
    assert live["instrumented"] is False
    assert live["counters"] == {}
    assert live["spend_usd"] is None
    assert set(live["unmeasured"]) == set(BILLED_COUNTERS)


def test_offline_never_reports_a_zero_for_a_billed_counter():
    """A zero would say "measured, and it is none". Nobody measured anything here."""
    node = dict(bridges_node_spec())
    apply_bridges_to_nodes([node], None)

    for counter in BILLED_COUNTERS:
        assert counter not in node["metrics"]
        assert counter not in node["bridges_live"]["counters"]
    assert 0 not in node["metrics"].values()


def test_the_node_spec_itself_ships_empty_metrics():
    """Before any poll runs, the node is already honest — no placeholder to forget to clear."""
    assert bridges_node_spec()["metrics"] == {}
    assert bridges_node_spec()["status"] == "offline"


def test_unconfigured_and_unreachable_are_different_reasons():
    """"we never asked" and "we asked and got nothing" are different facts about the world."""
    node = dict(bridges_node_spec())
    apply_bridges_to_nodes([node], None, telemetry_url="")
    assert node["bridges_live"]["reason"] == REASON_NO_ENDPOINT

    node = dict(bridges_node_spec())
    apply_bridges_to_nodes([node], None, telemetry_url="http://127.0.0.1:9/telemetry")
    assert node["bridges_live"]["reason"] == REASON_UNREACHABLE


def test_no_endpoint_means_no_request_is_made(monkeypatch):
    """Unconfigured must not produce a network call — a DNS failure would relabel "not built" as
    "down", which is a different and false statement."""

    def explode(*_a, **_kw):  # pragma: no cover - only runs on regression
        raise AssertionError("bridges_status made an HTTP request with no endpoint configured")

    monkeypatch.setattr(bridges_status.httpx, "Client", explode)
    assert fetch_bridges_status_sync() is None


def test_test_mode_fabricates_nothing():
    """Every other node in the TEST simulator invents plausible activity. This one must not:
    a screenshot of "$412 billed through bridges" is read as a measurement by everyone."""
    node = dict(bridges_node_spec())
    fill_bridges_sim_node(node)
    assert node["metrics"] == {}
    assert node["bridges_live"]["counters"] == {}
    assert node["bridges_live"]["spend_usd"] is None
    assert node["bridges_live"]["instrumented"] is False


def test_test_mode_tick_leaves_the_node_without_figures():
    """Through the real simulator, not the helper — the wiring is what regresses."""
    from main import EcosystemSimulator

    sim = EcosystemSimulator()
    state = sim.step()
    node = next(n for n in state["nodes"] if n["id"] == "bridges")
    assert node["metrics"] == {}
    assert node["bridges_live"]["instrumented"] is False


# ── live telemetry, when it eventually exists ─────────────────────────────────


def _status(**metrics):
    return {"health": {"status": "ok", "service": "aimarket-bridges", "version": "0.1.0"},
            "metrics": metrics}


def test_measured_counters_are_shown():
    node = dict(bridges_node_spec())
    apply_bridges_to_nodes([node], _status(
        tools_exported=47, paid_invokes=12, receipts_issued=12, budget_rejections=2))

    assert node["status"] == "active"
    assert node["metrics"]["paid_invokes"] == 12
    assert node["metrics"]["budget_rejections"] == 2
    assert node["bridges_live"]["instrumented"] is True


def test_a_measured_zero_is_kept():
    """The mirror image of the offline rule: 0 reported by a real counter IS a measurement."""
    node = dict(bridges_node_spec())
    apply_bridges_to_nodes([node], _status(paid_invokes=0, budget_rejections=0))

    assert node["metrics"]["paid_invokes"] == 0
    assert node["bridges_live"]["instrumented"] is True


def test_a_partially_instrumented_payload_reports_what_is_missing():
    node = dict(bridges_node_spec())
    apply_bridges_to_nodes([node], _status(paid_invokes=5))

    assert node["metrics"] == {"paid_invokes": 5}
    assert "paid_invokes" not in node["bridges_live"]["unmeasured"]
    assert "receipts_issued" in node["bridges_live"]["unmeasured"]


def test_a_malformed_counter_is_unmeasured_not_zero():
    node = dict(bridges_node_spec())
    apply_bridges_to_nodes([node], _status(paid_invokes="lots", receipts_issued=-3,
                                           budget_rejections=True))

    counters = node["bridges_live"]["counters"]
    assert counters == {}
    for bad in ("paid_invokes", "receipts_issued", "budget_rejections"):
        assert bad in node["bridges_live"]["unmeasured"]


def test_a_reachable_endpoint_with_no_counters_is_idle_not_active():
    """Reaching it proves something runs; it still produced no figure."""
    node = dict(bridges_node_spec())
    apply_bridges_to_nodes([node], _status())

    assert node["status"] == "idle"
    assert node["metrics"] == {}
    assert node["bridges_live"]["reason"] == REASON_NO_COUNTERS


def test_undeclared_settlement_defaults_to_simulated():
    """UNI settlement moves nothing. Guessing "real" is the harmful direction, so we never do."""
    node = dict(bridges_node_spec())
    apply_bridges_to_nodes([node], _status(paid_invokes=3, spend_usd=1.25))

    settlement = node["bridges_live"]["settlement"]
    assert settlement["simulated"] is True
    assert settlement["moves_real_value"] is False
    assert settlement["declared"] is False


def test_declared_real_settlement_is_reported_as_such():
    node = dict(bridges_node_spec())
    apply_bridges_to_nodes([node], _status(
        paid_invokes=3, spend_usd=1.25,
        settlement={"mode": "base", "moves_real_value": True}))

    settlement = node["bridges_live"]["settlement"]
    assert settlement["mode"] == "base"
    assert settlement["moves_real_value"] is True
    assert settlement["simulated"] is False


def test_money_never_enters_the_metric_readout():
    """The node's metric strip has nowhere to print a settlement mode, so an amount must not go
    there — only into the detail panel, which renders the two together."""
    node = dict(bridges_node_spec())
    apply_bridges_to_nodes([node], _status(paid_invokes=3, spend_usd=1.25))

    assert "spend_usd" not in node["metrics"]
    assert node["bridges_live"]["spend_usd"] == 1.25


# ── addressable by name ───────────────────────────────────────────────────────


@pytest.mark.parametrize("question", [
    "show bridges",
    "покажи бриджи",
    "где мосты?",
    "muestra los puentes",
    "montre les ponts",
    "显示桥接",
    "show me the langchain tools",
])
def test_the_viewer_can_focus_it_by_name(question):
    from ai_nav_actions import resolve_nav_actions

    actions = resolve_nav_actions(question)
    assert actions, f"{question!r} produced no focus action"
    assert actions[0]["type"] == "focus_node"
    assert actions[0]["node_id"] == "bridges"


def test_the_assistant_can_see_it_in_a_busy_graph():
    """The prompt caps its node list; an uncapped satellite gets answered as nonexistent."""
    import json

    from ai_assistant import build_live_context

    filler = [{"id": f"filler{i}", "label": f"F{i}", "group": "g"} for i in range(200)]
    payload = json.loads(build_live_context(
        {"nodes": filler + [{"id": "bridges", "label": "Bridges", "group": "core"}]}, mode="real"))
    assert "bridges" in {n["id"] for n in payload["nodes"]}
