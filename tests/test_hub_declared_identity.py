"""Identity comes from the hub, which got it from the operator's pin.

The monitor kept five hand-written tables mapping hosts and name prefixes to node ids, a
sixth copy in the frontend that had already drifted, and a transcribed list of reserved ids
that stopped six oracles short. The hub answers that question now — from
`federation_seeds.json`, where the operator wrote it next to the key they vouched for — and
these pin that the monitor believes the answer, believes it from ONE source, and keeps the
tables only for what no hub can answer.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

import pytest

import hub_discovery
from canonical_peers import canonical_node_id_for_peer


def test_the_hubs_answer_beats_every_local_table():
    """A satellite reachable at a host no table knows still folds onto its own node."""
    assert canonical_node_id_for_peer({
        "canonical_id": "skopos",
        "url": "https://skopos-2.example",
        "label": "something else entirely",
    }) == "skopos"


def test_without_an_answer_the_tables_still_work():
    """The residue: ARGUS, DIOSCURI, HELIOS and WARDEN publish no well-known at all, so no
    hub can ever answer for them."""
    assert canonical_node_id_for_peer({"url": "https://momus.modelmarket.dev"}) == "momus"


def test_a_stranger_naming_itself_after_us_is_still_a_stranger():
    assert canonical_node_id_for_peer({
        "url": "https://stranger.example", "label": "ATLAS", "name": "atlas",
    }) is None


def test_identity_is_only_believed_from_our_own_hub():
    """A peer list republished by ANOTHER hub is a stranger's opinion about our naming.

    The flag is an argument rather than a lookup precisely so this cannot drift: a caller
    has to say where the dict came from.
    """
    src = inspect.getsource(hub_discovery._build_peer_node)
    assert "trust_declared_identity" in src
    assert 'peer.get("canonical_id")' in src
    body = src[src.index("if trust_declared_identity"):]
    assert 'probe["canonical_id"]' in body, "the id must only be read behind the flag"

    children = inspect.getsource(hub_discovery._peer_hub_children)
    assert "canonical_id" not in children, (
        "another hub's peer list must never supply identity"
    )


def test_reserved_ids_are_derived_from_the_map():
    """The transcribed list stopped at `percola`, leaving six oracle ids claimable."""
    from ecosystem_layout import NODE_POSITIONS
    from oracle_family import ORACLE_FAMILY, oracle_node_id

    for slug in ("sortes", "gauss", "aestus", "betti", "kantor", "fourier"):
        assert oracle_node_id(slug) in hub_discovery._RESERVED_IDS, slug
    assert {oracle_node_id(o["slug"]) for o in ORACLE_FAMILY} <= hub_discovery._RESERVED_IDS
    assert set(NODE_POSITIONS) <= hub_discovery._RESERVED_IDS, (
        "every node the map draws must be unclaimable by a discovered peer"
    )


def test_a_node_the_tables_never_learned_folds_with_no_monitor_edit():
    """The whole point: the map learns a peer's identity from the hub, not from a code edit.

    WARDEN has a node on this map and no host rule that can reach it — by URL alone the
    tables answer None. With the hub's answer attached it folds, and nobody edited a table
    to make that happen.
    """
    from ecosystem_layout import NODE_POSITIONS

    assert "warden" in NODE_POSITIONS
    somewhere_new = {"url": "https://warden-relocated.example", "label": "WARDEN"}
    assert canonical_node_id_for_peer(somewhere_new) is None
    assert canonical_node_id_for_peer({**somewhere_new, "canonical_id": "warden"}) == "warden"


def test_an_answer_naming_a_node_the_map_never_draws_is_declined():
    """Self-expanding, not self-inventing.

    A hub — ours after a bad seed edit, or somebody else's — must not be able to mint a
    planet or rename one by assertion. The live case is benign: the oracle-family endpoint
    is seeded as `oracle_family`, a name no node carries, so the answer is declined and the
    host rules fold it exactly as before.
    """
    assert canonical_node_id_for_peer({
        "canonical_id": "brand-new-thing", "url": "https://stranger.example",
    }) is None
    assert canonical_node_id_for_peer({
        "canonical_id": "oracle_family", "url": "https://oracles.modelmarket.dev/family",
    }) == "oracle-platon"


def test_the_declined_answer_cannot_rename_an_existing_node():
    """A wrong id must not move a peer onto somebody else's planet either — it is declined,
    and the peer folds by what this map itself knows about the URL."""
    assert canonical_node_id_for_peer({
        "canonical_id": "not-a-node", "url": "https://momus.modelmarket.dev",
    }) == "momus"
