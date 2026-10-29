"""An eSIM operator who installs the kit and announces to the hub appears on the map as itself.

The owner's words (2026-10-15): such an operator "appears as a sphere in the Alien Monitor with
an opened card, a 3D eSIM-operator visual and a link to its site — the kit installs, it becomes
a participant of the AI economy". Before this, our own demo seller was a violet "oracle", and a
stranger's kit node, which publishes `protocol_versions: ["v2"]` from `aimarket node`, would have
been drawn as a federated HUB sun on a domain that only sells eSIMs.

Who sells eSIMs is read from OUR hub's catalogue (it lists `esim.quote@v1` only after calling
it); the seller's mode and catalogue size come from its own /agents/healthz, typed strictly.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import hub_discovery

HUB = "http://127.0.0.1:9083"
OPERATOR = "https://esim.example-operator.com"
STRANGER_HUB = "https://hub.stranger.example"


def _search(*rows: dict[str, Any]) -> dict[str, Any]:
    return {"matches": list(rows)}


def _quote_row(url: str, **extra: Any) -> dict[str, Any]:
    return {"capability_id": "esim.quote@v1", "source_hub": url, "product_id": "esim-example",
            "source_hub_name": "Example Travel eSIM", "trust_score": 0.62,
            "deliveries_30d": {"confirmed": 7, "distinct_buyers": 5, "refunded": 1}, **extra}


def _run(monkeypatch, responses: dict[str, Any], peers: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    asked: list[str] = []

    async def fake_get_json(_client, url, *, allow_private, timeout):  # noqa: ARG001
        asked.append(url)
        if url == f"{HUB}/ai-market/v2/federation/peers":
            return {"peers": peers}
        if url == f"{HUB}/.well-known/ai-market.json":
            return {"hub_url": "https://modelmarket.dev"}
        for prefix, body in responses.items():
            if url.startswith(prefix):
                return body
        return None

    async def no_chain(_client, _declarations):
        return {}

    monkeypatch.setattr(hub_discovery, "_get_json", fake_get_json)
    monkeypatch.setattr(hub_discovery, "url_is_safe", lambda url, allow_private=False: True)
    monkeypatch.setattr(hub_discovery.foreign_contracts, "verify", no_chain)
    monkeypatch.setenv("ALIEN_DISCOVERY_ENABLED", "1")
    return asyncio.run(hub_discovery.discover_async(HUB)), asked


def _by_url(result: dict[str, Any], url: str) -> dict[str, Any]:
    return next(n for n in result["nodes"] if n.get("url") == url)


def test_a_kit_operator_is_drawn_as_an_esim_operator_with_its_site(monkeypatch):
    result, asked = _run(monkeypatch, {
        f"{HUB}/ai-market/v2/search": _search(_quote_row(OPERATOR)),
        f"{OPERATOR}/.well-known/ai-market.json": {"name": "Example Travel eSIM", "protocol_versions": ["v2"],
                                                    "node_version": "aimarket-node 3.15.27",
                                                    "description": "Travel eSIMs for 120 countries"},
        f"{OPERATOR}/agents/healthz": {"ok": True, "offers": 640, "countries": 120, "demo": False,
                                       "paid_orders": True, "refunds": "automatic",
                                       "catalog": {"source": "live", "at": "2026-10-15T10:00:00Z"}},
    }, [{"url": OPERATOR, "name": "Example Travel eSIM", "capabilities_count": 2, "trust_score": 0.62}])

    node = _by_url(result, OPERATOR)
    assert node["group"] == "esim_operator", "a kit node on its own domain is a seller, not a hub sun"
    assert node["url"] == OPERATOR and node["esim"]["site"] == OPERATOR
    assert node["status"] == "active"
    from node_palette import esim_shade

    assert node["color"] == esim_shade(node["id"]), "its own shade of the operators' green"
    assert node["esim"]["demo"] is False and node["esim"]["selling"] is True
    assert node["esim"]["refunds"] == "automatic" and node["esim"]["catalog"] == "live"
    assert node["esim"]["deliveries_30d"] == {"confirmed": 7, "distinct_buyers": 5, "refunded": 1}
    assert node["esim"]["kit_url"].endswith("/kit")
    assert node["metrics"]["offers"] == 640 and node["metrics"]["countries"] == 120
    assert node["metrics"]["deliveries_30d"] == 7 and node["metrics"]["buyers_30d"] == 5
    assert f"{OPERATOR}/agents/healthz" in asked, "its health is its seller node's, where the kit puts it"


def test_a_stranger_hub_that_sells_no_esim_is_still_a_hub(monkeypatch):
    result, _ = _run(monkeypatch, {
        f"{HUB}/ai-market/v2/search": _search(_quote_row(OPERATOR)),
        f"{STRANGER_HUB}/.well-known/ai-market.json": {"name": "Stranger Hub", "hub_version": "3.1.0",
                                                       "protocol_versions": ["v2"]},
    }, [{"url": STRANGER_HUB, "name": "Stranger Hub"}])
    assert _by_url(result, STRANGER_HUB)["group"] == "peer_hub"


def test_a_declared_hub_can_sell_esims_without_becoming_a_shop(monkeypatch):
    result, _ = _run(monkeypatch, {
        f"{HUB}/ai-market/v2/search": _search(_quote_row(STRANGER_HUB)),
        f"{STRANGER_HUB}/.well-known/ai-market.json": {
            "name": "New Catalogue", "federation": {"role": "hub"},
        },
    }, [{"url": STRANGER_HUB, "name": "New Catalogue"}])
    node = _by_url(result, STRANGER_HUB)
    assert (node["group"], node["role"], node["icon"]) == ("peer_hub", "hub", "hub")
    assert node["status"] == "idle", "missing health cannot demote a declared hub"


def test_a_seller_without_categories_or_protocol_still_appears(monkeypatch):
    """The gate used to need an oracle-ish category or a hub's protocol; selling eSIMs is enough."""
    result, _ = _run(monkeypatch, {
        f"{HUB}/ai-market/v2/search": _search(_quote_row(OPERATOR)),
        f"{OPERATOR}/.well-known/ai-market.json": {"name": "Bare eSIM shop"},
    }, [{"url": OPERATOR}])
    node = _by_url(result, OPERATOR)
    assert node["group"] == "esim_operator"
    assert node["status"] == "idle", "no healthz answer: on the map, not claimed alive"
    assert node["esim"]["offers"] is None and node["esim"]["demo"] is None


def test_what_a_peer_says_about_itself_reaches_the_card_only_as_known_types(monkeypatch):
    result, _ = _run(monkeypatch, {
        f"{HUB}/ai-market/v2/search": _search(_quote_row(OPERATOR)),
        f"{OPERATOR}/.well-known/ai-market.json": {"name": "Odd shop", "protocol_versions": ["v2"]},
        f"{OPERATOR}/agents/healthz": {"ok": "yes", "offers": "lots", "countries": 12.5, "demo": "no",
                                       "paid_orders": 1, "refunds": "<img src=x onerror=alert(1)>",
                                       "catalog": {"source": "javascript:alert(1)"}},
    }, [{"url": OPERATOR}])
    esim = _by_url(result, OPERATOR)["esim"]
    assert esim["offers"] is None and esim["countries"] is None
    assert esim["demo"] is None and esim["selling"] is None
    assert esim["refunds"] is None and esim["catalog"] is None


def test_only_the_quote_capability_marks_a_seller_and_counts_are_counts():
    sellers = hub_discovery.esim_sellers_from_search(_search(
        {"capability_id": "esim.status@v1", "source_hub": "https://only-status.example"},
        {"capability_id": "gaia.weather.read@v1", "source_hub": "https://iot.example"},
        _quote_row("https://a.example/", deliveries_30d={"confirmed": -3, "distinct_buyers": True, "refunded": 2.5}),
        _quote_row("https://A.example", product_id="second-row-ignored"),
    ))
    assert set(sellers) == {"a.example"}
    assert sellers["a.example"]["product_id"] == "esim-example"
    assert sellers["a.example"]["deliveries_30d"] == {"confirmed": 0, "distinct_buyers": 0, "refunded": 0}
    assert hub_discovery.esim_sellers_from_search(None) == {}
    assert hub_discovery.esim_sellers_from_search({"matches": "nope"}) == {}


@pytest.mark.parametrize("locale,name", [("en", "eSIM operator"), ("ru", "eSIM-оператор"), ("es", "operador eSIM")])
def test_the_assistant_can_name_the_group(locale, name):
    from live_graph import group_name

    assert group_name("esim_operator", locale) == name


def test_an_esim_operator_belongs_to_the_hub_that_lists_it_not_to_itself():
    """'This node is a hub' was printed on our demo shop's card: a discovered peer was assumed
    to run its own hub. An eSIM operator is a seller in our hub's catalogue."""
    from hub_affiliation import apply_hub_affiliation

    nodes = [
        {"id": "example-travel-esim", "group": "esim_operator", "discovered": True, "url": OPERATOR},
        {"id": "stranger-hub", "group": "peer_hub", "discovered": True, "url": STRANGER_HUB},
    ]
    apply_hub_affiliation(nodes, primary_hub_url="https://modelmarket.dev", primary_label="modelmarket.dev")
    assert nodes[0]["hub"]["id"] == "hub" and nodes[0]["hub"]["url"] == "https://modelmarket.dev"
    assert nodes[1]["hub"]["id"] == "stranger-hub", "a discovered hub still belongs to itself"


@pytest.mark.parametrize("question", [
    "покажи есим", "где есим", "покажи eSIM-оператора", "show eSIM", "focus eSIM seller",
    "muéstrame el operador esim", "montre l’opérateur esim", "显示 esim",
])
def test_the_assistant_flies_to_an_esim_operator_by_what_it_is(question):
    """«покажи есим» answered in words and the camera stayed put: an operator's name is its own
    ("modelmarket.dev demo eSIM seller"), and a node matched only when its WHOLE name or host was
    in the question. The kind is a name too."""
    from ai_nav_actions import resolve_nav_actions

    state = {"nodes": [
        {"id": "gaia", "label": "GAIA", "group": "physical"},
        {"id": "modelmarket-dev-demo-esim-seller", "label": "modelmarket.dev demo eSIM seller",
         "group": "esim_operator", "url": "https://esim.modelmarket.dev"},
    ]}
    actions = resolve_nav_actions(question, state)
    assert actions and actions[0]["node_id"] == "modelmarket-dev-demo-esim-seller", question


def test_asking_what_an_esim_is_does_not_move_the_camera():
    from ai_nav_actions import resolve_nav_actions

    state = {"nodes": [{"id": "x", "label": "Shop", "group": "esim_operator"}]}
    assert resolve_nav_actions("что такое есим", state) == []


def test_each_operator_has_its_own_green_stable_across_restarts():
    import colorsys

    from node_palette import color_for, esim_shade

    ids = ["modelmarket-dev-demo-esim-seller", "example-travel-esim", "globetrotter-sim", "nomad-data", "roam-eu"]
    colours = [color_for("esim_operator", [], node_id=i) for i in ids]
    assert len(set(colours)) == len(ids), "two operators side by side must not be one colour twice"
    assert colours == [esim_shade(i) for i in ids], "the same id, the same shade"
    for c in colours:
        r, g, b = (int(c[k:k + 2], 16) / 255 for k in (1, 3, 5))
        hue = colorsys.rgb_to_hls(r, g, b)[0] * 360
        assert 120 <= hue <= 182, f"{c} left the operators' green"
    assert color_for("esim_operator", []) == "#2ef2b0", "without an id: the group colour"


def test_a_hub_that_publishes_no_description_is_described_by_its_own_numbers(monkeypatch):
    """A third-party operator's hub (aimarket-hub before 3.15.28) has no description in its
    well-known: the card said "Federation peer — discovered node" on the live map."""
    result, _ = _run(monkeypatch, {
        f"{HUB}/ai-market/v2/search": _search(_quote_row(OPERATOR)),
        f"{OPERATOR}/.well-known/ai-market.json": {"name": "Test Operator eSIM", "hub_version": "3.15.27",
                                                    "protocol_versions": ["v1", "v2"]},
        f"{OPERATOR}/agents/healthz": {"ok": True, "offers": 1728, "countries": 205, "demo": True},
    }, [{"url": OPERATOR}])
    node = _by_url(result, OPERATOR)
    assert node["description"] == ("eSIM operator running the eSIM operator kit: 205 countries, 1728 offers; "
                                   "demo: live prices, no sales.")
