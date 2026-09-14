"""Factory catalog sync — fail-safe when Factory API is slow or down."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from factory_products import (
    CATALOG_CLUSTER_ID,
    build_product_clusters,
    clear_factory_catalog_cache,
    enrich_catalog_with_featured,
    factory_public_url,
    fetch_factory_products_sync,
    merge_factory_products,
    product_storefront_url,
    resolve_factory_catalog,
)


def test_build_product_clusters_single_catalog_nebula(monkeypatch):
    monkeypatch.setenv("AIFACTORY_PUBLIC_URL", "https://factory.test")
    products = [
        {"id": "p1", "name": "SaaS One", "category": "saas"},
        {"id": "p2", "name": "Landing Two", "category": "landings"},
        {"id": "p3", "name": "Template Three", "is_template": True},
    ]
    nodes, links = build_product_clusters(products, existing_ids=set())
    assert len(nodes) == 1
    assert nodes[0]["id"] == CATALOG_CLUSTER_ID
    assert nodes[0]["label"] == "Products · 3"
    assert nodes[0]["url"] == "https://factory.test"
    assert nodes[0]["metrics"]["categories"] == 3
    assert len(nodes[0]["children"]) == 3
    assert nodes[0]["children"][0]["url"] == product_storefront_url("p1", public_base="https://factory.test")
    assert links == [{"source": "factory", "target": CATALOG_CLUSTER_ID, "label": "catalog"}]


def test_merge_replaces_category_clusters_with_single_catalog(monkeypatch):
    monkeypatch.setenv("AIFACTORY_PUBLIC_URL", "https://factory.test")
    nodes = [
        {"id": "factory", "group": "infra", "metrics": {}, "position": {"x": 0, "y": 0, "z": 0}},
        {"id": "cluster-saas", "group": "cluster", "metrics": {"count": 3}},
        {"id": "cluster-landings", "group": "cluster", "metrics": {"count": 2}},
    ]
    links = [
        {"source": "factory", "target": "cluster-saas", "label": "catalog"},
        {"source": "factory", "target": "cluster-landings", "label": "catalog"},
    ]
    count = merge_factory_products(
        nodes,
        links,
        [
            {"id": "a", "name": "Alpha", "category": "saas"},
            {"id": "b", "name": "Beta", "category": "landings"},
        ],
    )
    assert count == 1
    assert {n["id"] for n in nodes if n.get("group") == "cluster"} == {CATALOG_CLUSTER_ID}
    assert links == [{"source": "factory", "target": CATALOG_CLUSTER_ID, "label": "catalog"}]


def test_fetch_returns_none_on_http_error(monkeypatch):
    class _Resp:
        status_code = 503

        def json(self):
            return {}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return _Resp()

    monkeypatch.setattr("factory_products.httpx.Client", _Client)
    assert fetch_factory_products_sync("http://factory.test") is None


def test_fetch_returns_empty_list_on_success(monkeypatch):
    class _Resp:
        status_code = 200

        def json(self):
            return {"products": []}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return _Resp()

    monkeypatch.setattr("factory_products.httpx.Client", _Client)
    assert fetch_factory_products_sync("http://factory.test") == []


def test_merge_skips_when_catalog_unavailable():
    nodes = [
        {"id": "factory", "group": "infra", "metrics": {}, "position": {"x": 0, "y": 0, "z": 0}},
        {"id": "cluster-saas", "group": "cluster", "metrics": {"count": 3}},
    ]
    links = [{"source": "factory", "target": "cluster-saas", "label": "catalog"}]
    assert merge_factory_products(nodes, links, None) == 0
    assert any(n["id"] == "cluster-saas" for n in nodes)


def test_sync_factory_catalog_keeps_products_on_api_failure(monkeypatch):
    from universe import VirtualUniverse

    clear_factory_catalog_cache()
    u = VirtualUniverse()
    u.seed_entities()
    u.materialize_product({"id": "prod-keep-me", "name": "Keep Me", "category": "saas"})
    assert "prod-keep-me" in u.entities

    monkeypatch.setattr(
        "factory_products.fetch_factory_monitor_catalog_sync",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "factory_products.fetch_factory_products_sync",
        lambda *_args, **_kwargs: None,
    )
    added = u.sync_factory_catalog("http://factory.test")
    assert added == 0
    assert "prod-keep-me" in u.entities


def test_resolve_keeps_cache_until_empty_streak(monkeypatch):
    clear_factory_catalog_cache()
    calls = {"n": 0}

    class _Resp:
        status_code = 200

        def __init__(self, products):
            self._products = products

        def json(self):
            return {"products": self._products}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            calls["n"] += 1
            if "/api/products" in url and calls["n"] == 1:
                return _Resp([{"id": "p1", "name": "One", "category": "saas"}])
            if "/api/products" in url:
                return _Resp([])
            return _Resp([])

    monkeypatch.setattr("factory_products.httpx.Client", _Client)
    monkeypatch.setattr(
        "factory_products.fetch_factory_monitor_catalog_sync",
        lambda *a, **k: None,
    )
    first, auth1 = resolve_factory_catalog("http://factory.test")
    assert auth1 is True
    assert [p["id"] for p in first][:3] == ["prod-bdb1634806de", "prod-e1a3b0abf16a", "p1"]
    second, auth2 = resolve_factory_catalog("http://factory.test")
    assert auth2 is False
    assert len(second) == 3
    third, auth3 = resolve_factory_catalog("http://factory.test")
    assert auth3 is False
    assert len(third) == 3
    fourth, auth4 = resolve_factory_catalog("http://factory.test")
    assert auth4 is True
    assert fourth == []


def test_factory_public_url_skips_stale_localhost(monkeypatch):
    monkeypatch.setenv("AIFACTORY_PUBLIC_URL", "http://localhost:9080")
    monkeypatch.setenv("NEXT_PUBLIC_SITE_URL", "https://magic-ai-factory.com")
    monkeypatch.delenv("ALIEN_PUBLIC_FACTORY_URL", raising=False)
    monkeypatch.delenv("PUBLIC_SITE_URL", raising=False)
    assert factory_public_url() == "https://magic-ai-factory.com"


def test_factory_public_url_real_mode_never_emits_loopback(monkeypatch):
    monkeypatch.setenv("ALIEN_MODE", "real")
    monkeypatch.setenv("AIFACTORY_PUBLIC_URL", "http://localhost:9080")
    monkeypatch.delenv("ALIEN_PUBLIC_FACTORY_URL", raising=False)
    monkeypatch.delenv("PUBLIC_SITE_URL", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_SITE_URL", raising=False)
    assert factory_public_url() == "https://magic-ai-factory.com"


def test_cluster_children_use_public_storefront_urls(monkeypatch):
    monkeypatch.setenv("ALIEN_PUBLIC_FACTORY_URL", "https://magic-ai-factory.com")
    nodes, _ = build_product_clusters(
        [{"id": "prod-491ceb8a448f", "name": "NightCircuit", "category": "landings"}],
        existing_ids=set(),
    )
    assert nodes[0]["url"] == "https://magic-ai-factory.com"
    assert nodes[0]["children"][0]["url"] == (
        "https://magic-ai-factory.com/product/prod-491ceb8a448f"
    )


def test_featured_sentinel_and_relay_are_catalog_and_moons(monkeypatch):
    monkeypatch.setenv("ALIEN_PUBLIC_FACTORY_URL", "https://magic-ai-factory.com")
    clear_factory_catalog_cache()

    catalog = enrich_catalog_with_featured(
        [{"id": "prod-land", "name": "A landing", "category": "landings"}],
        "http://factory.test",
    )
    assert [p["id"] for p in catalog[:3]] == [
        "prod-bdb1634806de",
        "prod-e1a3b0abf16a",
        "prod-land",
    ]
    assert catalog[0]["name"] == "Sentinel"
    assert catalog[1]["name"] == "Relay"

    nodes = [
        {"id": "factory", "group": "core", "metrics": {}, "position": {"x": 5, "y": 2, "z": -2}},
    ]
    links: list[dict] = []
    merge_factory_products(nodes, links, catalog)
    ids = [n["id"] for n in nodes]
    assert "cluster-catalog" in ids
    assert "prod-bdb1634806de" in ids
    assert "prod-e1a3b0abf16a" in ids
    sent = next(n for n in nodes if n["id"] == "prod-bdb1634806de")
    assert sent["group"] == "factory_product"
    assert sent["url"] == "https://magic-ai-factory.com/product/prod-bdb1634806de"
    kids = next(n for n in nodes if n["id"] == "cluster-catalog")["children"]
    assert kids[0]["id"] == "prod-bdb1634806de"
    assert kids[1]["id"] == "prod-e1a3b0abf16a"
