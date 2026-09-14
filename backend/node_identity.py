"""What a node is CALLED and where it can be REACHED — one answer, for the card and for search.

Two things went wrong because there was no such place.

**A dead link on a card.** Foreign hubs describe themselves in their own signed ecosystem
declaration, and they describe themselves the way THEY see themselves: the Attested Memory Hub
advertises its Provenance Ledger as ``http://provenance-ledger:8812``, which is a Docker service
name on somebody else's compose network. The monitor put that on a node card as a clickable
link, so the card offered the reader an address that cannot resolve anywhere outside that host.
An address a viewer cannot open is worse than no address: they click it, get nothing, and learn
not to trust the card. Every foreign hub will do this, so the rule belongs here rather than in a
patch per satellite: an address is a LINK only when a browser elsewhere could actually open it,
and otherwise it is shown as text, plainly marked internal.

**A search that could not find what the map was showing.** Node lookup matched ids and labels
only, so a question naming an ADDRESS ("что за узел на provenance-ledger:8812", "кто такой
independentai.network") matched nothing — while the answer was on screen. Names and addresses are
the two things a person actually has when they ask about a node, so both are indexed, and from
the same identity as the card shows.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any
from urllib.parse import urlsplit

#: Suffixes that only mean anything inside somebody's own network.
_INTERNAL_SUFFIXES = (".local", ".internal", ".intranet", ".lan", ".home", ".corp",
                      ".svc", ".cluster.local", ".localdomain", ".test", ".example",
                      ".invalid", ".onion")

#: Schemes a browser can follow from a card.
_WEB_SCHEMES = ("http", "https")


def _host_of(raw: str) -> tuple[str, str, str]:
    """(scheme, host, port) for a URL or a bare `host:port` / `host`."""
    text = str(raw or "").strip()
    if not text:
        return ("", "", "")
    if "://" not in text:
        # `provenance-ledger:8812` and `example.com` both arrive here.
        text = f"//{text}"
    try:
        parts = urlsplit(text, scheme="")
        host = (parts.hostname or "").strip().lower().rstrip(".")
        # `.port` RAISES on a non-numeric port, and these strings are not all URLs: a node id
        # like `provider:hub:pl` reaches here, and a parser that throws on it would take the
        # whole state payload down over a label.
        try:
            port = str(parts.port or "")
        except ValueError:
            port = ""
    except ValueError:
        return ("", "", "")
    return ((parts.scheme or "").lower(), host, port)


def is_reachable(raw: Any) -> bool:
    """Could a browser on somebody else's machine open this address?

    False for every shape of "only from in here": a non-web scheme, loopback, a private or
    link-local IP, a Docker/Kubernetes service name (no dot at all), and the internal-only
    suffixes. This is deliberately about REACHABILITY, not about trust or liveness — a public
    address that happens to be down is still an address the reader can try.
    """
    scheme, host, _port = _host_of(raw)
    if not host:
        return False
    if scheme and scheme not in _WEB_SCHEMES:
        return False
    if host in ("localhost", "0.0.0.0", "::", "host.docker.internal"):
        return False
    if any(host == s.lstrip(".") or host.endswith(s) for s in _INTERNAL_SUFFIXES):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # A name. One label ("provenance-ledger", "memory-market") is a container hostname:
        # legitimate on its own network, meaningless everywhere else.
        return "." in host
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified)


def public_url(raw: Any) -> str:
    """The address as a link, or "" when it is not reachable from outside its own network."""
    text = str(raw or "").strip().rstrip("/")
    if not text or not is_reachable(text):
        return ""
    return text if "://" in text else f"https://{text}"


def internal_url(raw: Any) -> str:
    """The address as TEXT — what the node claims, when that claim is only locally true."""
    text = str(raw or "").strip().rstrip("/")
    return "" if (not text or is_reachable(text)) else text


def address_terms(raw: Any) -> list[str]:
    """Every form of this address a person might type, lowercased and de-duplicated.

    `http://provenance-ledger:8812` yields the full url, `provenance-ledger:8812`,
    `provenance-ledger`, and the port — so the question can name any of them.
    """
    text = str(raw or "").strip().rstrip("/")
    if not text:
        return []
    scheme, host, port = _host_of(text)
    out = [text.lower()]
    if scheme:
        out.append(text.lower().split("://", 1)[1])
    if host:
        out.append(f"{host}:{port}" if port else host)
        out.append(host)
        # `monitor.modelmarket.dev` should also answer to `modelmarket.dev`, which is how
        # people name a deployment — but never to a bare TLD.
        labels = host.split(".")
        if len(labels) > 2:
            out.append(".".join(labels[-2:]))
    seen: set[str] = set()
    terms: list[str] = []
    for term in out:
        t = term.strip().strip("/")
        if t and t not in seen and len(t) >= 3:
            seen.add(t)
            terms.append(t)
    return terms


def searchable_terms(node: dict[str, Any]) -> list[str]:
    """Names AND addresses for one node, so a lookup can match whatever the asker typed."""
    if not isinstance(node, dict):
        return []
    terms: list[str] = []
    for key in ("label", "id"):
        val = str(node.get(key) or "").strip().lower()
        if len(val) >= 3:
            terms.append(val)
    # `fedchild:https://independentai.network` — the interesting half is the address.
    nid = str(node.get("id") or "")
    if ":" in nid:
        tail = nid.split(":", 1)[1].strip().lower()
        if len(tail) >= 3:
            terms.append(tail)
            terms.extend(address_terms(tail))
    for key in ("url", "url_internal", "hub_url"):
        terms.extend(address_terms(node.get(key)))
    for alias in node.get("aliases") or []:
        val = str(alias or "").strip().lower()
        if len(val) >= 3:
            terms.append(val)
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        if term not in seen:
            seen.add(term)
            out.append(term)
    return out


def resolve_addresses(node: dict[str, Any]) -> dict[str, Any]:
    """A COPY of the node whose advertised address is split into a link and an internal claim.

    `url` keeps ONLY what a browser can open; `url_internal` carries the rest, so the card can
    say "internal address" instead of either lying with a link or hiding what the hub said.
    A copy, not a mutation: the same node dicts are the monitor's own working state, and the
    pollers that walk them expect the address the component actually answers on.
    """
    if not isinstance(node, dict):
        return node
    raw = node.get("url")
    children = node.get("children")
    if not raw and not isinstance(children, list):
        return node
    out = dict(node)
    if raw:
        link = public_url(raw)
        if link:
            out["url"] = link
            out.pop("url_internal", None)
        else:
            out["url_internal"] = internal_url(raw)
            out.pop("url", None)
    if isinstance(children, list):
        out["children"] = [resolve_addresses(c) if isinstance(c, dict) else c for c in children]
    return out


def resolved_nodes(nodes: Any) -> Any:
    """`resolve_addresses` over a payload's node list (tolerant of anything else)."""
    if not isinstance(nodes, list):
        return nodes
    return [resolve_addresses(n) if isinstance(n, dict) else n for n in nodes]


_WS = re.compile(r"\s+")


def normalize_query(text: str) -> str:
    return _WS.sub(" ", str(text or "").strip().lower())


def find_nodes(nodes: Any, query: str, limit: int = 8) -> list[dict[str, Any]]:
    """Nodes whose name or address matches `query`, best match first.

    Ranking is by the LENGTH of the matched term, so "independentai.network" beats a node whose
    label merely contains "hub". A query shorter than three characters matches nothing rather
    than everything.
    """
    q = normalize_query(query)
    if len(q) < 3 or not isinstance(nodes, list):
        return []
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        best = 0
        for term in searchable_terms(node):
            if q == term:
                best = max(best, len(term) + 100)   # an exact hit outranks any substring
            elif q in term or term in q:
                best = max(best, len(term))
        if best:
            scored.append((best, -index, node))
    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [node for _score, _idx, node in scored[:limit]]
