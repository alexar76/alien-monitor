"""WHICH chain the monitor reads — and the label it puts on what it shows.

The rule the operator stated, and the one the map already followed for its nodes
(`should_build_chain_context`):

  * the bubble (ALIEN_MODE=universe) always reads its own private Anvil;
  * a LIVE monitor with the crypto switch OFF reads the bubble too — an off switch is not a
    reason to show an empty explorer, and it must never touch a public chain;
  * a LIVE monitor with crypto ON reads THE EVM NETWORK IN SETTINGS. Today that is Base; it
    can be any network chain_net knows, and nothing here may assume Base.

The scanner did none of this: all three routes hardcoded `"base"` and then took whatever
`ALIEN_EVM_RPC` named — a chain-agnostic override that in every deployment points at the local
Anvil. So a panel headed "Base" was rendering chain 31337.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import chain_metrics  # noqa: E402
from chain_scan import scan_chain  # noqa: E402

ANVIL = "http://127.0.0.1:8545"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in ("ALIEN_MODE", "AIFACTORY_CRYPTO_ENABLED", "ALIEN_EVM_RPC", "EVM_RPC",
                "EVM_RPC_URL", "AIMARKET_PAYMENT_CHAIN", "ALIEN_EVM_CHAIN",
                "AIMARKET_NFT_CHAIN", "AIMARKET_NFT_CHAIN_RPC", "ALIEN_UNI_CHAIN_ID"):
        monkeypatch.delenv(key, raising=False)


def _live(monkeypatch, *, crypto: str, chain: str = "base"):
    monkeypatch.setenv("ALIEN_MODE", "real")
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", crypto)
    monkeypatch.setenv("AIMARKET_PAYMENT_CHAIN", chain)
    monkeypatch.setenv("ALIEN_EVM_RPC", ANVIL)   # the bubble's node, as on the live host


def test_live_with_crypto_off_reads_the_bubble(monkeypatch):
    _live(monkeypatch, crypto="0")
    src = chain_metrics.chain_source()
    assert src["source"] == "uni-bubble"
    assert src["urls"] == [ANVIL]
    assert src["chain_id"] == 31337 and src["name"] == "UNI Anvil"
    assert src["crypto_enabled"] is False


def test_live_with_crypto_on_reads_the_network_in_settings(monkeypatch):
    _live(monkeypatch, crypto="1")
    src = chain_metrics.chain_source()
    assert src["source"] == "settings-network"
    assert src["chain"] == "base" and src["chain_id"] == 8453
    # The chain-agnostic override is the bubble's; it may not stand in for the settings network.
    assert ANVIL not in src["urls"]
    assert src["urls"] and all(u.startswith("https://") for u in src["urls"])


def test_the_settings_network_is_not_assumed_to_be_base(monkeypatch):
    """"сейчас на проде бэйз, но может быть любая" — the chain comes from settings, always."""
    _live(monkeypatch, crypto="1", chain="ethereum")
    src = chain_metrics.chain_source()
    assert src["chain"] == "ethereum" and src["chain_id"] == 1
    assert src["urls"], "no endpoints resolved for the configured network"


def test_a_chain_scoped_override_still_wins_for_its_own_chain(monkeypatch):
    """An operator's own node is configured per chain, so it cannot be mistaken for another."""
    _live(monkeypatch, crypto="1")
    monkeypatch.setenv("AIMARKET_NFT_CHAIN", "base")
    monkeypatch.setenv("AIMARKET_NFT_CHAIN_RPC", "https://base.my-node.example")
    assert chain_metrics.chain_source()["urls"][0] == "https://base.my-node.example"


def test_the_bubble_reads_its_own_anvil_whatever_the_switch_says(monkeypatch):
    for crypto in ("0", "1"):
        monkeypatch.setenv("ALIEN_MODE", "universe")
        monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", crypto)
        monkeypatch.setenv("ALIEN_EVM_RPC", ANVIL)
        src = chain_metrics.chain_source()
        assert src["source"] == "uni-bubble" and src["urls"] == [ANVIL]
        assert src["realm"] == "uni"


def test_an_unconfigured_bubble_stays_local_instead_of_reaching_mainnet(monkeypatch):
    """chain_net's presets are public endpoints. Falling through to them with crypto off is
    the one outcome this policy exists to prevent."""
    monkeypatch.setenv("ALIEN_MODE", "universe")
    src = chain_metrics.chain_source()
    assert src["urls"] == [chain_metrics.UNI_DEFAULT_RPC]
    assert all("127.0.0.1" in u for u in src["urls"])


def test_the_crypto_switch_has_exactly_one_definition(monkeypatch):
    """main.py mirrored the predicate; two answers to "is crypto on" is how the scanner and
    the map end up describing different chains."""
    import main

    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
    assert main.crypto_enabled() is chain_metrics.crypto_enabled() is True
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "no")
    assert main.crypto_enabled() is chain_metrics.crypto_enabled() is False


def test_every_scan_says_which_network_it_is_showing(monkeypatch):
    """The reader must be able to tell, at a glance, whose transactions these are."""
    import chain_scan

    _live(monkeypatch, crypto="0")
    monkeypatch.setattr(chain_scan, "_rpc", lambda *a, **k: _answer(*a))
    out = asyncio.run(scan_chain(ANVIL, realm="live", limit=1))
    assert out["network"]["name"] == "UNI Anvil"
    assert out["network"]["source"] == "uni-bubble"
    assert out["network"]["crypto_enabled"] is False
    # deliberate, so it is NOT dressed up as a misconfiguration
    assert out["chain_mismatch"] is None


async def _answer(_client, _url, method, params):
    return {"eth_chainId": "0x7a69", "eth_blockNumber": "0x1",
            "eth_getBlockByNumber": {"timestamp": "0x66f00000", "transactions": []}}.get(method)


def test_a_public_chain_is_not_walked_sixty_blocks_deep(monkeypatch):
    """A bubble block is a handful of our own transactions; a Base block is hundreds of
    strangers' over somebody else's free endpoint. Sixty of those per panel open is megabytes."""
    import chain_scan

    assert chain_scan._block_span({"source": "uni-bubble"}) == chain_scan.MAX_BLOCK_SPAN
    assert chain_scan._block_span({"source": "settings-network"}) == chain_scan.PUBLIC_BLOCK_SPAN
    assert chain_scan.PUBLIC_BLOCK_SPAN < chain_scan.MAX_BLOCK_SPAN
    # an operator who set the span explicitly gets exactly that, on any chain
    monkeypatch.setenv("ALIEN_CHAIN_SCAN_SPAN", "60")
    assert chain_scan._block_span({"source": "settings-network"}) == chain_scan.MAX_BLOCK_SPAN


# --- where the money lands is the HUB's fact, not a hand-copied env ----------------------

def test_a_published_dev_account_is_never_shown_as_the_recipient_on_a_public_chain(monkeypatch):
    """The LIVE monitor advertised Anvil account 0 as the recipient of real money for as long as
    that env line survived a copy-paste. The hub refuses to RUN that way (is_dev_chain_address);
    the map must not quietly claim it either."""
    _live(monkeypatch, crypto="1")
    monkeypatch.setenv("ALIEN_HUB_RECIPIENT_LOOKUP", "0")
    monkeypatch.setenv("AIMARKET_PAYMENT_RECIPIENT", "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266")
    assert chain_metrics.payment_recipient() == ""
    warn = chain_metrics.recipient_warning()
    assert "Anvil" in warn and "Base" in warn, "the operator must be told why it is blank"


def test_the_same_account_is_correct_inside_the_bubble(monkeypatch):
    """It is the bubble's own chain: those accounts ARE the participants there."""
    monkeypatch.setenv("ALIEN_MODE", "universe")
    monkeypatch.setenv("ALIEN_HUB_RECIPIENT_LOOKUP", "0")
    monkeypatch.setenv("AIMARKET_PAYMENT_RECIPIENT", "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266")
    assert chain_metrics.payment_recipient().lower().startswith("0xf39f")
    assert chain_metrics.recipient_warning() == ""


def test_the_hub_wins_over_the_env(monkeypatch):
    """One owner: the hub knows where its deposits settle, the monitor only draws it."""
    _live(monkeypatch, crypto="1")
    monkeypatch.setenv("AIMARKET_PAYMENT_RECIPIENT", "0x1111111111111111111111111111111111111111")
    monkeypatch.setattr(chain_metrics, "_hub_declared_recipient",
                        lambda: "0x2222222222222222222222222222222222222222")
    assert chain_metrics.payment_recipient() == "0x2222222222222222222222222222222222222222"


def test_a_hub_that_does_not_publish_one_leaves_the_env_in_charge(monkeypatch):
    _live(monkeypatch, crypto="1")
    monkeypatch.setenv("AIMARKET_PAYMENT_RECIPIENT", "0x1111111111111111111111111111111111111111")
    monkeypatch.setattr(chain_metrics, "_hub_declared_recipient", lambda: "")
    assert chain_metrics.payment_recipient() == "0x1111111111111111111111111111111111111111"


def test_the_hub_lookup_never_breaks_the_panel(monkeypatch):
    def boom():
        raise RuntimeError("hub unreachable")

    monkeypatch.setattr(chain_metrics, "_fetch_hub_recipient", boom)
    monkeypatch.delenv("ALIEN_HUB_RECIPIENT_LOOKUP", raising=False)
    assert chain_metrics._hub_declared_recipient() == ""
