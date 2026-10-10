"""Which ecosystem this deployment is allowed to draw as its own.

`build_topology()` used to be a literal list of the AICOM shelf — METIS, MOMUS, ATLAS,
GAIA, the eighteen-oracle ring, the factory — with no relation to `HUB_URL`. Anyone who
deployed the Monitor got that shelf as their local ecosystem, and fifteen `apply_*_graph`
pollers went out over the internet to fetch its status from `*.modelmarket.dev`. On
independentai.network the effect was exact and backwards: forty-five of somebody else's
nodes drawn as local, and the three the hub actually owns (KOVA, AEGIS, the echo provider)
drawn as small planets in orbit.

So the shelf is a PROFILE, not a constant:

  aicom    the Monitor is pointed at the AICOM hub — draw the built-in shelf and poll it
  generic  it is pointed at somebody else's hub — the map is whatever that hub declares,
           plus whatever its operator declares locally, and nothing is polled off-host

Detection is deliberately offline and deliberately conservative. A deployment that has told
the world who it is (`ALIEN_PUBLIC_HUB_URL` and friends) and is not us gets `generic`; one
that has said nothing keeps `aicom`, so local dev and the test suite are unchanged.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

AICOM = "aicom"
GENERIC = "generic"

#: Hosts the built-in shelf actually describes. Suffix match, so `uni.modelmarket.dev`
#: and `hunt.modelmarket.dev` are covered without listing every subdomain.
_AICOM_SUFFIXES: tuple[str, ...] = ("modelmarket.dev", "magic-ai-factory.com")

#: A deployment that has not published an address is somebody running the monorepo — the
#: shelf is theirs. Only a *declared, foreign* identity switches the profile.
_LOCAL_HOSTS: frozenset[str] = frozenset({"", "localhost", "127.0.0.1", "0.0.0.0", "::1"})

_PUBLIC_URL_ENVS = (
    "ALIEN_PUBLIC_HUB_URL",
    "HUB_PUBLIC_URL",
    "AIMARKET_PUBLIC_HUB_URL",
)


def _host_of(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw if "://" in raw else f"http://{raw}")
        return (parsed.hostname or "").lower()
    except Exception:
        return ""


def _declared_public_host() -> str:
    for name in _PUBLIC_URL_ENVS:
        host = _host_of(os.environ.get(name, ""))
        if host:
            return host
    return ""


def profile_name() -> str:
    """`aicom` or `generic`. Read from the environment on every call — the test suite
    and the universe/live split both flip these without reimporting the module."""
    override = (os.environ.get("ALIEN_ECOSYSTEM_PROFILE") or "").strip().lower()
    if override in (AICOM, GENERIC):
        return override
    host = _declared_public_host()
    if host in _LOCAL_HOSTS:
        return AICOM
    if any(host == suffix or host.endswith(f".{suffix}") for suffix in _AICOM_SUFFIXES):
        return AICOM
    return GENERIC


def owns_builtin_shelf() -> bool:
    """May this deployment draw — and poll — the built-in AICOM satellites?

    Everything gated on this is a claim about somebody else's infrastructure: the node,
    its status poller, the URL-to-canonical-id folding, and the seeded hub suns.
    """
    return profile_name() == AICOM


# ── Operator-declared components ─────────────────────────────────────────────
# A hub's signed `ecosystem.nodes` covers what it sells. It does not cover the forty
# containers an operator runs beside it that never entered the federation, and those are
# exactly what an operator wants to see on their own map. So there is a file.

_ALLOWED_KEYS = frozenset(
    {"id", "label", "group", "icon", "description", "url", "categories"}
)
_MAX_COMPONENTS = 64


def _profile_paths() -> list[Path]:
    explicit = (os.environ.get("ALIEN_ECOSYSTEM_FILE") or "").strip()
    monitor_root = Path(__file__).resolve().parent.parent
    paths = [Path(explicit)] if explicit else []
    paths.append(monitor_root / "config" / "own-ecosystem.yaml")
    return paths


@lru_cache(maxsize=8)
def _load_components(cache_key: str) -> tuple[dict[str, Any], ...]:
    del cache_key  # only there to key the cache on the resolved path
    for path in _profile_paths():
        if not path.is_file():
            continue
        try:
            import yaml

            with open(path, encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
        except Exception:
            return ()
        raw = data.get("ecosystem")
        if not isinstance(raw, list):
            return ()
        out: list[dict[str, Any]] = []
        for entry in raw[:_MAX_COMPONENTS]:
            if not isinstance(entry, dict) or not entry.get("id"):
                continue
            node = {k: v for k, v in entry.items() if k in _ALLOWED_KEYS}
            node.setdefault("label", str(node["id"]))
            node.setdefault("group", "core")
            node.setdefault("icon", "service")
            node.setdefault("description", "Declared by the operator of this deployment.")
            out.append(node)
        return tuple(out)
    return ()


def own_components() -> list[dict[str, Any]]:
    """Components this operator declared for their own map, in file order.

    Never a source of trust: these are drawn and, if they carry a URL, linked. They are
    not capabilities, they do not federate, and nothing here is polled cross-host.
    """
    key = "|".join(str(p) for p in _profile_paths())
    return [dict(node) for node in _load_components(key)]


def reset_cache() -> None:
    """Tests change the environment between cases; the file cache must follow."""
    _load_components.cache_clear()
