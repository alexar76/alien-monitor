"""WARDEN node wiring — library layer, landing is the card exit."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from warden_layers import warden_node_spec, warden_topology_links  # noqa: E402
from warden_status import apply_warden_to_nodes, warden_links  # noqa: E402


def test_card_cta_is_the_landing_not_npm():
    spec = warden_node_spec()
    assert spec["url"] == "https://warden.modelmarket.dev"
    assert spec["links"]["landing"] == spec["url"]
    assert spec["links"]["npm"] == "https://www.npmjs.com/package/@aimarket/warden"
    assert spec["links"]["github"].endswith("/warden")


def test_overlay_keeps_landing_as_the_exit():
    nodes = [warden_node_spec()]
    nodes[0]["url"] = "https://www.npmjs.com/package/@aimarket/warden"
    apply_warden_to_nodes(nodes, None)
    assert nodes[0]["url"] == "https://warden.modelmarket.dev"
    assert nodes[0]["links"] == warden_links()
    assert nodes[0]["links"]["landing"] == nodes[0]["url"]


def test_topology_links_feed_host_and_publish_gate():
    edges = {(item["source"], item["target"]) for item in warden_topology_links()}
    assert ("momus", "warden") in edges
    assert ("warden", "argus") in edges
    assert ("themis", "warden") in edges
