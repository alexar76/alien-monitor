"""Where a fresh deployment goes to learn what the ecosystem looks like.

A monitor with no map is not broken, it is uninformed — and until now the only place it
knew to ask was its own `HUB_URL`. A hub deployed on a new server therefore drew an empty
universe until somebody told it where everyone else lives, which is the hand-configuration
this whole line of work exists to remove.

So there is a bootstrap list, and it is committed: the hubs that already carry the map.
The first one that answers wins; the rest are there for the day it does not. This mirrors
what the hub itself does with `aimarket-hub/aimarket_hub/federation_seeds.json` — an
operator-written starting point that discovery immediately grows past.

Two properties worth stating, because both were bought with incidents:

* The list is a SEED, never an authority. What a source hands back is a peer list, and
  every URL in it is SSRF-checked and folded through the same identity rules as anything
  else (`canonical_peers`); a map source cannot name one of our nodes for us.
* Order is preference, not trust. Falling through to the second entry when the first is
  down must not change what the map says — the sources are all reading the same
  federation, so a fallback is a different vantage point, not a different world.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_CONFIG = Path(__file__).resolve().parent.parent / "config" / "map_sources.json"

# Committed default: the hubs that exist today. `AIMarket Hub` first because it is the one
# with the whole federation in it; the others are real, independently deployed hubs that
# carry their own view of the same thing.
DEFAULT_MAP_SOURCES: tuple[str, ...] = (
    "https://modelmarket.dev",
    "https://hunt.modelmarket.dev",
    "http://108.165.32.182:9083",
)


def _from_env() -> list[str]:
    raw = os.getenv("ALIEN_MAP_SOURCES", "").strip()
    if not raw:
        return []
    return [part.strip().rstrip("/") for part in raw.split(",") if part.strip()]


def _from_file() -> list[str]:
    if not _CONFIG.is_file():
        return []
    try:
        data = json.loads(_CONFIG.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    sources = data.get("sources") if isinstance(data, dict) else data
    if not isinstance(sources, list):
        return []
    return [str(s).strip().rstrip("/") for s in sources if str(s).strip()]


def map_sources(primary: str = "") -> list[str]:
    """Hubs to read the map from, best first, without duplicates.

    ``primary`` — this deployment's own `HUB_URL` — always comes first when set: a hub that
    has its own federation should draw its own federation, and only borrow a view when it
    cannot answer. `ALIEN_MAP_SOURCES` replaces the fallbacks; the committed file, then the
    defaults above, supply them otherwise.
    """
    ordered: list[str] = []
    for url in [primary.strip().rstrip("/")] + (_from_env() or _from_file() or list(DEFAULT_MAP_SOURCES)):
        if url and url not in ordered:
            ordered.append(url)
    return ordered
