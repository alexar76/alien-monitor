"""Fold hub-discovered peers onto nodes the monitor already draws.

The Hub catalogue lists first-party satellites as federation peers so they can
be sold/invoked. Discovery used to emit every unmatched peer as ``group=oracle``
(violet, orbital ring). Those satellites already have canonical map nodes with
their own group, icon and poller — a second planet is a lie. Same fold as the
17-oracle family: enrich the node that exists, never mint a duplicate.

Gates stay gates: THEMIS, MOMUS, Treasury and WARDEN are distinct nodes. A hub
listing of THEMIS folds onto ``themis``, it does not become an oracle and it
does not collapse into MOMUS. A stranger on another host that merely *names*
itself after a satellite stays a discovered node.
"""

from __future__ import annotations

from ipaddress import ip_address
from typing import Any
from urllib.parse import urlparse

from oracle_family import family_node_id_for_peer

# Hub suns the map already draws. Discovery used to mint `signal-hunt-hub` /
# `competing-lab-hub` next to the seeded `signal_hunt_hub` / `competing_hub`.
SEEDED_HUB_IDS: frozenset[str] = frozenset({"hub", "competing_hub", "signal_hunt_hub"})

# (host, path_substring or None, canonical node id)
# More specific path rules first. modelmarket.dev itself is the primary hub sun
# (never folded onto a satellite). hunt.modelmarket.dev:9083 is Competing Lab Hub;
# hunt.modelmarket.dev (443) is Signal Hunt Hub — two processes, two planets.
_HOST_RULES: tuple[tuple[str, str | None, str], ...] = (
    ("momus.modelmarket.dev", "treasury", "treasury"),
    ("momus.modelmarket.dev", None, "momus"),
    ("iot.modelmarket.dev", None, "gaia"),
    ("gaia.modelmarket.dev", None, "gaia"),
    ("atlas.modelmarket.dev", None, "atlas"),
    ("themis.modelmarket.dev", None, "themis"),
    ("basanos.modelmarket.dev", None, "basanos"),
    ("skopos.modelmarket.dev", None, "skopos"),
    ("metis.modelmarket.dev", None, "metis"),
    ("logos.modelmarket.dev", None, "logos"),
    ("lottery.modelmarket.dev", None, "lottery"),
    ("use.modelmarket.dev", None, "use_cases"),
    ("modelmarket.dev", "studio", "hephaestus"),
    ("modeldev.modelmarket.dev", "bridges", "bridges"),
    ("modelmarket.dev", None, "hub"),
    ("magic-ai-factory.com", "agents", "factory_agents"),
    ("www.magic-ai-factory.com", "agents", "factory_agents"),
)

# Public URLs seeded into hub-discovery's known_by_url so a *peer hub's* child
# list becomes an edge to the existing planet, not a second moon.
FIRST_PARTY_URLS: tuple[tuple[str, str], ...] = (
    ("https://momus.modelmarket.dev", "momus"),
    ("https://momus.modelmarket.dev/treasury", "treasury"),
    ("https://iot.modelmarket.dev", "gaia"),
    ("https://gaia.modelmarket.dev", "gaia"),
    ("https://atlas.modelmarket.dev", "atlas"),
    ("https://themis.modelmarket.dev", "themis"),
    ("https://basanos.modelmarket.dev", "basanos"),
    ("https://skopos.modelmarket.dev", "skopos"),
    ("https://metis.modelmarket.dev", "metis"),
    ("https://logos.modelmarket.dev", "logos"),
    ("https://lottery.modelmarket.dev", "lottery"),
    ("https://use.modelmarket.dev", "use_cases"),
    ("https://modelmarket.dev/studio", "hephaestus"),
    ("https://modeldev.modelmarket.dev/bridges", "bridges"),
    ("https://modelmarket.dev", "hub"),
    ("https://magic-ai-factory.com", "factory"),
    ("https://hunt.modelmarket.dev", "signal_hunt_hub"),
    ("http://hunt.modelmarket.dev:9083", "competing_hub"),
    ("https://hub.modelmarket.dev", "competing_hub"),
    ("http://hub.modelmarket.dev:9083", "competing_hub"),
)

_NAME_PREFIXES: tuple[tuple[str, str], ...] = (
    ("momus", "momus"),
    ("themis", "themis"),
    ("basanos", "basanos"),
    ("gaia", "gaia"),
    ("atlas", "atlas"),
    ("skopos", "skopos"),
    ("metis", "metis"),
    ("logos", "logos"),
    ("lottery", "lottery"),
    ("hephaestus", "hephaestus"),
    ("bridges", "bridges"),
    ("warden", "warden"),
    ("argus", "argus"),
    ("treasury", "treasury"),
    ("signal-hunt-hub", "signal_hunt_hub"),
    ("signal_hunt_hub", "signal_hunt_hub"),
    ("competing-lab-hub", "competing_hub"),
    ("competing_hub", "competing_hub"),
)

_HUB_NAME_SLUGS: dict[str, str] = {
    "signal-hunt-hub": "signal_hunt_hub",
    "signal_hunt_hub": "signal_hunt_hub",
    "fed-signal_hunt_hub": "signal_hunt_hub",
    "competing-lab-hub": "competing_hub",
    "competing_hub": "competing_hub",
    "competing-lab": "competing_hub",
    "fed-competing_hub": "competing_hub",
    "magic-ai-factory-ai-market": "factory",
    "magic-ai-factory": "factory",
    "ai-factory": "factory",
}


def _host_path(url: str) -> tuple[str, str]:
    parsed = urlparse(str(url or "").strip())
    host = (parsed.hostname or "").lower()
    path = f"{parsed.path or ''}#{parsed.fragment or ''}".lower()
    return host, path


def _port(url: str) -> int | None:
    parsed = urlparse(str(url or "").strip())
    if parsed.port:
        return parsed.port
    if parsed.scheme == "https":
        return 443
    if parsed.scheme == "http":
        return 80
    return None


def _from_lab_hub(url: str) -> str | None:
    """Signal Hunt Hub vs Competing Lab Hub — same box, different ports.

    Env URLs (API IP:9083, public :9083) also fold, so the live peer
    ``http://108.x.x.x:9083`` does not mint a second Competing Lab sun.
    """
    host, _path = _host_path(url)
    if not host:
        return None
    port = _port(url)
    if host in ("hub.modelmarket.dev",):
        return "competing_hub"
    if host == "hunt.modelmarket.dev":
        if port == 9083:
            return "competing_hub"
        return "signal_hunt_hub"
    try:
        from competing_lab_layers import competing_hub_api_url, competing_hub_url, signal_hunt_url
    except Exception:
        return None
    for candidate, nid in (
        (competing_hub_api_url(), "competing_hub"),
        (competing_hub_url(), "competing_hub"),
        (signal_hunt_url(), "signal_hunt_hub"),
    ):
        ch, _ = _host_path(candidate)
        if not ch:
            continue
        if host == ch and (port == _port(candidate) or (nid == "competing_hub" and port == 9083)):
            return nid
    return None


def _from_factory(url: str) -> str | None:
    """Factory storefront is already the ``factory`` sun — not a second hub.

    ``/agents`` is the live-agents shelf. ``/product/…`` stays a catalog row,
    not a fold onto the factory sun.
    """
    host, path = _host_path(url)
    if not host:
        return None
    hosts = {"magic-ai-factory.com", "www.magic-ai-factory.com"}
    try:
        from factory_products import factory_public_url
        fh, _ = _host_path(factory_public_url())
        if fh:
            hosts.add(fh)
    except Exception:
        pass
    if host not in hosts:
        return None
    if "agents" in path:
        return "factory_agents"
    if "/product/" in path or path.rstrip("/").endswith("product"):
        return None
    return "factory"


def _from_host(url: str) -> str | None:
    lab = _from_lab_hub(url)
    if lab:
        return lab
    factory = _from_factory(url)
    if factory:
        return factory
    host, path = _host_path(url)
    if not host:
        return None
    for rule_host, needle, nid in _HOST_RULES:
        if host != rule_host:
            continue
        if needle is None or needle in path:
            return nid
    return None


def _from_name(text: str) -> str | None:
    """Id/label slug of a first-party peer (hub well-known name, not a foreign clone)."""
    slug = "".join(
        c if (c.isalnum() or c in "-_") else "-" for c in str(text or "").lower()
    ).strip("-")
    if slug.startswith("fed-"):
        slug = slug[4:]
    if not slug:
        return None
    if slug.startswith("momus") and "treasury" in slug:
        return "treasury"
    hub = _HUB_NAME_SLUGS.get(slug)
    if hub:
        return hub
    for prefix, nid in _NAME_PREFIXES:
        if slug == prefix or slug.startswith(f"{prefix}-") or slug.startswith(f"{prefix}_"):
            return nid
    return None


def _looks_like_literal_ip(host: str) -> bool:
    try:
        ip_address(host)
        return True
    except ValueError:
        return False



def _map_node_ids() -> frozenset[str]:
    """Every node this map actually draws.

    The hub's answer is believed only for a node that EXISTS here. A hub — ours, one day
    somebody else's, or ours after a bad seed edit — naming something this map has never
    drawn would otherwise mint a planet by assertion, or rename an existing one into a
    stranger. The live example is benign and instructive: the oracle-family endpoint is
    seeded as `oracle_family`, a name no node carries (the map draws the seventeen oracles
    individually), so the answer is declined and the host rules fold it as before. When the
    map grows a node by that name, it starts being used with no code change here.
    """
    from deployment_profile import owns_builtin_shelf
    from ecosystem_layout import NODE_POSITIONS
    from oracle_family import ORACLE_FAMILY, oracle_node_id

    # A deployment pointed at somebody else's hub draws none of these. Folding a peer onto
    # `atlas` there would name a stranger's service after ours and hang an edge on a node
    # that is not in the graph — the exact failure this function exists to prevent, one
    # deployment over. Its own two nodes are all it can honestly claim.
    if not owns_builtin_shelf():
        return frozenset({"hub", "federation"})

    # NODE_POSITIONS already carries the hub suns (hub, factory, competing_hub,
    # signal_hunt_hub) — the map places them, so it knows them. Reading the map is the
    # point: a second list here would be one more thing to keep in sync.
    return frozenset(NODE_POSITIONS) | {
        oracle_node_id(str(o.get("slug") or "")) for o in ORACLE_FAMILY if o.get("slug")
    } | {"oracle-cave-platon"}


def canonical_node_id_for_peer(n: dict[str, Any]) -> str | None:
    """Map a hub-discovered peer onto an existing map node id, or None if it is new.

    A `canonical_id` on the probe is THE answer: our own hub resolved it from the operator's
    pinned seed list (aimarket_hub/peer_identity.py), which is the same fact the tables
    below encode by hand — only kept where it belongs, next to the key the operator vouched
    for, and reachable by every consumer instead of transcribed into each one.

    It is only ever set for peers our hub itself listed (see `trust_declared_identity` in
    hub_discovery): a peer list republished by another hub is a stranger's opinion about
    our naming. The tables stay as the residue for what the hub cannot answer — ARGUS,
    DIOSCURI, HELIOS and WARDEN publish no well-known at all, so no hub knows them.
    """
    given = str(n.get("canonical_id") or "").strip()
    if given and given in _map_node_ids():
        return given
    from deployment_profile import owns_builtin_shelf

    # The host rules and the oracle-family slugs below are a transcription of the AICOM
    # map. Off that map they are not knowledge, they are a naming collision waiting to
    # happen: somebody else's `atlas.` host is not our ATLAS.
    if not owns_builtin_shelf():
        return None
    url = str(n.get("url") or "").strip()
    # Host rules first: "hephaestus" contains the family slug "aestus", so a
    # studio peer would otherwise land on the Aestus oracle.
    host_id = _from_host(url)
    if host_id:
        return host_id
    fam = family_node_id_for_peer(n)
    if fam:
        return fam
    # Seeded hub suns: well-known name on a bare IP (live :9083 that env still
    # lists as hunt.modelmarket.dev) must still fold. A stranger that merely
    # *named* itself Signal Hunt Hub on another host stays a discovered hub.
    host, _ = _host_path(url)
    for key in ("id", "label", "name"):
        named = _from_name(str(n.get(key) or ""))
        if named and named in SEEDED_HUB_IDS:
            if not url or _looks_like_literal_ip(host):
                return named
    if url:
        return None
    for key in ("id", "label", "name"):
        named = _from_name(str(n.get(key) or ""))
        if named:
            return named
    return None
