"""A peer-supplied URL must not inherit the trusted hub's private-network allowance.

`_apply_discovery` calls `discover_cached_sync(hub_url, allow_private=True)` so the UNI sim
can reach hubs it spawned on loopback. But that flag is threaded into `DiscoveryConfig` and
then into EVERY peer fetch, and with it set `url_is_safe` returns True for any http(s) URL
WITHOUT resolving it while `_pin_http_target` returns immediately without re-vetting. So the
DNS-rebinding defence and the private-range check were both off for URLs a third party
supplies.

That the hub itself is trusted is already handled separately: `discover_async` hardcodes
`allow_private=True` on the hub's own two fetches, with the comment "the hub itself is
trusted/operator-configured". So `cfg.allow_private` was widening only the peer path — the
one place it should not.

A peer entry needs no operator: open federation auto-admits after a sandbox assay, and the
hub republishes the announcer's own `well_known_url` verbatim in
GET /ai-market/v2/federation/peers.
"""

from __future__ import annotations

import pytest

from hub_discovery import DiscoveryConfig, url_is_safe


class TestAPeerUrlIsNeverTrustedBlindly:
    @pytest.mark.parametrize("url", [
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5:8080/.well-known/ai-market.json",
        "http://192.168.1.1/.well-known/ai-market.json",
        "http://172.16.0.9/.well-known/ai-market.json",
    ])
    def test_a_private_peer_url_is_refused_even_in_uni_mode(self, url):
        cfg = DiscoveryConfig(allow_private=True)
        assert url_is_safe(url, allow_private=cfg.peer_allow_private) is False, (
            f"{url} accepted from a peer document"
        )

    def test_the_uni_sims_own_loopback_hubs_still_work(self):
        """The reason the allowance exists: hubs the sim spawned on loopback."""
        cfg = DiscoveryConfig(allow_private=True)
        assert url_is_safe("http://127.0.0.1:9085/.well-known/ai-market.json",
                           allow_private=cfg.peer_allow_private) is True
        assert url_is_safe("http://localhost:9085/.well-known/ai-market.json",
                           allow_private=cfg.peer_allow_private) is True

    def test_without_uni_mode_loopback_is_refused_as_before(self):
        cfg = DiscoveryConfig(allow_private=False)
        assert url_is_safe("http://127.0.0.1:9085/x", allow_private=cfg.peer_allow_private) is False

    def test_a_public_peer_url_is_still_accepted(self):
        """A public IP LITERAL, so the assertion does not depend on DNS being reachable —
        an unresolvable hostname is refused in either mode, and always was."""
        for allow in (True, False):
            cfg = DiscoveryConfig(allow_private=allow)
            assert url_is_safe("https://93.184.216.34/.well-known/ai-market.json",
                               allow_private=cfg.peer_allow_private) is True

    def test_the_hub_itself_keeps_its_own_unconditional_allowance(self):
        """discover_async hardcodes allow_private=True for the operator-configured hub."""
        import inspect

        from hub_discovery import discover_async

        src = inspect.getsource(discover_async)
        assert "allow_private=True" in src, (
            "the trusted-hub fetch lost its allowance; a locally spawned hub is unreachable"
        )
