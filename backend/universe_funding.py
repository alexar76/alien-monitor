"""
Universe Funding Stream — external capital injection into UNI economy.

The ONLY synthetic element in UNI mode. Simulates an external funding
source (grant program, testnet faucet, investor capital) sending USDT
into the ecosystem on a regular schedule.

Funding grows with the universe — more hubs, more products, more funding.
Visualized as cosmic energy streams flowing from outside toward the hub.

In UNI mode, the FakeUSDT contract on Anvil is used to mint tokens.
The source address appears as "external" — outside the known entity graph.
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from universe import VirtualUniverse


class UniverseFundingStream:
    """Periodic external capital injection into the UNI economy."""

    def __init__(self, interval_ticks: int = 200, amount_range: tuple[float, float] = (100.0, 200.0)):
        self.total_funding = 0.0
        self.rounds: list[dict] = []
        self.interval_ticks = interval_ticks
        self.amount_range = amount_range
        self.last_funding_tick = 0
        self._funding_multiplier = 1.0

    def tick(self, current_tick: int, vu: VirtualUniverse) -> dict | None:
        if current_tick - self.last_funding_tick < self.interval_ticks:
            return None

        self.last_funding_tick = current_tick

        base = random.uniform(*self.amount_range)
        amount = round(base * self._funding_multiplier, 2)
        self.total_funding += amount

        tx_hash = self._mint_or_record(amount, vu)

        event = {
            "type": "funding_stream",
            "id": f"funding_{current_tick}",
            "amount": amount,
            "token": "USDT",
            "source": "external",
            "tx_hash": tx_hash,
            "ts": datetime.now(timezone.utc).isoformat(),
            "total_funding": self.total_funding,
            "round": len(self.rounds) + 1,
        }

        self.rounds.append(event)
        if len(self.rounds) > 100:
            self.rounds = self.rounds[-100:]

        vu.transactions.append({
            "id": tx_hash[:16],
            "hash": tx_hash,
            "from": "0xExternal",
            "to": vu.evm_escrow_address or "0xEscrow",
            "action": "funding",
            "target": "ecosystem",
            "amount": amount,
            "token": "USDT",
            "block": vu.chain_analytics.get("blocks", 0),
            "gas_used": 0,
            "status": "confirmed",
            "ts": event["ts"],
            "onchain": True,
            "funding": True,
        })

        if len(vu.transactions) > 200:
            vu.transactions = vu.transactions[-200:]

        vu.chain_analytics["tx_count"] = len(vu.transactions)

        print(f"[Funding] ${amount:.2f} USDT injected (total: ${self.total_funding:.2f})")

        return event

    def _mint_or_record(self, amount: float, vu: VirtualUniverse) -> str:
        if vu._w3 and vu._w3.is_connected() and vu.evm_usdt_address:
            try:
                return self._mint_onchain(amount, vu)
            except Exception as exc:
                print(f"[Funding] On-chain mint failed: {exc}")

        synthetic = f"0x{hashlib.sha256(f'funding_{amount}_{self.total_funding}_{random.random()}'.encode()).hexdigest()[:64]}"
        self._credit_factory_uni(amount, synthetic)
        return synthetic

    def _credit_factory_uni(self, amount_usd: float, ref: str) -> None:
        """Mirror synthetic funding into Factory UNI ledger when configured."""
        import os

        import httpx

        app_url = os.environ.get("AICOM_API_URL", "http://127.0.0.1:9081").rstrip("/")
        secret = os.environ.get("AIFACTORY_UNI_GRANT_SECRET", "").strip()
        if not secret:
            return
        try:
            from core.uni.pricing import usd_to_uni
        except ImportError:
            # Monitor container may not mount factory core; approximate 1:1
            usd_to_uni = lambda x, **kw: float(x)  # noqa: E731
        payload = {
            "owner_id": "universe:funding",
            "amount_uni": usd_to_uni(amount_usd, apply_spread=False),
            "ref": ref[:128],
            "reason": "universe_funding_stream",
        }
        try:
            httpx.post(
                f"{app_url}/api/uni/grant",
                json=payload,
                headers={"X-Uni-Grant-Secret": secret},
                timeout=8.0,
            )
        except Exception as exc:
            print(f"[Funding] Factory UNI grant skipped: {exc}")

    def _mint_onchain(self, amount: float, vu: VirtualUniverse) -> str:
        deployer = vu._w3.eth.accounts[0]
        usdt = vu._w3.eth.contract(
            address=vu.evm_usdt_address,
            abi=[
                {"constant": False, "inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}], "name": "transfer", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
            ],
        )
        amount_wei = vu._w3.to_wei(amount, "ether")
        recipient = vu.evm_escrow_address or vu._w3.eth.accounts[1]

        tx_hash = usdt.functions.transfer(recipient, amount_wei).transact({"from": deployer})
        receipt = vu._w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    def get_stats(self) -> dict:
        return {
            "total_funding": self.total_funding,
            "rounds": len(self.rounds),
            "last_amount": self.rounds[-1]["amount"] if self.rounds else 0,
            "multiplier": self._funding_multiplier,
            "interval_ticks": self.interval_ticks,
        }

    def grow_funding(self, multiplier: float) -> None:
        self._funding_multiplier = max(1.0, multiplier)
