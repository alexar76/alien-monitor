"""The map of the visible universe: one place that knows which coordinates are taken.

Positions in this codebase come from at least four independent authors — the hardcoded
`NODE_POSITIONS` table, a dozen `*_layers` modules that place their own nodes, the ring/slot
helpers in `ecosystem_layout`, and hub discovery for peers nobody has ever seen. Each keeps
its own nodes apart and none of them can see the others, so "does this spot already have a
planet in it" was a question with no owner. Adding a subsystem therefore meant guessing a
free region of space and finding out visually whether the guess was wrong.

This is that owner. It runs once, over the assembled graph, immediately before the snapshot
leaves the backend — so it does not matter who authored a position or in which module: two
planets cannot end up inside each other.

Three properties it has to have, and the reasons they are not negotiable:

* **Stable.** The same graph must produce the same coordinates every tick, or the map
  shimmers. Nodes are processed in a fixed order and displaced by a deterministic function
  of their id, never by iteration order or a random jitter.
* **Conservative.** A node that is already clear of everything else is never moved. Only a
  genuine overlap displaces anything, and the node that moves is the one that arrived later
  in priority order — so the familiar core layout stays exactly where operators expect it and
  newcomers give way, not the other way round.
* **Bounded.** Displacement walks a golden-angle spiral outward from the node's own preferred
  spot, so a crowded region spreads into a disc around itself rather than throwing a node
  across the map, and it gives up after a fixed number of attempts rather than looping.
"""
from __future__ import annotations

import math
from typing import Any, Iterable

#: Minimum centre-to-centre distance between any two nodes, in scene units. Node spheres
#: render at roughly 0.3–0.5 radius, so anything under ~0.8 reads as two objects touching;
#: the live federation's worst pair before the slot rings was 0.836.
MIN_SEPARATION = 0.9

#: A hub is not a planet. The scene draws it with orbit belts, a corona, a gravity well and
#: its own point light — about two units of glow — so two of them need both footprints plus
#: room to read a label through. Mirrors HUB_MIN_GAP in the frontend's federationLayout.ts.
SUN_SEPARATION = 4.6

#: Groups drawn as suns (frontend `isHubRole`). A hop-2 hub is reached only through somebody
#: else and is drawn as a planet in THEIR constellation, so it is not in here.
SUN_GROUPS = frozenset({"peer_hub", "pending_hub"})

#: Ids that are suns whatever their group says.
SUN_IDS = frozenset({"hub", "factory", "competing_hub", "signal_hunt_hub"})


def clearance_for(node: dict[str, Any]) -> float:
    """How much empty space this node needs around it, in scene units."""
    if str(node.get("id") or "") in SUN_IDS:
        return SUN_SEPARATION
    if str(node.get("role") or "") == "hub" or str(node.get("group") or "") in SUN_GROUPS:
        # A hub that arrived through somebody else is a planet in their system; only a
        # first-hop hub is a sun on this map.
        return SUN_SEPARATION if int(node.get("hop") or 0) <= 1 else MIN_SEPARATION
    return MIN_SEPARATION


#: Nodes whose position is part of the layout people already know. They are placed first and
#: never displaced — everything else moves around them.
ANCHOR_GROUPS = frozenset({
    "core", "contract", "chain", "network", "infra", "economy", "cluster",
})

_GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))
_MAX_ATTEMPTS = 64
_STEP = MIN_SEPARATION * 0.75


def _key(node: dict[str, Any]) -> str:
    return str(node.get("id") or node.get("label") or "")


def _seed(node_id: str) -> float:
    """A per-node angle offset, so two nodes displaced from the same spot go different ways."""
    return (sum(ord(ch) for ch in node_id) % 360) * math.pi / 180.0


def _priority(node: dict[str, Any]) -> tuple[int, str]:
    """Who keeps their spot when two want the same one.

    Anchors first, then suns, then everything else alphabetically by id. Alphabetical rather
    than "whatever order the graph was built in" because that order changes with what is
    live, and a map that rearranges itself when an unrelated service restarts is unreadable.
    Suns go early because they claim the most room: letting a 0.9-radius planet take a spot
    first only to displace a 4.6-radius hub around it is how the crowding came back.
    """
    group = str(node.get("group") or "")
    if group in ANCHOR_GROUPS:
        return (0, _key(node))
    if clearance_for(node) > MIN_SEPARATION:
        return (1, _key(node))
    return (2, _key(node))


def _distance(a: dict[str, float], b: dict[str, float]) -> float:
    return math.sqrt(
        (a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2 + (a["z"] - b["z"]) ** 2
    )


def _valid(position: Any) -> dict[str, float] | None:
    if not isinstance(position, dict):
        return None
    try:
        out = {axis: float(position[axis]) for axis in ("x", "y", "z")}
    except (KeyError, TypeError, ValueError):
        return None
    if any(not math.isfinite(v) for v in out.values()):
        return None
    return out


class SpaceMap:
    """Claimed coordinates, and the rule for finding a free one."""

    def __init__(self, min_separation: float = MIN_SEPARATION):
        self.min_separation = float(min_separation)
        self._taken: list[tuple[str, dict[str, float], float]] = []

    def is_free(
        self, position: dict[str, float], *, ignore: str = "", clearance: float | None = None
    ) -> bool:
        """Free for a node that needs `clearance` around it.

        The gap two nodes need is whichever of them needs LESS, and the asymmetry is the
        point: the 4.6 a hub claims is a rule between HUBS. Reading it as "nothing may come
        within 4.6 of a sun" evicts the sun's own constellation — a hub's peers orbit it at
        2.2, and applying the sun rule to them threw all four of them out of their system.
        """
        want = self.min_separation if clearance is None else float(clearance)
        return all(
            node_id == ignore or _distance(position, taken) >= min(want, taken_clearance)
            for node_id, taken, taken_clearance in self._taken
        )

    def claim(
        self,
        node_id: str,
        preferred: dict[str, float],
        *,
        clearance: float | None = None,
    ) -> dict[str, float]:
        """Take ``preferred`` if it is free, otherwise the nearest free spot on a spiral.

        The spiral is in the XZ plane with a small Y lift per turn: the graph is read from
        above more often than from the side, so spreading sideways keeps a cluster legible
        while a purely vertical stack would hide nodes behind each other.
        """
        want = self.min_separation if clearance is None else float(clearance)
        if self.is_free(preferred, ignore=node_id, clearance=want):
            self._taken.append((node_id, preferred, want))
            return preferred

        # The step scales with what this node needs: 64 attempts at a planet-sized stride
        # cannot carry a sun out of another sun's halo.
        step = want * 0.75
        base_angle = _seed(node_id)
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            angle = base_angle + attempt * _GOLDEN_ANGLE
            radius = step * math.sqrt(attempt)
            candidate = {
                "x": round(preferred["x"] + radius * math.cos(angle), 3),
                "y": round(preferred["y"] + (attempt % 3 - 1) * 0.18, 3),
                "z": round(preferred["z"] + radius * math.sin(angle), 3),
            }
            if self.is_free(candidate, ignore=node_id, clearance=want):
                self._taken.append((node_id, candidate, want))
                return candidate

        # Out of attempts: keep the node visible where it wanted to be rather than dropping
        # it or pushing it somewhere arbitrary. A crowded map is still a map; a missing node
        # is a lie about what exists.
        self._taken.append((node_id, preferred, want))
        return preferred


def enforce_spacing(
    nodes: Iterable[dict[str, Any]], *, min_separation: float = MIN_SEPARATION
) -> int:
    """Space out an assembled graph in place. Returns how many nodes had to move.

    Called once, at the end, on whatever the backend is about to send. Nodes without a usable
    position are left alone: giving one an invented coordinate would put a planet somewhere
    nothing exists, and the frontend already refuses to render them.
    """
    space = SpaceMap(min_separation)
    moved = 0
    for node in sorted((n for n in nodes if isinstance(n, dict)), key=_priority):
        preferred = _valid(node.get("position"))
        if preferred is None:
            continue
        placed = space.claim(_key(node), preferred, clearance=clearance_for(node))
        if placed is not preferred:
            node["position"] = placed
            moved += 1
    return moved
