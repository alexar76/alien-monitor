"""
External AI Buyer — autonomous agent that purchases from the Hub.

Uses real Hub REST API: search → channel/open → invoke → channel/close.
Selection uses diversity-aware scoring across capability categories.

This is NOT a mock — it exercises the real Hub, ChannelLedger, and
payment infrastructure. The only synthetic element is the wallet funding
(handled by UniverseFundingStream).
"""

from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from universe import VirtualUniverse

# Search intents for diverse purchasing
SEARCH_INTENTS = [
    "translation service",
    "code review tool",
    "data analysis",
    "market research",
    "content generation",
    "security audit",
    "API integration",
    "document summarization",
    "fraud detection",
    "SEO optimization",
    "customer support",
    "legal document review",
    "sentiment analysis",
    "image generation",
    "workflow automation",
]

CATEGORY_KEYWORDS = {
    "translate": ["translat", "language", "multilingual"],
    "code": ["code", "dev", "programming", "api", "software"],
    "data": ["data", "analytics", "analysis", "statistics"],
    "content": ["content", "writing", "generate", "creative"],
    "security": ["security", "audit", "compliance", "fraud"],
    "marketing": ["marketing", "seo", "landing", "sales"],
    "legal": ["legal", "contract", "document", "review"],
    "finance": ["finance", "trading", "market", "pricing"],
    "agent": ["agent", "assistant", "bot", "automation"],
    "infra": ["infra", "deploy", "monitor", "cloud"],
}


def sample_input(schema: Any, depth: int = 0) -> Any:
    """A minimal input that satisfies a published JSON Schema.

    Every one of the bubble capabilities declares a full schema — `required`, types and
    bounds — because each satellite is a pure stdlib function of its input and validates
    it. The buyer sent the same fixed dict to all of them
    (`{"task": "external_ai_purchase", "mode": "uni"}`), so the hub billed the call,
    routed it, and the provider answered 400: "Provider returned 400" reads like a broken
    satellite and is really a client sending nonsense to `geo.distance@v1`.

    Only the REQUIRED fields are filled: the point is a call that is accepted, not a
    fixture that exercises every option.
    """
    if not isinstance(schema, dict) or depth > 6:
        return {}
    if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
        return schema["enum"][0]
    if "const" in schema:
        return schema["const"]
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = next((k for k in kind if k != "null"), "object")

    if kind == "object" or (kind is None and "properties" in schema):
        props = schema.get("properties") or {}
        required = schema.get("required") or list(props)[:1]
        return {
            name: sample_input(props.get(name) or {"type": "string"}, depth + 1)
            for name in required
        }
    if kind == "array":
        items = schema.get("items") or {"type": "number"}
        count = max(int(schema.get("minItems") or 0), 2)
        return [sample_input(items, depth + 1) for _ in range(count)]
    if kind in ("number", "integer"):
        low = schema.get("minimum", schema.get("exclusiveMinimum"))
        high = schema.get("maximum", schema.get("exclusiveMaximum"))
        value = 1
        if low is not None and high is not None:
            value = (float(low) + float(high)) / 2.0
        elif low is not None:
            value = float(low) + 1
        elif high is not None:
            value = float(high) - 1
        return int(value) if kind == "integer" else round(float(value), 4)
    if kind == "boolean":
        return True
    if kind == "null":
        return None
    text = "uni"
    minimum = int(schema.get("minLength") or 0)
    return text if len(text) >= minimum else text * (minimum // len(text) + 1)


def _infer_category(name: str, description: str) -> str:
    blob = f"{name} {description}".lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in blob:
                return cat
    return "general"


#: How long the realm catalogue is reused before being re-read. It changes when a
#: satellite is published, not between rounds.
_CATALOGUE_TTL_S = 300.0

#: Anvil's published account #2. Nobody's wallet — this mnemonic is in every README on the
#: internet — and it is the bubble's BUYER on purpose: `payment_recipient` is accounts[0],
#: which also holds the token supply, so paying from it would make payer == recipient and
#: bind a channel to the hub's own wallet.
UNI_BUYER_KEY = "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a"

#: Minimal ERC-20 surface the deposit needs.
_ERC20_ABI = [
    {"name": "transfer", "type": "function", "constant": False,
     "inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}],
     "outputs": [{"name": "", "type": "bool"}]},
    {"name": "balanceOf", "type": "function", "constant": True,
     "inputs": [{"name": "who", "type": "address"}],
     "outputs": [{"name": "", "type": "uint256"}]},
    {"name": "decimals", "type": "function", "constant": True,
     "inputs": [], "outputs": [{"name": "", "type": "uint8"}]},
]


#: Consecutive `channel/open` refusals before the buyer stops asking. The hub is entitled
#: to refuse; what it is not entitled to is being asked forever. Five rounds is enough to
#: rule out a transient error and short enough that the map says so within a minute.
_MAX_OPEN_FAILURES = 5


class ExternalAIBuyer:
    """Autonomous AI agent that buys capabilities from the AIMarket Hub."""

    def __init__(self, hub_url: str = "http://127.0.0.1:9083"):
        self.hub_url = (os.environ.get("ALIEN_UNIVERSE_BUYER_HUB_URL") or hub_url).rstrip("/")
        self.rounds_completed = 0
        self.purchase_history: list[dict] = []
        self.preferred_categories: set[str] = set()
        self.budget_range = (80.0, 200.0)
        self._real_money_hub: bool | None = None
        self._halt_reason = ""
        self._open_failures = 0
        self._last_open_error = ""
        self._purchases_total = 0
        self._pay_to = ""
        self._channel_id = ""
        self._channel_secret = ""
        self._channel_balance = 0.0
        self._catalogue_rows: list[dict] = []
        self._catalogue_at = 0.0
        self._last_round_note = ""

    def _hub_takes_real_money(self) -> bool:
        """Does this hub settle with real funds? Asked once, cached, and fail-closed.

        The default hub URL is loopback, and on a host-network container that is the PRODUCTION
        hub. A simulated buyer aimed at a hub that verifies deposits on chain cannot open a
        channel — it has no wallet and no deposit — so every round ended in
        `400 on-chain verification unavailable`, once every ~40 seconds, forever. That is not a
        harmless no-op: it is a payment API being hammered by a demo, and 25 such refusals were
        sitting in the production log when this was found on 2026-08-24.

        Unreachable or unparseable counts as "real": a simulation must not decide it may
        transact because it could not tell.
        """
        if self._real_money_hub is not None:
            return self._real_money_hub
        if os.environ.get("ALIEN_UNIVERSE_BUYER_ALLOW_REAL_HUB", "").strip().lower() in (
                "1", "true", "yes", "on"):
            self._real_money_hub = False
            return False
        verdict = True
        note = "could not read the hub's payment posture"
        try:
            with httpx.Client(timeout=4.0) as client:
                doc = client.get(f"{self.hub_url}/.well-known/ai-market.json").json()
            configured = bool(doc.get("payment_configured"))
            testnet = doc.get("payment_testnet")
            verdict = configured and testnet is not True
            note = f"payment_configured={configured} payment_testnet={testnet!r}"
        except Exception as exc:
            note = f"{note} ({type(exc).__name__})"
        self._real_money_hub = verdict
        if verdict:
            self._halt_reason = (
                f"the simulated buyer is pointed at a real-money hub ({self.hub_url}: {note}); "
                f"it cannot fund a channel there and every round would be refused. Point "
                f"ALIEN_UNIVERSE_BUYER_HUB_URL at a sandbox hub, or set "
                f"ALIEN_UNIVERSE_BUYER_ALLOW_REAL_HUB=1 if you really mean it."
            )
            print(f"[UniverseBuyer] halted — {self._halt_reason}")
        return verdict

    def execute_round(self, vu: VirtualUniverse) -> dict:
        if self._hub_takes_real_money():
            return {"purchases": 0, "events": [], "halted": self._halt_reason}
        budget = round(random.uniform(*self.budget_range), 2)
        intent = random.choice(SEARCH_INTENTS)

        events: list[dict] = []
        purchases = 0

        try:
            matches = self._search(vu, intent, budget)
            if not matches:
                # The wish-list is DEMAND, and this realm may not sell any of it: the bubble
                # is six stdlib satellites, so "translation service" / "security audit" /
                # "image generation" match nothing while "data analysis" matches three. Most
                # rounds therefore returned here — without counting the round and without a
                # word in the log, which is the same invisibility the channel path had.
                # A buyer that finds none of what it wanted buys what is actually on offer.
                matches = self._catalogue(budget)
                if not matches:
                    self.rounds_completed += 1
                    self._last_round_note = f"nothing on offer under ${budget:.2f}"
                    print(f"[Buyer] {self._last_round_note}")
                    return {"purchases": 0, "events": [], "note": self._last_round_note}
                print(f"[Buyer] no match for {intent!r} — buying from the catalogue instead")

            selected = self._select(matches, budget)
            if not selected:
                self.rounds_completed += 1
                self._last_round_note = (
                    f"{len(matches)} offers, none affordable at ${budget:.2f}"
                )
                print(f"[Buyer] {self._last_round_note}")
                return {"purchases": 0, "events": [], "note": self._last_round_note}

            needed = sum(float(i.get("price_per_call_usd") or 0) for i in selected)
            channel_id = self._channel_for(needed, budget, vu, selected[0])
            if not channel_id:
                # A refused channel used to return here SILENTLY, without even counting the
                # round — so `buyer_rounds` stayed 0, no event was emitted, and the only
                # trace was one 400 in the container log every ~40 seconds. On the UNI
                # deployment that ran for ten days: the bubble hub is deliberately
                # configured like production (`AIFACTORY_PROD=1`,
                # `AIFACTORY_PAYMENT_VERIFY_STUB=0`) and has no reachable on-chain
                # verifier, so it fail-closed every deposit — correctly — and its own
                # simulated buyer could never buy anything. Nothing on the map said so.
                self._open_failures += 1
                self.rounds_completed += 1
                if self._open_failures >= _MAX_OPEN_FAILURES and not self._halt_reason:
                    self._halt_reason = (
                        f"{self._open_failures} consecutive channel/open refusals from "
                        f"{self.hub_url} — {self._last_open_error or 'no reason given'}. "
                        f"The buyer has stopped asking; this realm's economy is stalled "
                        f"until the hub can credit a channel."
                    )
                    print(f"[UniverseBuyer] halted — {self._halt_reason}")
                return {
                    "purchases": 0,
                    "events": [],
                    "blocked": self._last_open_error,
                    "halted": self._halt_reason,
                }
            self._open_failures = 0

            for item in selected:
                try:
                    result = self._invoke(item, channel_id)
                    if result:
                        purchases += 1
                        self._channel_balance = max(
                            0.0,
                            self._channel_balance - float(item.get("price_per_call_usd") or 0),
                        )
                        cat = _infer_category(item.get("name", ""), item.get("description", ""))
                        self.preferred_categories.add(cat)
                        self.purchase_history.append({
                            "capability_id": item.get("capability_id", ""),
                            "name": item.get("name", ""),
                            "price_usd": item.get("price_per_call_usd", 0),
                            "category": cat,
                            "ts": datetime.now(timezone.utc).isoformat(),
                        })
                        if len(self.purchase_history) > 300:
                            self.purchase_history = self.purchase_history[-300:]
                        if len(self.purchase_history) > 500:
                            self.purchase_history = self.purchase_history[-500:]
                        events.append({
                            "type": "buyer_purchase",
                            "agent": "ExternalAI",
                            "action": "invoke",
                            "target": item.get("capability_id", ""),
                            "amount": item.get("price_per_call_usd", 0),
                            "token": "USDT",
                            "id": f"buyer_{self.rounds_completed}_{purchases}",
                            "ts": datetime.now(timezone.utc).isoformat(),
                        })
                except Exception as exc:
                    print(f"[Buyer] Invoke failed for {item.get('name', '?')}: {exc}")

            # Deliberately NOT closed here: the next round reuses it (see _channel_for).

        except Exception as exc:
            print(f"[Buyer] Round failed: {exc}")

        self.rounds_completed += 1
        self._purchases_total += purchases
        return {"purchases": purchases, "events": events}

    def status(self) -> dict:
        """What this buyer is actually managing to do — for the map, not just the log."""
        return {
            "hub_url": self.hub_url,
            "rounds": self.rounds_completed,
            "purchases_total": self._purchases_total,
            "channel_id": self._channel_id,
            "channel_balance_usd": round(self._channel_balance, 6),
            "open_failures": self._open_failures,
            "last_round_note": self._last_round_note,
            "last_open_error": self._last_open_error,
            "halted": self._halt_reason,
        }

    def _catalogue(self, budget: float) -> list[dict]:
        """What this realm actually sells, from its own signed manifest.

        Same fields `_search` returns (`capability_id`, `product_id`, `source_hub`,
        `price_per_call_usd`) at the same published prices, so selection and invoke are
        unchanged — this only widens what the buyer is willing to want.
        """
        now = time.time()
        if not (self._catalogue_rows and now - self._catalogue_at < _CATALOGUE_TTL_S):
            try:
                with httpx.Client(timeout=8.0) as client:
                    r = client.get(
                        f"{self.hub_url}/ai-market/v2/manifest", params={"limit": 200}
                    )
                rows = (r.json() or {}).get("tools") or [] if r.status_code == 200 else []
            except Exception as exc:
                print(f"[Buyer] catalogue unavailable: {exc}")
                return []
            self._catalogue_rows = [
                t for t in rows
                if isinstance(t, dict) and t.get("capability_id") and t.get("offerable")
            ]
            self._catalogue_at = now

        def price(tool: dict) -> float:
            # The ROUTED price is what the buyer is billed: it carries the hub fee, and
            # budgeting on the bare list price under-budgets every federated call.
            return float(tool.get("routed_price_usd") or tool.get("price_per_call_usd") or 0)

        affordable = [t for t in self._catalogue_rows if price(t) <= budget]
        random.shuffle(affordable)
        return [
            {
                "capability_id": t.get("capability_id"),
                "product_id": t.get("product_id", ""),
                "source_hub": t.get("source_hub", "local"),
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "price_per_call_usd": price(t),
                "input_schema": t.get("input_schema"),
            }
            for t in affordable[:12]
        ]

    def _search(self, vu: VirtualUniverse, intent: str, budget: float) -> list[dict]:
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.get(
                    f"{self.hub_url}/ai-market/v2/search",
                    params={"intent": intent, "budget": budget, "limit": 12},
                )
                if r.status_code == 200:
                    data = r.json()
                    return data.get("matches") or data.get("results") or []
                print(f"[Buyer] Search HTTP {r.status_code}")
                return []
        except httpx.ConnectError:
            return []
        except Exception as exc:
            print(f"[Buyer] Search error: {exc}")
            return []

    def _select(self, matches: list[dict], budget: float) -> list[dict]:
        scored = []
        for m in matches:
            price = float(m.get("price_per_call_usd") or m.get("routed_price_usd") or 5.0)
            if price <= 0:
                continue
            trust = float(m.get("trust_score") or 0.5)
            name = str(m.get("name") or m.get("capability_id") or "")
            desc = str(m.get("description") or "")
            cat = _infer_category(name, desc)
            diversity = 1.5 if cat not in self.preferred_categories else 1.0
            score = (1.0 / price) * max(trust, 0.1) * diversity
            scored.append((score, price, m))

        scored.sort(key=lambda x: x[0], reverse=True)

        selected = []
        spent = 0.0
        for _, price, match in scored:
            if spent + price > budget:
                continue
            if len(selected) >= 6:
                break
            selected.append(match)
            spent += price

        return selected

    def _payment_recipient(self, vu: Any, item: dict | None = None) -> str:
        """Where this hub wants to be paid, discovered the way a real client discovers it.

        The hub deliberately keeps the recipient OUT of its public manifest and publishes
        it in the x402 `accepts[].payTo` of a 402 instead. Reading the universe's own
        `payment_recipient` instead of asking got it wrong: the universe sets that to anvil
        accounts[0], while the bubble hub is configured to be paid at accounts[1] — and a
        deposit to the wrong address verifies as "moved no USDC to the configured
        recipient", which is exactly right and completely opaque.
        """
        if self._pay_to:
            return self._pay_to
        # The probe has to be a REAL invoke of something this hub sells, in the shape the
        # endpoint validates. Two versions of this got it wrong and both failed the same
        # silent way — falling back to the realm own accounts[0] while the hub is paid at
        # accounts[1]:
        #   `capability_id: "x402.discovery@v1"` — nothing sells it, so 404, and a 404
        #     carries no payment requirements;
        #   `capability_id` alone — `product_id` is REQUIRED, so 422, likewise no 402.
        # So it sends exactly what `_invoke` sends, minus the channel header.
        item = item or {}
        if not item.get("capability_id"):
            return str(getattr(vu, "payment_recipient", "") or "")
        try:
            with httpx.Client(timeout=8.0) as client:
                r = client.post(
                    f"{self.hub_url}/ai-market/v2/invoke",
                    json={
                        "product_id": item.get("product_id", ""),
                        "capability_id": item.get("capability_id", ""),
                        "source_hub": item.get("source_hub", "local"),
                        "input": {"task": "payment_discovery", "mode": "uni"},
                    },
                )
            header = r.headers.get("payment-required") or r.headers.get("PAYMENT-REQUIRED")
            try:
                body = r.json()
            except Exception:
                body = {}
            accepts = body.get("accepts") if isinstance(body, dict) else None
            if not accepts and header:
                import base64

                decoded = json.loads(base64.b64decode(header)) or {}
                accepts = decoded.get("accepts")
            for entry in accepts or []:
                pay_to = str((entry or {}).get("payTo") or "").strip()
                if pay_to.startswith("0x"):
                    self._pay_to = pay_to
                    print(f"[Buyer] hub takes deposits at {pay_to}")
                    return pay_to
            if not (accepts or header):
                print(
                    f"[Buyer] invoke returned HTTP {r.status_code} with no payment "
                    f"requirements: {r.text[:120]}"
                )
        except Exception as exc:
            print(f"[Buyer] could not read payment requirements: {exc}")
        # Last resort: what this realm believes. Announced as a guess, not a fact.
        fallback = str(getattr(vu, "payment_recipient", "") or "")
        if fallback:
            print(f"[Buyer] falling back to the realm's own recipient {fallback[:10]}")
        return fallback

    def _deposit_onchain(self, vu: Any, budget: float, item: dict | None = None) -> tuple[str, str]:
        """Actually pay the hub on this realm's chain. Returns (tx_hash, payer).

        The buyer used to send ``tx_hash="buyer-1757…"`` — a string, not a transaction —
        which a hub in production can only refuse. This realm has a chain, a token and a
        funded account, so the deposit is a real ERC-20 transfer and the hash is the real
        one: the same door, the same verifier and the same payer proof as a paying
        customer on Base. Returns ("", reason) when this realm has no chain to pay on.
        """
        w3 = getattr(vu, "_w3", None)
        token_address = getattr(vu, "evm_usdt_address", "") or ""
        recipient = self._payment_recipient(vu, item)
        if w3 is None or not w3.is_connected():
            return "", "this realm has no chain connection to pay on"
        if not token_address or not recipient:
            return "", "this realm has no settlement token or recipient yet"

        from eth_account import Account

        buyer = Account.from_key(UNI_BUYER_KEY).address
        unlocked = {str(a).lower() for a in (getattr(vu, "_eth_accounts", None) or [])}
        if unlocked and buyer.lower() not in unlocked:
            # Signing the payer proof needs the key; sending the transfer needs the node to
            # have the account funded. Both or nothing — never a half-paid deposit.
            return "", f"buyer account {buyer[:10]} is not funded on this chain"

        token = w3.eth.contract(address=w3.to_checksum_address(token_address), abi=_ERC20_ABI)
        try:
            decimals = int(token.functions.decimals().call())
        except Exception:
            decimals = 18
        units = int(round(float(budget) * (10 ** decimals)))

        # Top up from the supply holder when the buyer cannot cover the round. Deliberately
        # generous: one transfer per many rounds beats one per round.
        balance = int(token.functions.balanceOf(buyer).call())
        if balance < units:
            supplier = w3.to_checksum_address((getattr(vu, "_eth_accounts", None) or [recipient])[0])
            top_up = units * 20
            tx = token.functions.transfer(buyer, top_up).transact({"from": supplier})
            w3.eth.wait_for_transaction_receipt(tx, timeout=30)
            print(f"[Buyer] topped up {buyer[:10]} with {top_up / 10 ** decimals:.2f} tokens")

        tx = token.functions.transfer(
            w3.to_checksum_address(recipient), units
        ).transact({"from": w3.to_checksum_address(buyer)})
        receipt = w3.eth.wait_for_transaction_receipt(tx, timeout=30)
        if int(receipt.get("status", 0)) != 1:
            return "", "the deposit transaction reverted on this realm's chain"
        # The hub requires confirmations, and on an instant-mining chain the deposit's own
        # block is the head — so give it one more rather than weakening the hub's setting.
        try:
            w3.provider.make_request("evm_mine", [])
        except Exception:
            pass
        tx_hex = tx.hex() if hasattr(tx, "hex") else str(tx)
        if not tx_hex.startswith("0x"):
            tx_hex = "0x" + tx_hex
        return tx_hex, buyer

    def _sign_challenge(self, challenge: str) -> str:
        """Prove control of the paying wallet over the challenge the HUB handed back.

        The challenge is amount- and tx-bound and versioned by the hub; asking for it
        rather than rebuilding it means this client cannot drift out of agreement with
        whichever door it is talking to.
        """
        from eth_account import Account
        from eth_account.messages import encode_defunct

        signed = Account.sign_message(
            encode_defunct(text=challenge), private_key=UNI_BUYER_KEY
        )
        signature = signed.signature.hex()
        return signature if signature.startswith("0x") else "0x" + signature

    def _open_channel(self, budget: float, vu: Any = None, item: dict | None = None) -> str | None:
        tx_hash, payer = self._deposit_onchain(vu, budget, item)
        if not tx_hash:
            self._last_open_error = f"no deposit made: {payer}"
            print(f"[Buyer] {self._last_open_error}")
            return None

        payload: dict[str, Any] = {
            "deposit_usd": budget,
            "tx_hash": tx_hash,
            "wallet": payer,
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                for attempt in (1, 2):
                    r = client.post(
                        f"{self.hub_url}/ai-market/v2/channel/open", json=payload
                    )
                    if r.status_code == 200:
                        data = r.json()
                        ch = data.get("channel") if isinstance(data.get("channel"), dict) else {}
                        # `open` mints a one-time debit secret and returns it ONCE. Without
                        # it the invoke path refuses with 402 even on a funded channel: a
                        # leaked channel id must not be enough to drain a deposit, so the
                        # id alone authorizes nothing. Dropping it is what left three
                        # "Invoke HTTP 402" lines under a channel that had really opened.
                        self._channel_secret = str(
                            data.get("channel_secret") or ch.get("channel_secret") or ""
                        )
                        if not self._channel_secret:
                            print("[Buyer] channel opened but no debit secret was returned")
                        return ch.get("channel_id") or data.get("channel_id")
                    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
                    challenge = str((body or {}).get("challenge") or "").strip()
                    if attempt == 1 and challenge:
                        # Expected on the first try: the hub tells us what to sign.
                        payload["payer_signature"] = self._sign_challenge(challenge)
                        continue
                    self._last_open_error = f"HTTP {r.status_code}: {r.text[:160]}"
                    print(f"[Buyer] Channel open {self._last_open_error}")
                    return None
        except Exception as exc:
            self._last_open_error = f"{type(exc).__name__}: {exc}"[:180]
            print(f"[Buyer] Channel open error: {exc}")
            return None
        return None

    def _channel_for(
        self, needed: float, budget: float, vu: Any, item: dict
    ) -> str | None:
        """Reuse the open channel while it can still pay; open a new one only when it cannot.

        A payment channel exists so that ONE deposit funds MANY invokes. This buyer opened
        a fresh one every round — every 8 ticks, about 90 an hour — and the hub, correctly,
        capped it: "rate limit exceeded — max 20 channel opens per hour per wallet". So the
        realm economy would have stalled after twenty rounds however well the deposit door
        worked. One deposit now carries rounds until it is spent.
        """
        if self._channel_id and needed > 0 and self._channel_balance >= needed:
            return self._channel_id
        if self._channel_id:
            # Spent (or unusable) — settle it before asking for another.
            self._close_channel(self._channel_id)
        channel_id = self._open_channel(budget, vu, item)
        if channel_id:
            self._channel_id = channel_id
            self._channel_balance = budget
        return channel_id

    def _input_for(self, item: dict) -> dict:
        """An input this capability will accept, built from the schema it publishes."""
        schema = item.get("input_schema") or self._schema_for(item.get("capability_id") or "")
        built = sample_input(schema) if schema else {}
        if isinstance(built, dict) and built:
            return built
        # No schema to read: the old fixed payload is the only guess left, and a provider
        # that refuses it is refusing honestly.
        return {"task": "external_ai_purchase", "mode": "uni"}

    def _schema_for(self, capability_id: str) -> Any:
        """The schema from the cached catalogue, for offers that came from `_search`."""
        for row in self._catalogue_rows:
            if row.get("capability_id") == capability_id:
                return row.get("input_schema")
        return None

    def _channel_headers(self, channel_id: str) -> dict[str, str]:
        """Both halves of a channel authorization: the id, and the secret that debits it."""
        headers = {"X-Payment-Channel": channel_id}
        if self._channel_secret:
            headers["X-Payment-Channel-Secret"] = self._channel_secret
        return headers

    def _invoke(self, item: dict, channel_id: str) -> dict | None:
        try:
            with httpx.Client(timeout=10.0) as client:
                r = client.post(
                    f"{self.hub_url}/ai-market/v2/invoke",
                    json={
                        "product_id": item.get("product_id", ""),
                        "capability_id": item.get("capability_id", ""),
                        "source_hub": item.get("source_hub", "local"),
                        "input": self._input_for(item),
                    },
                    headers=self._channel_headers(channel_id),
                )
                if r.status_code == 200:
                    return r.json()
                print(f"[Buyer] Invoke HTTP {r.status_code}")
                return None
        except Exception as exc:
            print(f"[Buyer] Invoke error: {exc}")
            return None

    def _close_channel(self, channel_id: str) -> None:
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.post(
                    f"{self.hub_url}/ai-market/v2/channel/close",
                    json={"channel_id": channel_id},
                    # Closing settles money, so it wants the debit secret too — the same
                    # one `open` handed out once. Without it: "Channel close HTTP 400".
                    headers=self._channel_headers(channel_id),
                )
                if r.status_code != 200:
                    print(f"[Buyer] Channel close HTTP {r.status_code}: {r.text[:120]}")
        except Exception as exc:
            print(f"[Buyer] Channel close error: {exc}")
        finally:
            # One secret per channel, and this channel is done.
            self._channel_secret = ""
            if channel_id == self._channel_id:
                self._channel_id = ""
                self._channel_balance = 0.0
