"""Every ecosystem component must be a node in EVERY monitor mode.

Written because a satellite went missing in exactly one mode and nobody noticed until the AI assistant
told a user that MOMUS "is not part of the ecosystem". Three separate gaps produced that one answer:

  1. `universe` mode builds its graph from the simulator's entities, not from build_topology(), and
     nothing seeded momus/treasury there;
  2. the apply_*_graph helpers only DECORATE an existing node — they return early when it is absent,
     so a missing node stays missing and silently;
  3. the assistant's prompt truncated its node list without saying so, turning "I cannot see it" into
     "it does not exist".

Each of those is individually reasonable and together they lied to a user. So the invariant is checked
directly and per mode: the component set is declared once, and every mode must contain all of it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

# The components a viewer must be able to find on the map, in any mode. Add a satellite here when you
# add it to the ecosystem — this list failing is the point.
REQUIRED = (
    "hub", "factory", "mesh", "acex", "lottery",
    "argus", "dioscuri", "helios", "metis", "skopos",
    "gaia", "atlas", "momus", "treasury", "logos",
    # The third paid invoke channel. Present here for the same reason as its siblings, and
    # regardless of the fact that it reports no figures: "we cannot measure this channel" is a
    # fact the map must carry, and it can only carry it if the node exists in every mode.
    "bridges",
    "themis",
    "basanos",
    # The invoke-time firewall. It is a LIBRARY with no host, no port and no /health, which is
    # precisely why it was missing from every mode and why the assistant answered "where is
    # WARDEN?" with "inside ARGUS". A node that has no address still has to be findable.
    "warden",
)

MODES = ("real", "universe", "test")


def _topology_ids() -> set[str]:
    from main import build_topology

    nodes, _links = build_topology()
    return {n.get("id") for n in nodes if isinstance(n, dict)}


def _universe_ids() -> set[str]:
    """The simulator's entities — what `universe` mode actually renders.

    Use the real entry point, `seed_entities()`. Calling the private `_seed_*_entity` helpers one by
    one looked equivalent and was not: most components are seeded INLINE inside that method, so a
    piecemeal call reported every one of them missing. A test that fails for the wrong reason is worse
    than no test — it trains you to ignore it."""
    from universe import VirtualUniverse

    u = VirtualUniverse()
    u.seed_entities()
    return set(u.entities.keys())


@pytest.mark.parametrize("component", REQUIRED)
def test_component_is_in_the_static_topology(component):
    assert component in _topology_ids(), (
        f"{component!r} is missing from build_topology() — it will not appear in real/test mode")


@pytest.mark.parametrize("component", REQUIRED)
def test_component_is_in_the_universe_simulator(component):
    """The gap that actually bit: universe mode ignores build_topology() entirely."""
    ids = _universe_ids()
    assert component in ids, (
        f"{component!r} has no entity in the universe simulator. universe mode renders "
        f"u.entities.values(), and apply_{component}_graph() only decorates a node that already "
        f"exists — so it will be invisible on the map and the assistant will report it as absent.")


def test_the_required_set_matches_the_assistant_priority_list():
    """The assistant caps its node list. Anything in REQUIRED must be in its priority list, or a busy
    graph can push a real component out of the prompt — which is how "it does not exist" happened."""
    from ai_assistant import build_live_context
    import json

    # Flood the graph so only prioritised nodes survive the cap.
    filler = [{"id": f"filler{i}", "label": f"F{i}", "group": "g"} for i in range(200)]
    required_nodes = [{"id": c, "label": c.upper(), "group": "g"} for c in REQUIRED]
    payload = json.loads(build_live_context({"nodes": filler + required_nodes}, mode="real"))
    seen = {n["id"] for n in payload["nodes"]}
    missing = [c for c in REQUIRED if c not in seen]
    assert not missing, f"the assistant would not see {missing} in a busy graph"


@pytest.mark.parametrize("component", REQUIRED)
def test_every_component_can_be_focused_by_name(component):
    """A viewer who names a component must get the camera. A node nobody can address is a node
    nobody can find."""
    from ai_nav_actions import resolve_nav_actions

    actions = resolve_nav_actions(f"show {component}")
    assert actions, f"'show {component}' produced no focus action"
    assert actions[0]["type"] == "focus_node"


def test_no_mode_is_silently_unchecked():
    """If a fourth mode appears, this fails rather than leaving it quietly unverified.

    main.py has no MODES constant, so read the modes it actually branches on: every `mode="..."`
    literal passed to the apply_*_graph helpers."""
    import re

    src = (Path(__file__).resolve().parent.parent / "backend" / "main.py").read_text(encoding="utf-8")
    used = set(re.findall(r'mode="([a-z]+)"', src))
    unverified = used - set(MODES)
    assert not unverified, f"monitor mode(s) nothing here checks: {sorted(unverified)}"
