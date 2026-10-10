"""Event topics must be derivable from the deployed contract's own declarations.

This exists because of a bug that lived a long time and could not be seen from the tests that
covered the code around it. `EV_CHANNEL_SETTLED` was a hand-copied hash of
`ChannelSettled(bytes32,uint256,uint256,address)` while `AIMarketEscrow.sol` declares five
parameters (`usedRecipient` *and* `refundRecipient`). The getLogs filter therefore never
matched a settlement: every settled channel kept counting as open, forever, and the number the
monitor showed drifted further from reality every day.

The existing tests could not catch it — `test_onchain_reads.py` uses the constants as opaque
dict keys, so a wrong hash and a right one behave identically. The only test that can catch it
is one that reads the Solidity.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from eth_utils import keccak

import sys
BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

import onchain_reads as oc  # noqa: E402

ESCROW_SOL = (Path(__file__).resolve().parents[2]
              / "contracts" / "evm" / "src" / "AIMarketEscrow.sol")


def _declared_signature(name: str) -> str:
    """The canonical event signature, read out of the Solidity declaration."""
    src = ESCROW_SOL.read_text(encoding="utf-8")
    start = src.index(f"event {name}(")
    end = src.index(");", start)
    body = src[start + len(f"event {name}("):end]
    # Strip comments BEFORE splitting on commas: ChannelRefunded's trailing comment is
    # `// "safety_blocked", "provider_error", "user_cancelled"`, and splitting first turns
    # those quoted words into two extra parameters — which is how the first version of this
    # helper "proved" a signature that no contract declares.
    body = re.sub(r"//[^\n]*", "", body)
    params = []
    for part in body.split(","):
        part = part.strip()
        if not part:
            continue
        params.append(part.split()[0])   # the type is the first token
    return f"{name}({','.join(params)})"


@pytest.mark.skipif(
    not ESCROW_SOL.is_file(),
    reason="AIMarketEscrow.sol lives in monorepo contracts/ — absent from alien-monitor satellite",
)
@pytest.mark.parametrize("key,event_name", [
    ("opened", "ChannelOpened"),
    ("settled", "ChannelSettled"),
    ("refunded", "ChannelRefunded"),
    ("expired", "ChannelExpiredAndSettled"),
])
def test_signature_matches_the_contract(key, event_name):
    assert oc.EVENT_SIGNATURES[key] == _declared_signature(event_name), (
        f"{event_name} was changed in Solidity and this module still describes the old shape; "
        f"the getLogs filter will silently stop matching it")


@pytest.mark.parametrize("key,constant", [
    ("opened", "EV_CHANNEL_OPENED"),
    ("settled", "EV_CHANNEL_SETTLED"),
    ("refunded", "EV_CHANNEL_REFUNDED"),
    ("expired", "EV_CHANNEL_EXPIRED"),
])
def test_topic_is_derived_not_transcribed(key, constant):
    expected = "0x" + keccak(oc.EVENT_SIGNATURES[key].encode()).hex()
    assert getattr(oc, constant) == expected


def test_the_settled_topic_is_not_the_old_broken_one():
    """The specific regression, named. The old value is the hash of a four-parameter
    ChannelSettled that this contract has never declared."""
    broken = "0x" + keccak(b"ChannelSettled(bytes32,uint256,uint256,address)").hex()
    assert oc.EV_CHANNEL_SETTLED != broken
    assert oc.EV_CHANNEL_SETTLED == "0x" + keccak(
        b"ChannelSettled(bytes32,uint256,uint256,address,address)").hex()


def test_every_filtered_topic_is_distinct():
    """A duplicate would silently merge two counters."""
    topics = [oc.EV_CHANNEL_OPENED, oc.EV_CHANNEL_SETTLED, oc.EV_CHANNEL_REFUNDED,
              oc.EV_CHANNEL_EXPIRED]
    assert len(set(topics)) == len(topics)
