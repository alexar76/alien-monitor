"""A short TTL in front of the satellite pollers.

The state tick is 1.5 s (ALIEN_STATE_TICK_SEC) and every rebuild calls every
satellite's `fetch_*_sync`, none of which cached. So each satellite was being asked
roughly 40 times a minute, for numbers that change on its own poll cycle — often
every 5 minutes. It was pure waste until it was not: LOGOS publishes a rate limit
of 30 requests a minute per client, so the monitor exhausted it and every card fed
by that service went blank. The dashboard broke itself by asking too eagerly.

Three rules make this honest rather than just cheap:

  * **A failed read does not immediately evict a good answer.** One timeout or one
    429 should not blank a card that was correct a second ago, so the last good
    value is served for a bounded grace window.
  * **A real outage still surfaces.** Past that window the failure is returned as
    it is. A cache that hides a dead satellite forever would make the monitor lie,
    which is worse than a blank card.
  * **A known failure is cached too.** A satellite that is already down does not
    become more down by being asked 40 times a minute, and the card reads the same
    either way — so failures get the same TTL, and recovery is still noticed on the
    next expiry.

`treasury_status.py` already did this for its chain reads (ALIEN_TREASURY_CHAIN_TTL);
this is the same idea for the HTTP pollers, in one place instead of eleven.
"""

from __future__ import annotations

import functools
import os
import threading
import time
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

DEFAULT_TTL_S = 30.0
#: How long a stale-but-good value may cover for a failing read, as a multiple of
#: the TTL. Two cycles: long enough to ride out a blip, short enough that a
#: satellite which is genuinely down is reported as down.
GRACE_MULTIPLE = 2.0


def _ttl(env_var: str | None, default: float) -> float:
    """TTL from env when the operator set one, else the default."""
    raw = os.environ.get(env_var or "", "").strip()
    if not raw:
        raw = os.environ.get("ALIEN_POLL_CACHE_TTL", "").strip()
    if raw:
        try:
            value = float(raw)
            if value >= 0:
                return value
        except ValueError:
            pass
    return default


def ttl_cached(
    *,
    ttl_s: float = DEFAULT_TTL_S,
    env_var: str | None = None,
    grace_multiple: float = GRACE_MULTIPLE,
) -> Callable[[F], F]:
    """Memoise a poller's result for `ttl_s`, keyed on its arguments.

    A falsy result (None, {}, []) counts as a failed read: the previous good value
    is returned while it is inside the grace window, and after that the failure is
    passed through unchanged.
    """

    def decorate(fn: F) -> F:
        lock = threading.Lock()
        # key → (stored_at, value, is_good)
        store: dict[Any, tuple[float, Any, bool]] = {}

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            force = bool(kwargs.pop("force_refresh", False))
            key = (args, tuple(sorted(kwargs.items())))
            ttl = _ttl(env_var, ttl_s)
            now = time.monotonic()

            if not force and ttl > 0:
                with lock:
                    entry = store.get(key)
                if entry is not None:
                    stored_at, value, good = entry
                    if now - stored_at < ttl:
                        # A cached failure is served too. HELIOS being down does not
                        # become truer by asking 40 times a minute, and the card says
                        # "down" either way — so a satellite that is already known to
                        # be unreachable gets the same breathing room as a healthy
                        # one. It is still retried every TTL, so recovery is noticed.
                        return value

            result = fn(*args, **kwargs)

            with lock:
                entry = store.get(key)
                if result:
                    store[key] = (now, result, True)
                    return result
                # Failed read: cover for it only briefly, and only with a value
                # that was actually good.
                if entry is not None and entry[2] and now - entry[0] < ttl * grace_multiple:
                    return entry[1]
                store[key] = (now, result, False)
                return result

        wrapper.cache_clear = lambda: store.clear()  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorate


def clear_all() -> None:
    """Tests only — there is no global registry, so this is a documented no-op
    kept so callers do not invent one."""
    return None
