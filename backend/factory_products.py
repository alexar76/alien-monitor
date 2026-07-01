"""Sync AI-Factory catalog into star-cluster nodes (no overlapping product planets)."""

from __future__ import annotations

import logging
import math
import os
import re
from collections import defaultdict
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_APP_URL = "http://127.0.0.1:9081"
DEFAULT_FETCH_TIMEOUT = 25.0
DEFAULT_CATEGORIES_TIMEOUT = 18.0
GOLDEN_ANGLE = 2.399963229728653282

# Last good Factory catalog + consecutive fetch/empty failures (shared by UNI + LIVE).
_catalog_cache: list[dict[str, Any]] | None = None
_catalog_fail_streak: int = 0


def _catalog_fail_threshold() -> int:
    raw = (os.environ.get("ALIEN_FACTORY_CATALOG_FAIL_THRESHOLD") or "3").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 3


def clear_factory_catalog_cache() -> None:
    """Test helper — reset cached catalog and failure streak."""
    global _catalog_cache, _catalog_fail_streak
    _catalog_cache = None
    _catalog_fail_streak = 0


def resolve_factory_catalog(
    app_url: str,
    *,
    timeout: float | None = None,
) -> tuple[list[dict[str, Any]] | None, bool]:
    """Return (products, authoritative).

    On transient errors or suspicious empty responses, reuses the last good catalog
  until ``ALIEN_FACTORY_CATALOG_FAIL_THRESHOLD`` consecutive failures (default 3).
    ``authoritative=False`` means callers must not delete products missing from the list.
    """
    global _catalog_cache, _catalog_fail_streak

    fresh = fetch_factory_products_sync(app_url, timeout=timeout)
    threshold = _catalog_fail_threshold()

    if fresh is None:
        _catalog_fail_streak += 1
        if _catalog_cache is not None:
            logger.warning(
                "factory catalog unreachable (streak %s/%s) — keeping %s cached products",
                _catalog_fail_streak,
                threshold,
                len(_catalog_cache),
            )
            return list(_catalog_cache), False
        cats = fetch_factory_categories_sync(app_url)
        if cats:
            pseudo = _products_from_categories(cats)
            logger.warning(
                "factory /api/products slow/unreachable — built %s clusters from /categories",
                len({_cluster_key(p) for p in pseudo}),
            )
            return pseudo, False
        count = fetch_storefront_count_sync(app_url)
        if count and count > 0:
            pseudo = _products_from_storefront_count(count)
            logger.warning(
                "factory catalog endpoints slow — using storefront-count fallback (%s products)",
                count,
            )
            return pseudo, False
        return None, False

    if not fresh and _catalog_cache:
        _catalog_fail_streak += 1
        if _catalog_fail_streak < threshold:
            logger.warning(
                "factory catalog empty but cache has %s products (streak %s/%s) — keeping cache",
                len(_catalog_cache),
                _catalog_fail_streak,
                threshold,
            )
            return list(_catalog_cache), False
        logger.warning(
            "factory catalog empty after %s consecutive issues — accepting empty catalog",
            _catalog_fail_streak,
        )
        _catalog_cache = []
        _catalog_fail_streak = 0
        return [], True

    _catalog_fail_streak = 0
    _catalog_cache = list(fresh)
    return list(fresh), True


def _fetch_timeout() -> float:
    raw = (os.environ.get("ALIEN_FACTORY_API_TIMEOUT") or "").strip()
    if raw:
        try:
            return max(3.0, float(raw))
        except ValueError:
            pass
    return DEFAULT_FETCH_TIMEOUT


def fetch_factory_products_sync(
    app_url: str,
    *,
    timeout: float | None = None,
) -> list[dict[str, Any]] | None:
    """Return storefront products, ``[]`` when API responds with none, ``None`` on transport/error."""
    effective_timeout = timeout if timeout is not None else _fetch_timeout()
    url = f"{app_url.rstrip('/')}/api/products"
    try:
        with httpx.Client(timeout=effective_timeout) as client:
            r = client.get(url)
            if r.status_code != 200:
                logger.warning(
                    "factory catalog fetch failed: %s status=%s",
                    url,
                    r.status_code,
                )
                return None
            data = r.json()
            return list(data.get("products") or [])
    except Exception as exc:
        logger.warning("factory catalog fetch failed: %s (%s)", url, exc)
        return None


def _categories_timeout() -> float:
    raw = (os.environ.get("ALIEN_FACTORY_CATEGORIES_TIMEOUT") or "").strip()
    if raw:
        try:
            return max(2.0, float(raw))
        except ValueError:
            pass
    return DEFAULT_CATEGORIES_TIMEOUT


def fetch_factory_categories_sync(
    app_url: str,
    *,
    timeout: float | None = None,
) -> dict[str, Any] | None:
    """Fast storefront category counts — used when GET /api/products is too slow."""
    effective_timeout = timeout if timeout is not None else _categories_timeout()
    url = f"{app_url.rstrip('/')}/api/products/categories"
    try:
        with httpx.Client(timeout=effective_timeout) as client:
            r = client.get(url)
            if r.status_code != 200:
                logger.warning("factory categories fetch failed: %s status=%s", url, r.status_code)
                return None
            data = r.json()
            return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.warning("factory categories fetch failed: %s (%s)", url, exc)
        return None


def _products_from_categories(categories_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Synthesize minimal product rows from category counts for cluster layout."""
    out: list[dict[str, Any]] = []
    for cat in categories_payload.get("categories") or []:
        if not isinstance(cat, dict):
            continue
        count = int(cat.get("product_count") or 0)
        if count <= 0:
            continue
        key = str(cat.get("id") or "other")
        name = str(cat.get("name") or key)
        for i in range(count):
            out.append({
                "id": f"cat-{key}-{i}",
                "name": f"{name} #{i + 1}",
                "category": key,
            })
    return out


def fetch_storefront_count_sync(
    app_url: str,
    *,
    timeout: float | None = None,
) -> int | None:
    """Fast cached total from Factory — returns even when ``stale=true``."""
    effective_timeout = timeout if timeout is not None else _categories_timeout()
    url = f"{app_url.rstrip('/')}/api/products/storefront-count"
    try:
        with httpx.Client(timeout=min(5.0, effective_timeout)) as client:
            r = client.get(url)
            if r.status_code != 200:
                return None
            data = r.json()
            if not isinstance(data, dict):
                return None
            count = data.get("count")
            return int(count) if count is not None else None
    except Exception as exc:
        logger.warning("factory storefront-count fetch failed: %s (%s)", url, exc)
        return None


def _products_from_storefront_count(count: int) -> list[dict[str, Any]]:
    return [
        {"id": f"storefront-{i}", "name": f"Product {i + 1}", "category": "products"}
        for i in range(max(0, count))
    ]


def ensure_factory_clusters(
    nodes: list[dict],
    links: list[dict],
    app_url: str,
    *,
    catalog_timeout: float | None = None,
) -> int:
    """Attach factory star-clusters — full catalog when fast enough, else /categories."""
    catalog, authoritative = resolve_factory_catalog(app_url, timeout=catalog_timeout)
    if catalog is not None:
        return merge_factory_products(
            nodes,
            links,
            catalog,
            app_url=app_url,
            authoritative=authoritative,
        )
    return 0


def _cluster_key(product: dict[str, Any]) -> str:
    if product.get("is_template"):
        return "templates"
    cat = str(product.get("category") or "other").strip().lower()
    cat = re.sub(r"[^a-z0-9_-]+", "-", cat)[:32] or "other"
    return cat


def _cluster_label(key: str, count: int) -> str:
    labels = {
        "templates": "Templates",
        "landings": "Landings",
        "saas": "SaaS apps",
        "other": "Products",
    }
    base = labels.get(key, key.replace("-", " ").title())
    return f"{base} · {count}"


def build_product_clusters(
    products: list[dict[str, Any]],
    *,
    existing_ids: set[str],
    factory_position: dict[str, float] | None = None,
    app_url: str = DEFAULT_APP_URL,
    id_prefix: str = "cluster",
) -> tuple[list[dict], list[dict]]:
    """One nebula cluster per category/templates — members in children, spaced on a spiral."""
    fp = factory_position or {"x": 4, "y": 2, "z": -2}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for p in products:
        grouped[_cluster_key(p)].append(p)

    nodes: list[dict] = []
    links: list[dict] = []
    keys = sorted(grouped.keys(), key=lambda k: (-len(grouped[k]), k))

    for i, key in enumerate(keys):
        items = grouped[key]
        cid = f"{id_prefix}-{key}"
        if cid in existing_ids:
            continue

        angle = i * GOLDEN_ANGLE
        ring = i // 6
        radius = 5.0 + ring * 2.2
        height = math.sin(i * 0.7) * 1.2 + ring * 0.35

        nodes.append({
            "id": cid,
            "label": _cluster_label(key, len(items)),
            "group": "cluster",
            "icon": "cluster",
            "description": f"Star cluster — {len(items)} factory products ({key})",
            "metrics": {
                "count": len(items),
                "category": key,
                "templates": sum(1 for x in items if x.get("is_template")),
            },
            "status": "active",
            "position": {
                "x": fp["x"] + math.cos(angle) * radius,
                "y": fp["y"] + height,
                "z": fp["z"] + math.sin(angle) * radius,
            },
            "url": app_url.rstrip("/"),
            "children": [
                {
                    "id": str(p.get("id") or f"p{i}"),
                    "label": str(p.get("name") or p.get("id"))[:64],
                }
                for i, p in enumerate(items[:80])
            ],
        })
        links.append({"source": "factory", "target": cid, "label": "catalog"})
        existing_ids.add(cid)

    return nodes, links


def merge_factory_products(
    nodes: list[dict],
    links: list[dict],
    products: list[dict[str, Any]] | None,
    *,
    app_url: str = DEFAULT_APP_URL,
    authoritative: bool = True,
) -> int:
    """Replace per-product nodes with spaced clusters; return cluster count."""
    if products is None:
        cached = _catalog_cache
        if cached:
            products = list(cached)
            authoritative = False
        else:
            return 0
    if not authoritative and not products:
        return 0
    nodes[:] = [n for n in nodes if n.get("group") not in ("product", "cluster")]
    links[:] = [
        lnk
        for lnk in links
        if not (
            lnk.get("target", "").startswith("cluster-")
            or lnk.get("target", "").startswith("prod-")
            or (lnk.get("source") == "factory" and lnk.get("label") == "published")
        )
    ]
    existing = {n["id"] for n in nodes}
    factory = next((n for n in nodes if n.get("id") == "factory"), None)
    fp = (factory or {}).get("position")
    extra_nodes, extra_links = build_product_clusters(
        products,
        existing_ids=existing,
        factory_position=fp,
        app_url=app_url,
    )
    nodes.extend(extra_nodes)
    links.extend(extra_links)
    if factory is not None:
        factory.setdefault("metrics", {})["products"] = sum(
            int((n.get("metrics") or {}).get("count") or 0) for n in extra_nodes
        )
        factory["status"] = "active"
    return len(extra_nodes)


def collapse_graph_products(
    nodes: list[dict],
    links: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Merge individual product nodes into clusters (UNI materialized planets, etc.)."""
    products: list[dict[str, Any]] = []
    for n in nodes:
        if n.get("group") != "product":
            continue
        m = n.get("metrics") or {}
        products.append({
            "id": n.get("id"),
            "name": n.get("label"),
            "category": m.get("category", "other"),
            "description": n.get("description"),
            "is_template": m.get("category") == "templates" or "template" in str(n.get("id", "")).lower(),
        })
    if not products:
        return nodes, links
    product_ids = {n["id"] for n in nodes if n.get("group") == "product"}
    core_nodes = [n for n in nodes if n.get("group") != "product"]
    core_links = [
        lnk
        for lnk in links
        if lnk.get("target") not in product_ids and lnk.get("source") not in product_ids
    ]
    merge_factory_products(core_nodes, core_links, products)
    return core_nodes, core_links
