"""Shipping a map that does not fit in a message.

Every tick the backend sent the whole graph over the WebSocket. That is correct and cheap
for the sixty nodes a deployment draws today, and it is the ceiling for everything else:
measured here, five thousand nodes took 35 s to load and fifteen thousand ran at the
software renderer's floor, while fifty thousand killed the browser process outright — not
by drawing, which is now one call for the far field, but by building fifty thousand objects
to describe things the camera cannot resolve.

A hundred thousand hubs therefore needs a different shape, and it is the same split the
renderer already makes:

  DIGEST   every node as five numbers and an id — where it is and what kind of thing it
           is. Enough to draw the star field, useless for anything else. Fetched once per
           epoch over HTTP, paged, never on the tick.
  WINDOW   full node objects for what is near a point. Fetched when the camera moves, and
           bounded by a hard limit rather than by how big the federation happens to be.
  LOCAL    this deployment's own ecosystem, which is small by construction and rides the
           tick as before.

Below the threshold nothing changes at all: the tick carries the whole graph, `windowed` is
false, and no client fetches anything extra. The split exists to remove a ceiling, not to
add a round trip to a map of sixty nodes.
"""

from __future__ import annotations

import hashlib
import math
import os
from typing import Any, Iterable, Sequence

#: Below this many nodes the tick carries everything, exactly as it always has.
#: Fifteen thousand rendered fine; the number here is far under that on purpose — the
#: threshold is where the FULL payload stops being cheap, not where it stops working.
def window_threshold() -> int:
    try:
        return max(0, int(os.getenv("ALIEN_MAP_WINDOW_THRESHOLD", "1500")))
    except ValueError:
        return 1500


#: How many full nodes one window may contain. The renderer builds real bodies for ~150 and
#: keeps the rest as points, so a few hundred is already more than it can show.
def window_limit() -> int:
    try:
        return max(1, int(os.getenv("ALIEN_MAP_WINDOW_LIMIT", "600")))
    except ValueError:
        return 600


#: Digest rows per page. 4000 rows is roughly 200 KB of JSON — one modest response.
DIGEST_PAGE = 4000

#: Kind codes. The client colours the star field from these; it has no node objects to read
#: a group off, which is the whole point.
KIND_LOCAL = 0      # hop 0 — this deployment's own ecosystem
KIND_PEER_HUB = 1   # hop 1 — a hub we federate with
KIND_FAR = 2        # hop 2+ — reached through somebody else
KIND_PENDING = 3    # observed, approved by nobody


def _hop(node: dict[str, Any]) -> int:
    try:
        return max(0, int(node.get("hop") or 0))
    except (TypeError, ValueError):
        return 0


def kind_of(node: dict[str, Any]) -> int:
    group = str(node.get("group") or "")
    if group in ("pending_hub", "pending_hub_node"):
        return KIND_PENDING
    hop = _hop(node)
    if hop == 0:
        return KIND_LOCAL
    if hop == 1:
        return KIND_PEER_HUB
    return KIND_FAR


def is_local(node: dict[str, Any]) -> bool:
    """Rides the tick regardless of map size — it is what this deployment IS."""
    return _hop(node) == 0


def _position(node: dict[str, Any]) -> tuple[float, float, float] | None:
    pos = node.get("position")
    if not isinstance(pos, dict):
        return None
    try:
        out = (float(pos["x"]), float(pos["y"]), float(pos["z"]))
    except (KeyError, TypeError, ValueError):
        return None
    if any(not math.isfinite(v) for v in out):
        return None
    return out


def should_window(nodes: Sequence[dict[str, Any]]) -> bool:
    threshold = window_threshold()
    return bool(threshold) and len(nodes) > threshold


def digest_epoch(nodes: Iterable[dict[str, Any]]) -> str:
    """Changes when the star field changes, and not when a metric ticks.

    Keyed on identity and place only. A digest re-fetch costs a megabyte, so it must not be
    triggered by an invocation counter moving — and it MUST be triggered by a hub appearing,
    which a plain count would miss the moment another one leaves in the same tick.
    """
    digest = hashlib.blake2b(digest_size=12)
    for node in nodes:
        pos = _position(node) or (0.0, 0.0, 0.0)
        digest.update(
            f"{node.get('id')}|{pos[0]:.1f}|{pos[1]:.1f}|{pos[2]:.1f}|{kind_of(node)}\n".encode()
        )
    return digest.hexdigest()


def build_digest(
    nodes: Sequence[dict[str, Any]], *, cursor: int = 0, limit: int = DIGEST_PAGE
) -> dict[str, Any]:
    """One page of the star chart: `[id, x, y, z, kind]` per node, nothing else.

    Positional rows rather than objects, and one decimal of position: at a hundred thousand
    nodes the difference between this and the full payload is megabytes against hundreds.
    """
    usable = [n for n in nodes if isinstance(n, dict) and _position(n)]
    start = max(0, int(cursor))
    page = usable[start:start + max(1, int(limit))]
    rows: list[list[Any]] = []
    for node in page:
        x, y, z = _position(node)  # type: ignore[misc]
        rows.append([str(node.get("id") or ""), round(x, 1), round(y, 1), round(z, 1), kind_of(node)])
    nxt = start + len(page)
    return {
        "epoch": digest_epoch(usable),
        "total": len(usable),
        "cursor": start,
        "next_cursor": nxt if nxt < len(usable) else None,
        "rows": rows,
    }


def select_window(
    nodes: Sequence[dict[str, Any]],
    links: Sequence[dict[str, Any]],
    *,
    center: tuple[float, float, float],
    radius: float,
    limit: int | None = None,
    include_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Full detail for what is near `center`, nearest first.

    `include_ids` is for what the reader is looking AT rather than near — a selected hub the
    camera has not reached yet, and its constellation. Without it, clicking a distant star
    would open a card with nothing behind it.
    """
    cap = window_limit() if limit is None else max(1, int(limit))
    cx, cy, cz = center
    r = max(0.0, float(radius))
    wanted = {str(i) for i in include_ids if i}

    scored: list[tuple[float, dict[str, Any]]] = []
    forced: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = str(node.get("id") or "")
        pos = _position(node)
        if nid in wanted:
            forced.append(node)
            continue
        if pos is None:
            continue
        d = math.dist((cx, cy, cz), pos)
        if d <= r:
            scored.append((d, node))
    scored.sort(key=lambda pair: pair[0])

    # A hub's own constellation comes with it: a sun without its planets is a worse answer
    # than one node fewer, because the reader cannot tell an empty system from an unloaded one.
    chosen: dict[str, dict[str, Any]] = {str(n.get("id")): n for n in forced}
    for _d, node in scored:
        if len(chosen) >= cap:
            break
        chosen[str(node.get("id"))] = node
    if len(chosen) < cap:
        parents = {str(n.get("id")) for n in chosen.values()}
        for node in nodes:
            if len(chosen) >= cap:
                break
            if not isinstance(node, dict):
                continue
            nid = str(node.get("id") or "")
            if nid in chosen:
                continue
            if str(node.get("parent_id") or "") in parents:
                chosen[nid] = node

    ids = set(chosen)
    window_links = [
        link for link in links
        if isinstance(link, dict)
        and str(link.get("source") or "") in ids
        and str(link.get("target") or "") in ids
    ]
    return {
        "center": {"x": cx, "y": cy, "z": cz},
        "radius": r,
        "truncated": len(chosen) >= cap,
        "nodes": list(chosen.values()),
        "links": window_links,
    }


def tick_payload(state: dict[str, Any]) -> dict[str, Any]:
    """The state a windowed tick carries: local nodes, and a pointer to the rest.

    Returned unchanged when the map is small — a deployment with sixty nodes must not start
    making extra round trips because a hundred-thousand-node case exists.
    """
    nodes = state.get("nodes")
    if not isinstance(nodes, list) or not should_window(nodes):
        return state

    local = [n for n in nodes if isinstance(n, dict) and is_local(n)]
    local_ids = {str(n.get("id")) for n in local}
    links = state.get("links")
    local_links = [
        link for link in (links if isinstance(links, list) else [])
        if isinstance(link, dict)
        and str(link.get("source") or "") in local_ids
        and str(link.get("target") or "") in local_ids
    ]
    out = dict(state)
    out["nodes"] = local
    out["links"] = local_links
    out["map"] = {
        "windowed": True,
        "total": len(nodes),
        "local": len(local),
        "epoch": digest_epoch([n for n in nodes if isinstance(n, dict) and _position(n)]),
        "digest_page": DIGEST_PAGE,
        "window_limit": window_limit(),
    }
    return out
