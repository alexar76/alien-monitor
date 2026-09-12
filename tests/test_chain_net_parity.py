"""alien-monitor is a standalone service, so it vendors a verbatim copy of the canonical
chain-net module. This guard fails the moment the copy drifts, and smoke-tests that the
vendored module loads and selects the default network.
"""
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
VENDORED = REPO / "alien-monitor" / "backend" / "chain_net.py"
CANONICAL = REPO / "aimarket-hub" / "aimarket_hub" / "chain_net.py"


def test_vendored_chain_net_matches_canonical():
    if not CANONICAL.exists():
        pytest.skip("canonical aimarket_hub/chain_net.py not present (trimmed checkout)")
    assert VENDORED.read_text() == CANONICAL.read_text(), (
        "alien-monitor/backend/chain_net.py has drifted from the canonical "
        "aimarket-hub/aimarket_hub/chain_net.py — re-vendor:\n"
        "  cp aimarket-hub/aimarket_hub/chain_net.py alien-monitor/backend/chain_net.py"
    )


def test_vendored_module_loads_and_defaults_to_base(monkeypatch):
    for k in ("AIMARKET_CHAIN", "AIMARKET_NETWORK", "AIMARKET_TESTNET"):
        monkeypatch.delenv(k, raising=False)
    import chain_net as cn  # vendored copy on the backend path

    net = cn.active_network()
    assert net.id == "base" and net.is_evm and net.chain_id == 8453
    assert net.addresses["AIMarketEscrow"].lower() == _registry_escrow()

def _registry_escrow() -> str:
    """The escrow from the deployment registry.

    These two assertions used to pin the address by PREFIX (`startswith("0x0606983")`),
    which is drift that neither the full-address sweep nor the repo-wide drift test can see —
    a 9-character prefix is not an address. The 2026-09-04 escrow redeploy is what surfaced
    it. Compare against the registry so the assertion keeps meaning "the Base demo escrow"
    rather than "one particular deployment of it".
    """
    import json
    from pathlib import Path

    for candidate in (
        Path(__file__).resolve().parents[2] / "config" / "deployments" / "base-mainnet.json",
        Path(__file__).resolve().parents[1] / "backend" / "deployments" / "base-mainnet.json",
    ):
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        addr = ((data.get("contracts") or {}).get("AIMarketEscrow") or "").strip()
        if addr:
            return addr.lower()
    raise AssertionError("deployment registry not readable — cannot verify the escrow")
