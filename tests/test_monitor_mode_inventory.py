"""Monitor graph inventory — required nodes per mode."""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from factory_products import (  # noqa: E402
    _products_from_categories,
    resolve_factory_catalog,
)
from oracle_family import CAVE, ORACLE_FAMILY, oracle_node_id  # noqa: E402

CORE_IDS = {
    "hub", "factory", "mesh", "acex", "evm_escrow", "solana_escrow", "nft_contract",
    "desktop_apps", "plugins", "sdk_dart", "sdk_typescript", "sdk_rust", "federation",
    "widget", "ethereum", "solana", "cli", "lottery", "argus",
}
ORACLE_IDS = {oracle_node_id(o["slug"]) for o in ORACLE_FAMILY} | {CAVE["id"]}


def test_products_from_categories_builds_cluster_rows():
    payload = {
        "categories": [
            {"id": "saas", "name": "SaaS", "product_count": 2},
            {"id": "devtools", "name": "DevTools", "product_count": 0},
        ],
        "total_count": 2,
    }
    rows = _products_from_categories(payload)
    assert len(rows) == 2
    assert all(r["category"] == "saas" for r in rows)


def test_resolve_factory_catalog_falls_back_to_categories(monkeypatch):
    import factory_products as fp

    monkeypatch.setattr(fp, "fetch_factory_products_sync", lambda *a, **k: None)
    monkeypatch.setattr(
        fp,
        "fetch_factory_categories_sync",
        lambda *a, **k: {
            "categories": [{"id": "landings", "name": "Landings", "product_count": 3}],
            "total_count": 3,
        },
    )
    monkeypatch.setattr(fp, "fetch_storefront_count_sync", lambda *a, **k: None)
    fp.clear_factory_catalog_cache()
    catalog, auth = resolve_factory_catalog("http://factory.test")
    assert auth is False
    assert catalog is not None
    assert len(catalog) == 3


def test_resolve_factory_catalog_falls_back_to_storefront_count(monkeypatch):
    import factory_products as fp

    monkeypatch.setattr(fp, "fetch_factory_products_sync", lambda *a, **k: None)
    monkeypatch.setattr(fp, "fetch_factory_categories_sync", lambda *a, **k: None)
    monkeypatch.setattr(fp, "fetch_storefront_count_sync", lambda *a, **k: 5)
    fp.clear_factory_catalog_cache()
    catalog, auth = resolve_factory_catalog("http://factory.test")
    assert auth is False
    assert catalog is not None
    assert len(catalog) == 5


def test_live_fetch_has_oracles_and_clusters(monkeypatch):
    import asyncio

    import factory_products as fp
    from main import fetch_real_metrics

    monkeypatch.setattr(fp, "fetch_factory_products_sync", lambda *a, **k: None)
    monkeypatch.setattr(
        fp,
        "fetch_factory_categories_sync",
        lambda *a, **k: {
            "categories": [
                {"id": "saas", "name": "SaaS", "product_count": 2},
                {"id": "landings", "name": "Landings", "product_count": 4},
            ],
            "total_count": 6,
        },
    )
    monkeypatch.setattr(fp, "fetch_storefront_count_sync", lambda *a, **k: None)
    fp.clear_factory_catalog_cache()

    state = asyncio.run(fetch_real_metrics())
    ids = {n["id"] for n in state["nodes"]}
    groups = {n.get("group") for n in state["nodes"]}
    assert CORE_IDS.issubset(ids)
    assert ORACLE_IDS.issubset(ids)
    assert "cluster" in groups
