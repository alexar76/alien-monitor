"""Factory catalog sync — fail-safe when Factory API is slow or down."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from factory_products import (
    clear_factory_catalog_cache,
    fetch_factory_products_sync,
    merge_factory_products,
    resolve_factory_catalog,
)


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
            if calls["n"] == 1:
                return _Resp([{"id": "p1", "name": "One", "category": "saas"}])
            return _Resp([])

    monkeypatch.setattr("factory_products.httpx.Client", _Client)
    first, auth1 = resolve_factory_catalog("http://factory.test")
    assert auth1 is True
    assert len(first) == 1
    second, auth2 = resolve_factory_catalog("http://factory.test")
    assert auth2 is False
    assert len(second) == 1
    third, auth3 = resolve_factory_catalog("http://factory.test")
    assert auth3 is False
    assert len(third) == 1
    fourth, auth4 = resolve_factory_catalog("http://factory.test")
    assert auth4 is True
    assert fourth == []
