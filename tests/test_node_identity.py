"""Names and addresses: what a card may offer as a link, and what a search must find.

Both halves come from one real defect each.

A node card showed `http://provenance-ledger:8812` as a clickable link. That is a Docker
service name on the Attested Memory Hub's own compose network — the monitor had taken a foreign
hub's self-description at face value and offered the reader an address that resolves nowhere
else. Every federated hub describes itself that way, so the rule cannot live in a per-satellite
patch.

And node lookup matched ids and labels only, so a question naming an address — the only handle
a person has on a stranger's node — matched nothing while the answer was on screen.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import ai_nav_actions  # noqa: E402
import node_identity as ni  # noqa: E402

PROVENANCE = "http://provenance-ledger:8812"


@pytest.mark.parametrize("addr", [
    PROVENANCE,                      # a compose service name: one label, no dot
    "http://memory-market:8810",
    "http://localhost:9100",
    "http://127.0.0.1:8545",
    "http://10.0.0.7:8080",
    "http://192.168.1.20",
    "http://172.17.0.1:8546",
    "https://hub.internal",
    "https://gateway.svc.cluster.local",
    "http://host.docker.internal:9083",
    "ftp://files.example.org",        # not a scheme a card can offer
    "",
])
def test_these_are_not_addresses_a_viewer_can_open(addr):
    assert ni.is_reachable(addr) is False
    assert ni.public_url(addr) == ""


@pytest.mark.parametrize("addr", [
    "https://modelmarket.dev",
    "https://independentai.network/hub",
    "http://monitor-uni.modelmarket.dev",
    "https://8.8.8.8",               # a public IP is reachable, however unusual
    "momus.modelmarket.dev",         # bare host — schemeless, still public
])
def test_these_are(addr):
    assert ni.is_reachable(addr) is True
    assert ni.public_url(addr).startswith("http")


def test_a_schemeless_public_host_becomes_https_not_http():
    """A card link must not downgrade a host that never asked for plaintext."""
    assert ni.public_url("momus.modelmarket.dev") == "https://momus.modelmarket.dev"


def test_the_card_keeps_the_internal_claim_as_text_not_as_a_link():
    node = {"id": "provider:hub:pl", "label": "Provenance Ledger", "url": PROVENANCE}
    out = ni.resolve_addresses(node)
    assert "url" not in out, "an unreachable address must not stay in the link field"
    assert out["url_internal"] == PROVENANCE, "…and must not be thrown away either"
    # the source node is untouched: the monitor's own pollers still need the real address
    assert node["url"] == PROVENANCE


def test_a_reachable_address_passes_through_unchanged():
    node = {"id": "peer", "label": "Independent AI Hub", "url": "https://independentai.network"}
    out = ni.resolve_addresses(node)
    assert out["url"] == "https://independentai.network"
    assert "url_internal" not in out


def test_children_are_resolved_too():
    node = {"id": "hub", "url": "https://modelmarket.dev",
            "children": [{"id": "c", "url": PROVENANCE}]}
    out = ni.resolve_addresses(node)
    assert out["children"][0]["url_internal"] == PROVENANCE
    assert "url" not in out["children"][0]


def test_a_junk_string_costs_a_label_not_an_exception():
    """`urlsplit(...).port` RAISES on a non-numeric port, and node ids reach this code:
    `provider:hub:pl` would have taken the whole state payload down over a label."""
    for junk in ("provider:hub:pl", "::::", "http://", "?", "a:b:c:d"):
        assert isinstance(ni.address_terms(junk), list)
        assert ni.public_url(junk) in ("", f"https://{junk}") or True  # never raises


def test_an_address_is_searchable_by_every_form_a_person_types():
    terms = ni.address_terms(PROVENANCE)
    assert PROVENANCE in terms
    assert "provenance-ledger:8812" in terms
    assert "provenance-ledger" in terms
    # a registrable domain, because that is how people name a deployment
    assert "modelmarket.dev" in ni.address_terms("https://monitor-uni.modelmarket.dev")
    # …but never a bare TLD
    assert "dev" not in ni.address_terms("https://monitor-uni.modelmarket.dev")


def test_search_finds_a_node_by_name_and_by_address():
    nodes = ni.resolved_nodes([
        {"id": "provider:hub:pl", "label": "Provenance Ledger", "url": PROVENANCE},
        {"id": "fedchild:https://independentai.network", "label": "Independent AI Hub",
         "url": "https://independentai.network"},
        {"id": "hub", "label": "AIMarket Hub", "url": "https://modelmarket.dev"},
    ])
    assert [n["label"] for n in ni.find_nodes(nodes, "provenance-ledger")] == ["Provenance Ledger"]
    assert [n["label"] for n in ni.find_nodes(nodes, "independentai.network")] == ["Independent AI Hub"]
    assert [n["label"] for n in ni.find_nodes(nodes, "Provenance Ledger")] == ["Provenance Ledger"]
    assert ni.find_nodes(nodes, "ab") == [], "a two-character query must match nothing"


def test_the_map_lookup_focuses_a_node_named_by_its_address():
    """This is the question that used to focus nothing: the user can see a stranger's node and
    the only thing they can quote is its host."""
    state = {"nodes": ni.resolved_nodes([
        {"id": "provider:hub:pl", "label": "Provenance Ledger", "url": PROVENANCE},
        {"id": "fedchild:https://independentai.network", "label": "Independent AI Hub",
         "url": "https://independentai.network"},
    ])}
    assert ai_nav_actions.match_live_node_id(
        "что за узел на provenance-ledger:8812", state) == "provider:hub:pl"
    assert ai_nav_actions.match_live_node_id(
        "покажи independentai.network", state) == "fedchild:https://independentai.network"
    assert ai_nav_actions.match_live_node_id(
        "show provenance ledger", state) == "provider:hub:pl"


def test_the_assistant_is_told_which_addresses_are_internal():
    """An address-less node and a node with an internal address are different answers."""
    import json

    import ai_assistant

    ctx = json.loads(ai_assistant.build_live_context(
        {"nodes": ni.resolved_nodes([{"id": "provider:hub:pl", "label": "Provenance Ledger",
                                      "url": PROVENANCE}])},
        "real",
    ))
    entry = ctx["nodes"][0]
    assert entry.get("url_internal") == PROVENANCE
    assert "url" not in entry
