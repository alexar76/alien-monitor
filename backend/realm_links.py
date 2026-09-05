"""Where the other realm lives — so the two maps are navigable from each other.

The ecosystem runs two monitors side by side: the universe map (``ALIEN_MODE=universe``),
which renders the UNI realm's phase and scenario, and the live map (``ALIEN_MODE=real``),
which shows the actual federation including strangers nobody approved. They are separate
processes on separate ports behind separate paths, and until now nothing in either UI
admitted the other existed — you got from one to the other by knowing the URL.

Why the link belongs here and not inside the bubble hub: UNI's premise is that from the
inside it is indistinguishable from the live economy and there is no way out. A "back to
live" link served *by the bubble hub* would be a door in that wall — an agent reading the
page would learn there is an outside. The monitor is not inside the bubble; it is the
observation deck, and an operator standing on it is entitled to see both worlds.

Everything is env-configurable and every default is relative, because a deployment that is
not ours has different paths and must not inherit our hostnames.
"""
from __future__ import annotations

import os

#: Defaults are relative so a stranger's clone does not inherit our hostnames.
#: Production (and any split-host deploy) MUST set ALIEN_UNIVERSE_MAP_URL /
#: ALIEN_LIVE_MAP_URL in the environment — e.g. the two public subdomains.
DEFAULT_UNIVERSE_MAP = "/monitor/"
DEFAULT_LIVE_MAP = "/monitor-live/"


def _clean(value: str) -> str:
    return (value or "").strip()


def universe_map_url() -> str:
    return _clean(os.getenv("ALIEN_UNIVERSE_MAP_URL", "")) or DEFAULT_UNIVERSE_MAP


def live_map_url() -> str:
    return _clean(os.getenv("ALIEN_LIVE_MAP_URL", "")) or DEFAULT_LIVE_MAP


def uni_hub_url() -> str:
    """The bubble's own hub, if this deployment has one. No default: most do not."""
    return _clean(os.getenv("ALIEN_UNI_HUB_URL", "")).rstrip("/")


def session_tick_mode(requested: str | None, server_mode: str) -> str:
    """What this process may actually tick.

    LIVE and UNI are separate processes. A universe monitor that honors ``mode=real``
    would poll *this* process's hub (the bubble) and paint those numbers as live money.
    The same in reverse: ticking universe on the live map would invent a bubble next to
    real settlement. TEST is a local overlay on whichever map you are standing on.
    """
    req = (requested or "").strip().lower()
    srv = (server_mode or "").strip().lower()
    if srv not in ("test", "real", "universe"):
        srv = "test"
    if req == "test":
        return "test"
    if req in ("real", "universe"):
        if srv in ("real", "universe") and req != srv:
            return srv
        return req
    return srv


def realm_links(mode: str) -> dict[str, object]:
    """The other realm's map, and this realm's hub, for the mode badge.

    Test mode gets nothing: it is a simulation of the whole ecosystem rather than one of
    the two realms, so "the other realm" has no meaning there and a link would invent one.
    """
    mode = (mode or "").strip().lower()
    if mode == "universe":
        other = {"realm": "live", "map_url": live_map_url()}
        hub = uni_hub_url()
        return {"realm": "uni", "hub_url": hub, "other": other} if hub else {
            "realm": "uni", "other": other
        }
    if mode == "real":
        return {"realm": "live", "other": {"realm": "uni", "map_url": universe_map_url()}}
    return {}
