"""Whose ecosystem is this Monitor allowed to draw?

The live failure this covers: independentai.network ran the Monitor against its own hub and
got forty-five of OUR nodes as its local shelf — METIS, MOMUS, ATLAS, GAIA, eighteen oracles
— while the three services its hub actually owns were small planets in orbit. Fifteen status
pollers then went out over the internet to `*.modelmarket.dev` every thirty seconds to keep
somebody else's map warm.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in (
        "ALIEN_ECOSYSTEM_PROFILE",
        "ALIEN_ECOSYSTEM_FILE",
        "ALIEN_PUBLIC_HUB_URL",
        "HUB_PUBLIC_URL",
        "AIMARKET_PUBLIC_HUB_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    import deployment_profile

    deployment_profile.reset_cache()
    yield
    deployment_profile.reset_cache()


class TestProfileDetection:
    def test_a_deployment_that_said_nothing_keeps_the_builtin_shelf(self):
        """Local dev and the test suite publish no address — nothing changes for them."""
        from deployment_profile import AICOM, owns_builtin_shelf, profile_name

        assert profile_name() == AICOM
        assert owns_builtin_shelf() is True

    @pytest.mark.parametrize(
        "public",
        [
            "https://modelmarket.dev",
            "https://uni.modelmarket.dev",
            "https://hunt.modelmarket.dev",
            "https://magic-ai-factory.com",
            "http://localhost:9083",
        ],
    )
    def test_our_own_addresses_keep_the_shelf(self, monkeypatch, public):
        from deployment_profile import owns_builtin_shelf

        monkeypatch.setenv("ALIEN_PUBLIC_HUB_URL", public)
        assert owns_builtin_shelf() is True

    def test_a_declared_foreign_hub_does_not_get_our_shelf(self, monkeypatch):
        from deployment_profile import GENERIC, owns_builtin_shelf, profile_name

        monkeypatch.setenv("ALIEN_PUBLIC_HUB_URL", "https://independentai.network/hub")
        assert profile_name() == GENERIC
        assert owns_builtin_shelf() is False

    def test_an_operator_can_say_so_explicitly(self, monkeypatch):
        from deployment_profile import owns_builtin_shelf

        monkeypatch.setenv("ALIEN_PUBLIC_HUB_URL", "https://modelmarket.dev")
        monkeypatch.setenv("ALIEN_ECOSYSTEM_PROFILE", "generic")
        assert owns_builtin_shelf() is False


class TestTheGenericMap:
    """What somebody else's deployment actually draws before anything is discovered."""

    def test_it_claims_only_what_it_can_assert(self, monkeypatch):
        monkeypatch.setenv("ALIEN_PUBLIC_HUB_URL", "https://independentai.network/hub")
        import main

        nodes, links = main.build_topology()
        assert {n["id"] for n in nodes} == {"hub", "federation"}
        assert all(n.get("hop") == 0 for n in nodes)
        assert links == [{"source": "hub", "target": "federation", "label": "Peer crawl"}]

    def test_not_one_of_our_satellites_survives(self, monkeypatch):
        monkeypatch.setenv("ALIEN_PUBLIC_HUB_URL", "https://independentai.network/hub")
        import main

        nodes, _links = main.build_topology()
        ours = {"metis", "momus", "atlas", "gaia", "skopos", "logos", "themis", "basanos"}
        assert not ours & {n["id"] for n in nodes}
        assert not any("modelmarket.dev" in str(n.get("url") or "") for n in nodes)

    def test_the_builtin_shelf_is_still_there_for_us(self, monkeypatch):
        monkeypatch.setenv("ALIEN_PUBLIC_HUB_URL", "https://modelmarket.dev")
        import main

        nodes, _links = main.build_topology()
        ids = {n["id"] for n in nodes}
        assert {"metis", "momus", "atlas", "gaia", "factory", "hub"} <= ids

    def test_an_operator_declares_their_own_containers(self, monkeypatch, tmp_path):
        """A hub's signed `ecosystem.nodes` covers what it SELLS. The forty containers
        beside it that never entered the federation are what its operator wants to see."""
        profile = tmp_path / "own.yaml"
        profile.write_text(
            "ecosystem:\n"
            "  - id: my-metis\n"
            "    label: My METIS\n"
            "    group: cognition\n"
            "    url: https://example.invalid/metis\n"
            "  - id: my-oracle\n"
            "    label: My Oracle\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("ALIEN_PUBLIC_HUB_URL", "https://independentai.network/hub")
        monkeypatch.setenv("ALIEN_ECOSYSTEM_FILE", str(profile))
        import deployment_profile
        import main

        deployment_profile.reset_cache()
        nodes, links = main.build_topology()
        by_id = {n["id"]: n for n in nodes}
        assert {"hub", "federation", "my-metis", "my-oracle"} == set(by_id)
        assert by_id["my-metis"]["label"] == "My METIS"
        assert by_id["my-oracle"]["group"] == "core"  # sensible default, not a crash
        # Placed in the hub's own orbit, not stacked on the origin.
        for nid in ("my-metis", "my-oracle"):
            p = by_id[nid]["position"]
            assert math.hypot(p["x"], p["y"], p["z"]) > 5.0
        assert {"my-metis", "my-oracle"} <= {l["target"] for l in links}


class TestNobodyElsesInfrastructureIsClaimed:
    def test_a_foreign_peer_is_never_folded_onto_our_node_ids(self, monkeypatch):
        """`atlas.modelmarket.dev` resolves to our `atlas` — but only on a map that draws
        it. Elsewhere the fold names a stranger's service after ours and hangs an edge on
        a node the graph does not contain."""
        from canonical_peers import canonical_node_id_for_peer

        peer = {"id": "x", "label": "ATLAS", "url": "https://atlas.modelmarket.dev"}
        monkeypatch.setenv("ALIEN_PUBLIC_HUB_URL", "https://modelmarket.dev")
        assert canonical_node_id_for_peer(peer) == "atlas"
        monkeypatch.setenv("ALIEN_PUBLIC_HUB_URL", "https://independentai.network/hub")
        assert canonical_node_id_for_peer(peer) is None

    def test_our_apex_hub_does_not_become_somebody_elses_hub(self, monkeypatch):
        """`modelmarket.dev` maps to the id `hub` — the centre of the map. On a foreign
        deployment that would fold OUR hub into THEIR own sun."""
        from canonical_peers import canonical_node_id_for_peer

        peer = {"id": "mm", "label": "modelmarket.dev", "url": "https://modelmarket.dev"}
        monkeypatch.setenv("ALIEN_PUBLIC_HUB_URL", "https://independentai.network/hub")
        assert canonical_node_id_for_peer(peer) is None


class TestNobodyElsesMoney:
    """Turning crypto on must not point a foreign map at OUR contracts.

    `chain_net` ships the address registry for the deployment WE run on Base — the escrow,
    the lottery, the capability NFT. `chain_metrics.configured_contracts` falls back to it
    whenever the operator has not set an address, so a Monitor pointed at somebody else's
    hub, with crypto enabled, would have read our escrow's balance and drawn it as theirs.
    """

    def test_our_registry_does_not_travel(self, monkeypatch):
        from chain_metrics import our_chain_addresses

        monkeypatch.setenv("ALIEN_PUBLIC_HUB_URL", "https://modelmarket.dev")
        ours = our_chain_addresses("base")
        assert ours.get("AIMarketEscrow"), "our own map still needs its contracts"

        monkeypatch.setenv("ALIEN_PUBLIC_HUB_URL", "https://independentai.network/hub")
        assert our_chain_addresses("base") == {}

    def test_an_operator_still_names_their_own(self, monkeypatch):
        """The gate removes OUR defaults; it must not remove the operator's own answer."""
        import importlib

        import chain_net

        monkeypatch.setenv("ALIEN_PUBLIC_HUB_URL", "https://independentai.network/hub")
        monkeypatch.setenv("AIMARKET_ESCROW_EVM_ADDRESS", "0x1111111111111111111111111111111111111111")
        import chain_metrics

        importlib.reload(chain_net)
        importlib.reload(chain_metrics)
        got = chain_metrics.configured_contracts()
        assert got["escrow_evm"] == "0x1111111111111111111111111111111111111111"
        assert got["nft_evm"] is None, "an address nobody set must stay unset, not become ours"
        importlib.reload(chain_net)
        importlib.reload(chain_metrics)

    def test_a_foreign_map_falls_back_to_no_escrow_rather_than_ours(self, monkeypatch):
        import importlib

        import chain_metrics
        import chain_net

        for var in ("AIMARKET_ESCROW_EVM_ADDRESS", "AIFACTORY_AI_MARKET_CONTRACT",
                    "AIMARKET_NFT_CONTRACT", "AIMARKET_NFT_CONTRACT_ADDRESS"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("ALIEN_PUBLIC_HUB_URL", "https://independentai.network/hub")
        importlib.reload(chain_net)
        importlib.reload(chain_metrics)
        got = chain_metrics.configured_contracts()
        assert got["escrow_evm"] is None and got["nft_evm"] is None
        importlib.reload(chain_net)
        importlib.reload(chain_metrics)
