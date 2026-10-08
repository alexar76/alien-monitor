"""What colour a node is, and why.

Colour on this map has been carrying provenance, badly. Every federated node that was not
a hub fell to one default — `#a64dff` on the UNI path, and nothing at all on the LIVE path,
where the frontend then painted it core cyan. So the same KOVA was purple on one of our maps
and cyan on the other, three unrelated services under one hub were identically purple, and a
second operator's satellites would have been that same purple: a federation that grows into
one flat colour, which is the same as having no colour at all.

Provenance is already on the map three times over — a sun is a hub and a planet is not, a
node sits inside the constellation of whoever it belongs to, and the card names its hub. So
colour is free to carry the one thing nothing else shows about a foreign node: **what it
does**. An oracle is violet whoever runs it; a sensor gateway is green whoever runs it.

The families are the same ones our own shelf already uses, so a peer's ATLAS-shaped service
and our ATLAS read as the same kind of thing — which is the honest statement, and the one an
operator scanning a thousand hubs actually needs.
"""

from __future__ import annotations

import colorsys
import hashlib
from typing import Iterable, Sequence

#: Family → hex. Mirrors GROUP_COLORS in the frontend; the two must agree or a node changes
#: colour depending on whether the server had an opinion.
FAMILY_COLORS: dict[str, str] = {
    "oracle": "#a64dff",
    "physical": "#43e65a",
    "security": "#ff2d6f",
    "observability": "#00e5cc",
    "cognition": "#9b59ff",
    "economy": "#ffd700",
    "media": "#ff4466",
    "agent": "#66ffcc",
    "client": "#00ff88",
    "infra": "#7b2fff",
}

#: (hue°, spread°, saturation, lightness) per family — a BAND, not a single colour.
#:
#: One colour per family fixes a purple universe by making a crimson one: twelve security
#: services under one hub arrive identical, and the reader cannot tell which planet they
#: clicked last. A family therefore owns a narrow arc of hue, and a node picks its shade
#: inside that arc from its own id — deterministic, so it never shimmers between ticks, and
#: narrow, so the family still reads as one thing at a glance.
FAMILY_BANDS: dict[str, tuple[float, float, float, float]] = {
    "oracle": (272.0, 16.0, 1.00, 0.65),
    "physical": (132.0, 20.0, 0.78, 0.58),
    "security": (340.0, 16.0, 1.00, 0.59),
    "observability": (172.0, 18.0, 1.00, 0.45),
    "cognition": (258.0, 14.0, 0.90, 0.67),
    "economy": (48.0, 12.0, 1.00, 0.50),
    "media": (350.0, 12.0, 1.00, 0.64),
    "agent": (162.0, 16.0, 1.00, 0.70),
    "client": (150.0, 16.0, 1.00, 0.50),
    "infra": (262.0, 14.0, 0.85, 0.59),
}

#: A federated service that has declared nothing about itself.
#:
#: Grey was the wrong answer twice over: it swapped a purple universe for a grey one, and
#: it is not what honesty required. The dishonest thing was painting an undeclared node
#: ORACLE VIOLET — asserting a family nobody claimed. A colour that belongs to no family
#: asserts nothing, so it may be as vivid as any other.
#:
#: So an undeclared node takes a saturated hue drawn from the GAPS between the family arcs.
#: It is colourful and distinct, and it still cannot impersonate a meaning: every hue inside
#: a family arc belongs to that family, and nothing else is ever placed there.
UNCLASSIFIED = "#8a93a6"  # kept as the frontend's static fallback only
UNCLASSIFIED_SATURATION = 0.72
UNCLASSIFIED_LIGHTNESS = 0.58


def _family_arcs() -> list[tuple[float, float]]:
    """Merged [start, end] hue arcs the families occupy, in degrees."""
    raw: list[tuple[float, float]] = []
    for base, spread, _s, _l in FAMILY_BANDS.values():
        raw.append(((base - spread) % 360.0, (base + spread) % 360.0))
    spans: list[tuple[float, float]] = []
    for lo, hi in raw:
        spans.append((lo, hi + 360.0) if hi < lo else (lo, hi))
    spans.sort()
    merged: list[tuple[float, float]] = []
    for lo, hi in spans:
        if merged and lo <= merged[-1][1] + 4.0:  # 4° of breathing room between arcs
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


def _free_gaps() -> list[tuple[float, float]]:
    """The hue arcs no family claims — where an undeclared node may live."""
    arcs = _family_arcs()
    gaps: list[tuple[float, float]] = []
    for i, (_lo, hi) in enumerate(arcs):
        nxt = arcs[(i + 1) % len(arcs)][0] + (360.0 if i + 1 >= len(arcs) else 0.0)
        if nxt - hi > 8.0:  # a gap narrower than this is not worth a colour
            gaps.append((hi + 4.0, nxt - 4.0))
    return gaps

#: Hubs keep their own colours: a hub is not a capability service and must not look like one.
STRUCTURAL_COLORS: dict[str, str] = {
    "peer_hub": "#38e0ff",
    "peer_hub_node": "#7fd4ff",
    "pending_hub": "#ffcc4d",
    "pending_hub_node": "#c9a04d",
}

#: category → family. Drawn from what peers actually publish today; unknown words simply do
#: not match, which lands the node on UNCLASSIFIED rather than on a guess.
_CATEGORY_FAMILY: dict[str, str] = {}


def _register(family: str, *words: str) -> None:
    for word in words:
        _CATEGORY_FAMILY[word] = family


_register(
    "oracle",
    "oracle", "randomness-beacon", "randomness", "verifiable-delay", "vdf", "consensus",
    "sampling", "percolation", "optimization", "entropy", "proof", "zk",
)
_register(
    "physical",
    "iot", "sensors", "sensor", "physical-data", "geospatial", "weather", "air-quality",
    "energy", "seismic", "gnss-integrity", "wildfire", "watchbox", "risk-brief", "telemetry",
)
_register(
    "security",
    "security", "red-team", "audit", "adversarial", "assurance", "solidity", "conformance",
    "procurement", "supply-chain", "admission", "verification", "firewall", "safety",
)
_register(
    "observability", "observability", "analytics", "federation", "fleet", "monitoring",
)
_register(
    "cognition", "reasoning", "inference", "llm", "embedding", "reputation", "knowledge",
)
_register(
    "economy",
    "payments", "payment", "usdc", "invoice", "billing", "escrow", "settlement", "treasury",
    "wallet", "blockchain", "onchain",
)
_register("media", "video", "image", "audio", "render", "speech", "voice")
_register("agent", "agent", "agents", "automation", "orchestration")


def family_for(categories: Sequence[str] | None) -> str | None:
    """Which family a service belongs to, from what it says about itself.

    The FIRST recognised category wins. Peers list their primary category first — ATLAS
    leads with `iot`, MOMUS with `security`, LOGOS with `analytics`, SKOPOS with
    `observability` — and scoring by overlap instead would put SKOPOS in security because it
    also mentions the word once.
    """
    for raw in categories or ():
        family = _CATEGORY_FAMILY.get(str(raw).strip().lower())
        if family:
            return family
    return None


def _hex(h: float, sat: float, light: float) -> str:
    r, g, b = colorsys.hls_to_rgb((h % 360.0) / 360.0, light, sat)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def _offset(seed: str) -> float:
    """A stable -1..1 for this node, from its id.

    blake2b rather than `hash()`: Python salts str hashing per process, so the same node
    would change shade on every restart — a map that shimmers when nothing moved.
    """
    if not seed:
        return 0.0
    digest = hashlib.blake2b(seed.encode("utf-8"), digest_size=4).digest()
    return (int.from_bytes(digest, "big") / 0xFFFFFFFF) * 2.0 - 1.0


#: Golden angle as a fraction of a turn. Successive siblings placed this far apart never
#: bunch, at any count — the same reason the layout uses it for orbital slots.
_GOLDEN_FRACTION = 0.6180339887498949


def _fraction(seed: str, sibling: int | None, sibling_seed: str) -> float:
    """Where in its available hue range this node sits, as 0..1.

    A hash alone is uniform but not SPREAD: three providers under one hub drew three
    magentas within thirty degrees of each other on the live map, because three samples
    from a uniform distribution are allowed to land together. Siblings are therefore walked
    by the golden angle from a per-hub starting point — different hubs start elsewhere, and
    within a hub no two children can bunch however many there are.
    """
    if sibling is None:
        return (_offset(seed) + 1.0) / 2.0
    start = (_offset(sibling_seed or seed) + 1.0) / 2.0
    return (start + sibling * _GOLDEN_FRACTION) % 1.0


def shade_for(
    family: str | None,
    seed: str = "",
    *,
    sibling: int | None = None,
    sibling_seed: str = "",
) -> str:
    """One node's exact colour: inside its family's arc, or in the space between arcs."""
    frac = _fraction(seed, sibling, sibling_seed)
    band = FAMILY_BANDS.get(str(family or ""))
    if band is not None:
        base, spread, sat, light = band
        return _hex(base + spread * (frac * 2.0 - 1.0), sat, light)
    gaps = _free_gaps()
    if not gaps:  # pragma: no cover - only if the families ever cover the whole circle
        return UNCLASSIFIED
    total = sum(hi - lo for lo, hi in gaps)
    pos = frac * total
    for lo, hi in gaps:
        if pos <= hi - lo:
            return _hex(lo + pos, UNCLASSIFIED_SATURATION, UNCLASSIFIED_LIGHTNESS)
        pos -= hi - lo
    lo, hi = gaps[-1]
    return _hex(hi, UNCLASSIFIED_SATURATION, UNCLASSIFIED_LIGHTNESS)


def color_for(
    group: str | None = None,
    categories: Iterable[str] | None = None,
    *,
    role: str | None = None,
    node_id: str = "",
    sibling: int | None = None,
    sibling_seed: str = "",
) -> str:
    """The colour a federated node should be drawn in.

    Structural kinds (a hub, a stranger) keep their own colour — what they ARE is the point.
    Everything else is coloured by what it does, and by nothing at all when it has not said.
    """
    key = str(group or "")
    cats = list(categories or ())
    family = family_for(cats)

    # A hub keeps hub-cyan when it is only a hub. But most of what declares `hub_version` in
    # this federation is a capability service that happens to serve a hub-shaped well-known
    # — ATLAS leads with `iot`, MOMUS with `security` — and painting ten of those one cyan
    # is the same flat universe one level up. So a hub that says what it serves is coloured
    # by that; a hub that says nothing (a real federation hub: modelmarket.dev, Signal Hunt)
    # stays cyan. Nothing is lost: a hub is a SUN, which no planet ever is.
    if key in ("peer_hub", "peer_hub_node") or str(role or "") == "hub":
        return shade_for(
            family, node_id, sibling=sibling, sibling_seed=sibling_seed
        ) if family else STRUCTURAL_COLORS.get(key, STRUCTURAL_COLORS["peer_hub"])
    if key in STRUCTURAL_COLORS:
        return STRUCTURAL_COLORS[key]
    if family:
        return shade_for(family, node_id, sibling=sibling, sibling_seed=sibling_seed)
    # A family name used directly as a group (our own shelf does this) still resolves.
    if key in FAMILY_BANDS:
        return shade_for(key, node_id, sibling=sibling, sibling_seed=sibling_seed)
    return shade_for(None, node_id, sibling=sibling, sibling_seed=sibling_seed)
