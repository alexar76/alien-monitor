"""A realm whose buyer cannot buy must say so, not fail quietly forever.

Found on `monitor-uni.modelmarket.dev` on 2026-09-07, ten days into the condition: the
bubble hub is deliberately configured like production (`deploy/uni-hub.sh` sets
`AIFACTORY_PROD=1`, `AIFACTORY_PAYMENT_VERIFY_STUB=0`, `AIMARKET_PAYMENT_CHAIN=base`,
because the bubble's premise is being indistinguishable from live), and no on-chain
verifier is reachable from that container — so every deposit was fail-closed, correctly,
and the realm's own simulated buyer could never open a channel.

The refusal path returned early without counting the round, so `buyer_rounds` stayed 0, no
event was emitted, and the only trace was one HTTP 400 per round in the container log. The
map showed 215 invocations the whole time — the lifetime figure the header was borrowing
before that was fixed the same day.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import universe_external_buyer as ueb
from universe_layers import apply_buyer_health


class _RefusingBuyer(ueb.ExternalAIBuyer):
    """A buyer whose hub refuses every channel — the live UNI condition."""

    def _hub_takes_real_money(self) -> bool:
        return False

    def _search(self, vu, intent, budget):
        return [{"capability_id": "x@v1", "name": "X", "price_per_call_usd": 0.01}]

    def _select(self, matches, budget):
        return matches

    def _open_channel(self, budget, vu=None, item=None):
        self._last_open_error = (
            'HTTP 400: {"error":"on-chain verification unavailable — refusing to credit '
            'channel in production without a verified transaction"}'
        )
        return None


def test_a_refused_round_still_counts_as_a_round():
    buyer = _RefusingBuyer(hub_url="http://127.0.0.1:9183")
    result = buyer.execute_round(vu=None)
    assert result["purchases"] == 0
    assert buyer.rounds_completed == 1            # was 0 forever
    assert "on-chain verification unavailable" in result["blocked"]


def test_the_buyer_stops_asking_and_says_why():
    buyer = _RefusingBuyer(hub_url="http://127.0.0.1:9183")
    for _ in range(ueb._MAX_OPEN_FAILURES):
        buyer.execute_round(vu=None)
    status = buyer.status()
    assert status["open_failures"] == ueb._MAX_OPEN_FAILURES
    assert "consecutive channel/open refusals" in status["halted"]
    assert "127.0.0.1:9183" in status["halted"]
    assert "on-chain verification unavailable" in status["halted"]


def test_a_working_round_clears_the_failure_streak():
    buyer = _RefusingBuyer(hub_url="http://127.0.0.1:9183")
    buyer.execute_round(vu=None)
    assert buyer.status()["open_failures"] == 1

    buyer._open_channel = lambda budget, vu=None, item=None: "ch-1"          # type: ignore[method-assign]
    buyer._invoke = lambda item, channel_id: {"ok": True}  # type: ignore[method-assign]
    buyer._close_channel = lambda channel_id: None        # type: ignore[method-assign]
    result = buyer.execute_round(vu=None)
    assert result["purchases"] == 1
    assert buyer.status()["open_failures"] == 0
    assert buyer.status()["purchases_total"] == 1


def test_stalled_economy_reaches_the_summary():
    summary: dict = {}
    apply_buyer_health(summary, {"buyer": {
        "hub_url": "http://127.0.0.1:9183", "rounds": 12, "purchases_total": 0,
        "open_failures": 5, "last_open_error": "HTTP 400: nope",
        "halted": "5 consecutive channel/open refusals from http://127.0.0.1:9183 — HTTP 400: nope.",
    }})
    assert summary["buyer_rounds"] == 12
    assert summary["buyer_purchases_total"] == 0
    assert "consecutive channel/open refusals" in summary["economy_stalled"]


def test_a_healthy_buyer_stalls_nothing():
    summary: dict = {}
    apply_buyer_health(summary, {"buyer": {
        "hub_url": "http://127.0.0.1:9183", "rounds": 40, "purchases_total": 17,
        "open_failures": 0, "last_open_error": "", "halted": "",
    }})
    assert "economy_stalled" not in summary
    assert summary["buyer_purchases_total"] == 17


class TestRealDeposit:
    """The buyer paying for real, because a hub in production cannot accept anything else.

    It used to send `tx_hash="buyer-1757…"` — a string, not a transaction. That is refused
    by any hub with `AIFACTORY_PROD=1`, which the bubble hub deliberately sets (its whole
    premise is being indistinguishable from live). So the realm's economy could not start.
    """

    def test_no_chain_means_no_deposit_and_a_reason(self):
        buyer = ueb.ExternalAIBuyer(hub_url="http://127.0.0.1:9183")
        tx, reason = buyer._deposit_onchain(None, 10.0)
        assert tx == ""
        assert "no chain connection" in reason

    def test_the_buyer_is_not_the_recipient(self):
        """Paying from accounts[0] would bind a channel to the hub's own wallet."""
        from eth_account import Account

        buyer = Account.from_key(ueb.UNI_BUYER_KEY).address
        anvil_account_zero = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
        assert buyer.lower() != anvil_account_zero.lower()

    def test_it_signs_the_challenge_the_hub_hands_back(self):
        """Recovering the signature must give the paying wallet, or the hub refuses."""
        from eth_account import Account
        from eth_account.messages import encode_defunct

        buyer_obj = ueb.ExternalAIBuyer(hub_url="http://127.0.0.1:9183")
        challenge = (
            "AIMarket-Payer-Proof/v1\npurpose:channel-open\nchain:base\n"
            "tx:0x" + "ab" * 32 + "\npayer:0x" + "cd" * 20 + "\namount_cents:1000"
        )
        signature = buyer_obj._sign_challenge(challenge)
        recovered = Account.recover_message(
            encode_defunct(text=challenge), signature=signature
        )
        assert recovered.lower() == Account.from_key(ueb.UNI_BUYER_KEY).address.lower()

    def test_a_fake_hash_is_never_sent_again(self):
        """The old payload shape, pinned out: no `buyer-<epoch>` strings."""
        source = (Path(ueb.__file__)).read_text()
        assert "buyer-{int(time.time())}" not in source
        assert 'f"buyer-' not in source

    def test_the_402_probe_needs_a_capability_the_hub_sells(self):
        """The probe must be a real invoke, in the shape the endpoint validates.

        Two versions failed the same silent way, falling back to the realm own accounts[0]
        while the hub is paid at accounts[1]: `x402.discovery@v1` (nothing sells it → 404)
        and `capability_id` without `product_id` (required → 422). Neither carries payment
        requirements, and the deposit then verified as "moved no USDC to the configured
        recipient" — the right answer to the wrong payment.
        """
        buyer = ueb.ExternalAIBuyer(hub_url="http://127.0.0.1:9183")

        class _Realm:
            payment_recipient = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"

        # No capability to probe with → do not invent one, use what the realm believes.
        assert buyer._payment_recipient(_Realm(), None) == _Realm.payment_recipient
        assert buyer._payment_recipient(_Realm(), {}) == _Realm.payment_recipient

    def test_a_channel_needs_its_secret_to_authorize_a_debit(self):
        """A funded channel whose id alone is sent gets 402 on every invoke.

        `open` mints a one-time debit secret precisely so a leaked channel id cannot drain
        a deposit. The buyer dropped it, which produced three "Invoke HTTP 402" lines under
        a channel that had really opened and really held 12.5 tokens.
        """
        buyer = ueb.ExternalAIBuyer(hub_url="http://127.0.0.1:9183")
        assert buyer._channel_headers("ch_1") == {"X-Payment-Channel": "ch_1"}

        buyer._channel_secret = "s3cr3t"
        assert buyer._channel_headers("ch_1") == {
            "X-Payment-Channel": "ch_1",
            "X-Payment-Channel-Secret": "s3cr3t",
        }

    def test_the_secret_never_outlives_its_channel(self):
        buyer = ueb.ExternalAIBuyer(hub_url="http://127.0.0.1:9183")
        buyer._channel_secret = "s3cr3t"
        buyer._close_channel("ch_1")          # unreachable hub; the finally: still runs
        assert buyer._channel_secret == ""

    def test_one_deposit_funds_many_rounds(self):
        """A channel per round hits the hub rate limit and stops the realm economy dead.

        Measured on the bubble 2026-09-07: the buyer opened a fresh channel every 8 ticks,
        about 90 an hour, and the hub capped it — "rate limit exceeded — max 20 channel
        opens per hour per wallet". Correct of the hub; the buyer was misusing the whole
        point of a payment channel, which is many invokes per deposit.
        """
        buyer = ueb.ExternalAIBuyer(hub_url="http://127.0.0.1:9183")
        opens = []

        def _open(budget, vu=None, item=None):
            opens.append(budget)
            return "ch_%d" % len(opens)

        buyer._open_channel = _open                     # type: ignore[method-assign]
        buyer._close_channel = lambda cid: None         # type: ignore[method-assign]

        first = buyer._channel_for(0.01, 100.0, None, {})
        assert first == "ch_1" and len(opens) == 1
        # …still funded, so the next rounds reuse it rather than opening again
        buyer._channel_balance = 0.05
        assert buyer._channel_for(0.01, 100.0, None, {}) == "ch_1"
        assert buyer._channel_for(0.04, 100.0, None, {}) == "ch_1"
        assert len(opens) == 1

        # spent → settle and open exactly one more
        buyer._channel_balance = 0.0
        assert buyer._channel_for(0.01, 100.0, None, {}) == "ch_2"
        assert len(opens) == 2

    def test_closing_forgets_the_channel_it_closed(self):
        buyer = ueb.ExternalAIBuyer(hub_url="http://127.0.0.1:9183")
        buyer._channel_id = "ch_1"
        buyer._channel_balance = 5.0
        buyer._channel_secret = "s"
        buyer._close_channel("ch_1")
        assert buyer._channel_id == ""
        assert buyer._channel_balance == 0.0
        assert buyer._channel_secret == ""

    def test_the_status_reports_what_it_is_holding(self):
        buyer = ueb.ExternalAIBuyer(hub_url="http://127.0.0.1:9183")
        buyer._channel_id = "ch_7"
        buyer._channel_balance = 1.25
        status = buyer.status()
        assert status["channel_id"] == "ch_7"
        assert status["channel_balance_usd"] == 1.25


class TestDemandMeetsSupply:
    """A wish-list is demand; a realm sells what it sells.

    The buyer picks one of 15 hardcoded intents at random, and the bubble is six stdlib
    satellites — "data analysis" matches three capabilities, "translation service",
    "security audit" and "image generation" match nothing. Measured 2026-09-07: most rounds
    returned on `if not matches` WITHOUT counting the round and without a line in the log,
    so `buyer_rounds` sat at 0 through an entire EXPANSION phase. Same invisibility as the
    channel path, one branch over.
    """

    def _buyer_with_catalogue(self, rows):
        buyer = ueb.ExternalAIBuyer(hub_url="http://127.0.0.1:9183")
        buyer._catalogue_rows = rows
        buyer._catalogue_at = 1e18          # far future: never re-fetch during the test
        return buyer

    def test_the_catalogue_becomes_the_offer_set(self):
        buyer = self._buyer_with_catalogue([
            {"capability_id": "diktyon.graph.degree@v1", "product_id": "diktyon",
             "source_hub": "local", "offerable": True, "price_per_call_usd": 0.004},
            {"capability_id": "uni.answer@v1", "product_id": "uni-pack",
             "source_hub": "local", "offerable": True, "routed_price_usd": 0.02},
        ])
        offers = buyer._catalogue(budget=1.0)
        assert {o["capability_id"] for o in offers} == {
            "diktyon.graph.degree@v1", "uni.answer@v1"
        }
        assert all(o["price_per_call_usd"] > 0 for o in offers)

    def test_the_routed_price_is_the_one_that_counts(self):
        """`routed_price_usd` includes the hub fee; ignoring it under-budgets every round."""
        buyer = self._buyer_with_catalogue([
            {"capability_id": "x@v1", "product_id": "p", "offerable": True,
             "price_per_call_usd": 0.01, "routed_price_usd": 0.25},
        ])
        assert buyer._catalogue(budget=0.10) == []
        assert buyer._catalogue(budget=1.0)[0]["price_per_call_usd"] == 0.25

    def test_an_empty_realm_is_reported_not_skipped(self):
        buyer = self._buyer_with_catalogue([])
        buyer._hub_takes_real_money = lambda: False          # type: ignore[method-assign]
        buyer._search = lambda vu, intent, budget: []        # type: ignore[method-assign]

        result = buyer.execute_round(vu=None)
        assert result["purchases"] == 0
        assert buyer.rounds_completed == 1                   # the round HAPPENED
        assert "nothing on offer" in buyer.status()["last_round_note"]

    def test_offers_that_are_all_too_dear_are_reported(self):
        buyer = self._buyer_with_catalogue([])
        buyer._hub_takes_real_money = lambda: False          # type: ignore[method-assign]
        buyer._search = lambda vu, intent, budget: [         # type: ignore[method-assign]
            {"capability_id": "x@v1", "price_per_call_usd": 10_000.0}
        ]
        buyer._select = lambda matches, budget: []           # type: ignore[method-assign]

        result = buyer.execute_round(vu=None)
        assert result["purchases"] == 0
        assert buyer.rounds_completed == 1
        assert "none affordable" in buyer.status()["last_round_note"]


class _Chain:
    """The smallest fake chain `_settlement_chain` can hand back."""

    def __init__(self, accounts):
        self.eth = type("eth", (), {"accounts": accounts})()

    @staticmethod
    def is_connected():
        return True


class TestTheDepositLandsOnTheChainTheHubReads:
    """The realm's chain and the hub's chain were two different Anvils.

    `my-vps` runs the monitor's universe chain on 127.0.0.1:8545 and the bubble hub's
    chain on 172.17.0.1:8546. Both answer chain id 31337 and both carry the same
    deterministic addresses from the public test mnemonic, so the deposit looked correct
    in every field the buyer could see and existed on neither ledger the hub could read:
    "transaction not found or not yet mined", on every round, for the life of the realm.
    """

    def test_unset_keeps_paying_on_the_realms_own_chain(self, monkeypatch):
        monkeypatch.delenv("ALIEN_UNIVERSE_BUYER_RPC", raising=False)
        realm = _Chain(["0xaa"])
        vu = type("vu", (), {"_w3": realm, "evm_usdt_address": "0xtoken",
                             "_eth_accounts": ["0xaa"]})()
        w3, token, accounts, why = ueb.ExternalAIBuyer()._settlement_chain(vu)
        assert why == ""
        assert w3 is realm
        assert (token, accounts) == ("0xtoken", ["0xaa"])

    def test_a_named_rpc_is_used_instead_of_the_realms(self, monkeypatch):
        monkeypatch.setenv("ALIEN_UNIVERSE_BUYER_RPC", "http://172.17.0.1:8546")
        monkeypatch.setenv("ALIEN_UNIVERSE_BUYER_TOKEN", "0xbubble")
        buyer = ueb.ExternalAIBuyer()
        hub_chain = _Chain(["0xbb", "0xcc"])
        buyer._settle_w3 = hub_chain
        buyer._settle_accounts = ["0xbb", "0xcc"]
        realm = _Chain(["0xaa"])
        vu = type("vu", (), {"_w3": realm, "evm_usdt_address": "0xtoken",
                             "_eth_accounts": ["0xaa"]})()
        w3, token, accounts, why = buyer._settlement_chain(vu)
        assert why == ""
        assert w3 is hub_chain, "the deposit would have been mined on the wrong chain"
        assert token == "0xbubble"
        assert accounts == ["0xbb", "0xcc"]

    def test_an_unreachable_settlement_chain_is_reported_not_silently_skipped(
        self, monkeypatch,
    ):
        monkeypatch.setenv("ALIEN_UNIVERSE_BUYER_RPC", "http://127.0.0.1:1")
        monkeypatch.setattr(ueb.ExternalAIBuyer, "_payment_recipient", lambda *a, **k: "0xhub")
        vu = type("vu", (), {"_w3": None, "evm_usdt_address": "0xtoken",
                             "_eth_accounts": []})()
        buyer = ueb.ExternalAIBuyer()

        class _Boom:
            def __init__(self, *a, **k):
                raise OSError("connection refused")

        import sys as _sys
        import types as _types
        fake = _types.ModuleType("web3")
        fake.Web3 = _Boom
        fake.Web3.HTTPProvider = lambda *a, **k: None
        monkeypatch.setitem(_sys.modules, "web3", fake)
        tx, reason = buyer._deposit_onchain(vu, 1.0, {"capability_id": "x@v1"})
        assert tx == ""
        assert "127.0.0.1:1" in reason and "unreachable" in reason


class TestRefusalsDoNotBurnTheHubsRateLimit:
    """A refused open still counts against "max 20 channel opens per hour per wallet".

    Asking forever spent the whole quota on refusals, so the hub's answer changed from
    the real reason to "rate limit exceeded" — which is how a wrong-chain deposit came to
    look like a throttling problem on the map.
    """

    def test_the_buyer_backs_off_after_the_halt(self):
        buyer = _RefusingBuyer(hub_url="http://127.0.0.1:9183")
        for _ in range(ueb._MAX_OPEN_FAILURES):
            buyer.execute_round(vu=None)
        assert buyer._open_retry_at > 0, "it would keep asking every round"
        asked = buyer._open_failures
        buyer.execute_round(vu=None)
        assert buyer._open_failures == asked, "it asked again inside the backoff"
        assert buyer.rounds_completed == ueb._MAX_OPEN_FAILURES + 1

    def test_the_backoff_doubles_but_stays_inside_the_hubs_window(self):
        buyer = _RefusingBuyer(hub_url="http://127.0.0.1:9183")
        waits = []
        for _ in range(ueb._MAX_OPEN_FAILURES + 6):
            buyer._open_retry_at = 0.0          # let every round through
            buyer.execute_round(vu=None)
            if buyer._open_retry_at:
                waits.append(buyer._open_retry_at)
        assert waits == sorted(waits)
        assert max(waits) - min(waits) > 0, "the wait never grew"
        assert ueb._MAX_OPEN_BACKOFF_S <= 3600, "a cap past the hub's hourly window"

    def test_a_successful_open_clears_the_backoff(self):
        buyer = _RefusingBuyer(hub_url="http://127.0.0.1:9183")
        for _ in range(ueb._MAX_OPEN_FAILURES):
            buyer.execute_round(vu=None)
        assert buyer._open_retry_at > 0
        buyer._open_retry_at = 0.0
        buyer._open_channel = lambda budget, vu=None, item=None: "ch-1"
        buyer._invoke = lambda item, channel_id: {"ok": True}
        buyer.execute_round(vu=None)
        assert buyer._open_retry_at == 0.0
        assert buyer._open_failures == 0


class TestARefusedOpenDoesNotStrandTheDeposit:
    """The deposit is an on-chain transfer made BEFORE the request.

    Measured on the first pass after the chain fix: the buyer moved $96.60 to the hub's
    wallet on the bubble chain and got back "rate limit exceeded — max 20 channel opens
    per hour per wallet", which the hub checks before it verifies anything. The money was
    gone and no channel existed. Paying again next round would strand another one.
    """

    class _Buyer(ueb.ExternalAIBuyer):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.deposits = 0
            self.accept_on = 99

        def _deposit_onchain(self, vu, budget, item=None):
            self.deposits += 1
            return f"0xtx{self.deposits}", "0xpayer"

        def _post_open(self, payload):
            raise NotImplementedError

    def _drive(self, buyer, rounds, accept_on=None):
        """Run `_open_channel` `rounds` times against a hub that refuses until accept_on."""
        calls = []

        class _Resp:
            def __init__(self, ok):
                self.status_code = 200 if ok else 400
                self.headers = {"content-type": "application/json"}
                self.text = "" if ok else '{"error":"rate limit exceeded"}'

            def json(self):
                return ({"channel": {"channel_id": "ch-1"}, "channel_secret": "s"}
                        if self.status_code == 200 else {"error": "rate limit exceeded"})

        import contextlib

        class _Client:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, url, json=None, **k):
                calls.append(json)
                return _Resp(len(calls) >= (accept_on or 10 ** 9))

        original = ueb.httpx.Client
        ueb.httpx.Client = _Client
        try:
            out = [buyer._open_channel(100.0, vu=None, item={}) for _ in range(rounds)]
        finally:
            ueb.httpx.Client = original
        return out, calls

    def test_a_refusal_keeps_the_deposit_and_does_not_pay_again(self):
        buyer = self._Buyer(hub_url="http://127.0.0.1:9183")
        results, calls = self._drive(buyer, rounds=4)
        assert results == [None, None, None, None]
        assert buyer.deposits == 1, f"paid {buyer.deposits} times for one channel"
        assert {c["tx_hash"] for c in calls} == {"0xtx1"}, "a second transfer was sent"
        assert buyer.status()["unspent_deposit_usd"] == 100.0

    def test_the_carried_deposit_is_what_opens_the_channel(self):
        buyer = self._Buyer(hub_url="http://127.0.0.1:9183")
        results, calls = self._drive(buyer, rounds=3, accept_on=3)
        assert results[-1] == "ch-1"
        assert buyer.deposits == 1
        assert buyer.status()["unspent_deposit_usd"] == 0.0, "it stayed owed after opening"
        assert buyer._opened_deposit_usd == 100.0

    def test_the_channel_is_credited_with_what_the_hub_verified(self):
        """A re-presented deposit carries its own amount, not the round's budget."""
        buyer = self._Buyer(hub_url="http://127.0.0.1:9183")
        buyer._unspent = {"tx_hash": "0xold", "payer": "0xpayer", "usd": 42.0}
        results, calls = self._drive(buyer, rounds=1, accept_on=1)
        assert results == ["ch-1"]
        assert buyer.deposits == 0, "it paid again on top of an unspent deposit"
        assert calls[0]["deposit_usd"] == 42.0
        assert buyer._opened_deposit_usd == 42.0
