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
GOLDEN_ANGLE = 2.399963229728653282


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
) -> int:
    """Replace per-product nodes with spaced clusters; return cluster count."""
    if products is None:
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
