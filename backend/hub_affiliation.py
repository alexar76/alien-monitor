"""Stamp every Alien Monitor node with the hub it belongs to.

Operators need this on the detail card — which federation Hub owns / lists / settles
for this surface. Rules:

- A hub node belongs to itself.
- Signal Hunt game → Signal Hunt Hub.
- Use Cases portal → Competing Lab Hub.
- Other competing-galaxy nodes → Competing Lab Hub (default lab edge).
- Auto-discovered federation peers → themselves.
- Everything else in the primary galaxy → AIMarket Hub (``HUB_URL``).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from competing_lab_layers import competing_hub_url, signal_hunt_url


def _host(url: str | None) -> str:
    if not url:
        return ""
    try:
        p = urlparse(url if "://" in url else f"http://{url}")
        host = (p.hostname or "").lower()
        port = p.port
        if port and port not in (80, 443):
            return f"{host}:{port}"
        return host
    except Exception:
        return str(url).lower().strip()


def _hub_ref(*, hid: str, label: str, url: str | None = None) -> dict[str, str]:
    out = {"id": hid, "label": label}
    if url:
        out["url"] = url
    return out


def apply_hub_affiliation(
    nodes: list[dict[str, Any]],
    *,
    primary_hub_url: str,
    primary_label: str = "AIMarket Hub",
) -> None:
    """Mutate ``nodes`` in place — set ``hub: {id, label, url?}`` on each."""
    primary = primary_hub_url.rstrip("/")
    lab = competing_hub_url().rstrip("/")
    hunt = signal_hunt_url().rstrip("/")
    primary_host = _host(primary)
    lab_host = _host(lab)
    hunt_host = _host(hunt)

    primary_hub = _hub_ref(hid="hub", label=primary_label, url=primary)
    lab_hub = _hub_ref(hid="competing_hub", label="Competing Lab Hub", url=lab)
    hunt_hub = _hub_ref(hid="signal_hunt_hub", label="Signal Hunt Hub", url=hunt)

    for node in nodes:
        if not isinstance(node, dict) or not node.get("id"):
            continue
        nid = str(node["id"])
        url = (node.get("url") or "").rstrip("/")
        host = _host(url)

        if nid == "hub":
            node["hub"] = dict(primary_hub)
            continue

        if nid == "competing_hub":
            node["hub"] = _hub_ref(
                hid="competing_hub",
                label=str(node.get("label") or "Competing Lab Hub"),
                url=url or lab,
            )
            continue

        if nid == "signal_hunt_hub":
            node["hub"] = _hub_ref(
                hid="signal_hunt_hub",
                label=str(node.get("label") or "Signal Hunt Hub"),
                url=url or hunt,
            )
            continue

        # Game belongs to Signal Hunt Hub; use portal to Competing Lab Hub.
        if nid == "signal_hunt":
            node["hub"] = dict(hunt_hub)
            continue

        if nid == "use_cases" or node.get("galaxy") == "competing":
            node["hub"] = dict(lab_hub)
            continue

        if host and host == hunt_host:
            node["hub"] = dict(hunt_hub)
            continue
        if host and host == lab_host:
            node["hub"] = dict(lab_hub)
            continue
        if host and primary_host and host == primary_host:
            node["hub"] = dict(primary_hub)
            continue

        if node.get("discovered") and url:
            node["hub"] = _hub_ref(
                hid=nid,
                label=str(node.get("label") or nid),
                url=url,
            )
            continue

        node["hub"] = dict(primary_hub)
