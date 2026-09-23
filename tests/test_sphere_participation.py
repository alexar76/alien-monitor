"""Who earns a sphere on the map, and why.

The rule, in three tiers with the line at the second hop:

  hop 0  our own hub and providers — always drawn: we show what we deploy.
  hop 1  a hub we federate with, or one knocking for admission — ALWAYS drawn. A hub is a
         routing relationship, not a shop window; zero capabilities can be correct (an
         aggregator of pure re-exports filters to zero) and a hub awaiting admission is
         empty BECAUSE it is waiting.
  hop 2  inherited from a stranger — drawn only if it is part of this economy, by ANY of
         three routes: it supplies (a capability, priced or free), it buys (it has
         transacted with us), or it holds an on-chain address — an escrow or a settlement
         wallet — that WE verified against the chain (see test_foreign_contracts).

Measured on `monitor.attestedmemory.net` 2026-09-07: `Competing Lab Hub` at hop 2 with
zero capabilities and no transaction history — a name copied out of another hub's document.
Testing the catalogue alone would have been wrong the other way: a service built with our
tools that buys hourly and lists nothing is as much a participant as any seller.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import hub_discovery as hd


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch):
    hd._ECONOMY_PARTICIPANTS.clear()
    monkeypatch.delenv("ALIEN_KEEP_SILENT_NODES", raising=False)
    yield
    hd._ECONOMY_PARTICIPANTS.clear()


def _child(node_id: str, *, caps: int, hop: int = 2, url: str = "", role: str = "peer") -> dict:
    return {
        "id": node_id, "label": node_id, "hop": hop, "role": role,
        "url": url, "metrics": {"capabilities": caps} if caps else {},
    }


def _filter(nodes: list[dict]) -> set[str]:
    """Call the PRODUCTION rule — never a copy of it.

    This used to re-implement the tiers inline, which is a test that keeps passing while
    the code it guards moves: the on-chain condition was added to `deserves_sphere` and a
    hand-copied filter here would have known nothing about it.
    """
    keep_anyway = hd._explicitly_kept_nodes()
    return {node["id"] for node in nodes if hd.deserves_sphere(node, keep_anyway)}


class TestSuppliers:
    def test_a_second_hop_node_that_sells_is_drawn(self):
        assert _filter([_child("themis", caps=1)]) == {"themis"}

    def test_a_second_hop_node_that_sells_nothing_is_not(self):
        assert _filter([_child("competing", caps=0)]) == set()


class TestConsumers:
    def test_a_customer_earns_its_sphere_with_an_empty_catalogue(self):
        """Our own customers must not be hidden by a supply-side-only test."""
        hd.note_economy_participants(["https://buyer.example.dev"])
        node = _child("fedchild:https://buyer.example.dev", caps=0,
                      url="https://buyer.example.dev")
        assert _filter([node]) == {node["id"]}

    def test_matching_ignores_scheme_and_trailing_slash(self):
        hd.note_economy_participants(["http://Buyer.Example.dev/"])
        node = _child("x", caps=0, url="https://buyer.example.dev")
        assert _filter([node]) == {"x"}

    @pytest.mark.parametrize("noise", ["anonymous", "local", "", "   "])
    def test_placeholder_consumers_make_nobody_a_participant(self, noise):
        hd.note_economy_participants([noise])
        assert _filter([_child("x", caps=0, url="https://buyer.example.dev")]) == set()

    def test_the_registry_remembers_past_customers(self):
        """An event that scrolled out of the 20-row feed window is still history."""
        hd.note_economy_participants(["https://buyer.example.dev"])
        hd.note_economy_participants(["https://other.example.dev"])   # a later tick
        node = _child("x", caps=0, url="https://buyer.example.dev")
        assert _filter([node]) == {"x"}


class TestHubsAndOurOwn:
    @pytest.mark.parametrize("hop", [0, 1])
    def test_our_shelf_and_first_hop_hubs_are_always_drawn(self, hop):
        """A hub is always shown — zero can be correct, and a knock is not a catalogue."""
        assert _filter([_child("hub-x", caps=0, hop=hop)]) == {"hub-x"}

    def test_a_pending_hub_is_drawn_with_nothing_at_all(self):
        assert _filter([_child("pending:https://charon.example", caps=0, hop=1)]) \
            == {"pending:https://charon.example"}


class TestDeliberateOverride:
    def test_an_operator_can_keep_a_silent_node(self, monkeypatch):
        """A rule needs a deliberate exception, or the first one deletes the rule."""
        monkeypatch.setenv("ALIEN_KEEP_SILENT_NODES", "fedchild:https://quiet.example")
        node = _child("fedchild:https://quiet.example", caps=0)
        assert _filter([node]) == {node["id"]}

    def test_the_override_is_exact_not_a_prefix(self, monkeypatch):
        monkeypatch.setenv("ALIEN_KEEP_SILENT_NODES", "fedchild:https://quiet.example")
        assert _filter([_child("fedchild:https://quiet.example.evil", caps=0)]) == set()


class TestOnChainEvidence:
    """The third route in: money it can be SEEN to move, on a chain we read ourselves.

    This is the condition that lets the universe expand past our own ledger. A hub nobody
    here has traded with, that lists nothing in our catalogue, but whose escrow holds code
    and has transactions, is running an economy — and the sphere it earns opens onto those
    transactions, so the reader is not taking our word for it either.
    """

    def test_a_verified_contract_earns_a_sphere_with_no_caps_and_no_trades(self):
        node = _child("fedchild:https://stranger.example", caps=0)
        node["contracts"] = {"verified": True, "entries": [{"role": "escrow", "verified": True}]}
        assert _filter([node]) == {node["id"]}

    def test_a_merely_DECLARED_contract_earns_nothing(self):
        """An address anybody can type is not evidence. `verified` comes from the chain."""
        node = _child("fedchild:https://claims.example", caps=0)
        node["contracts"] = {
            "verified": False,
            "entries": [{"role": "escrow", "address": "0x" + "1" * 40, "verified": False}],
        }
        assert _filter([node]) == set()

    def test_an_empty_contracts_block_earns_nothing(self):
        node = _child("fedchild:https://empty.example", caps=0)
        node["contracts"] = {}
        assert _filter([node]) == set()

    def test_on_chain_evidence_does_not_rescue_our_own_omissions(self):
        """hop 0/1 are drawn regardless; the flag must not be what makes them appear."""
        hub = _child("peer_hub:x", caps=0, hop=1)
        assert _filter([hub]) == {hub["id"]}
