"""Multi-instance ARGUS roster for Alien Monitor.

The graph ball keeps the product name ``ARGUS-3`` (counts live in metrics, not the label).
Click opens a searchable,
sortable, cursor-paginated list of connected agents — Factory Products pattern,
not thousands of 3D nodes.

Instances arrive via:
  - ``POST /api/argus/heartbeat`` (lightweight presence)
  - ``POST /api/argus/run`` (verifiable run + upsert)

In-memory, process-local (same durability class as ``argus_feed`` / lottery).
Hard caps + TTL keep the map honest at fleet scale.
"""

from __future__ import annotations

import base64
import hashlib
import math
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

# Presence window for "active" count on the ball.
ACTIVE_TTL_S = 300.0
# Soft offline then hard-evict.
STALE_TTL_S = 7 * 24 * 3600.0
MAX_INSTANCES = 5000
DEFAULT_PAGE = 40
MAX_PAGE = 100

_SORTS = frozenset({"last_seen", "name", "version", "spend", "economy"})
_ID_RE = re.compile(r"^[a-zA-Z0-9_.:-]{4,128}$")

_LOCK = threading.RLock()
# instance_id -> record
_REG: dict[str, dict[str, Any]] = {}


def _now() -> float:
    return time.time()


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


def _clean_id(raw: Any) -> str | None:
    s = str(raw or "").strip()
    if not s or not _ID_RE.match(s):
        return None
    return s


def _short_wallet(addr: str) -> str:
    a = addr.strip()
    if a.startswith("0x") and len(a) >= 12:
        return f"{a[:6]}…{a[-4:]}"
    return a[:20] if a else ""


def _derive_id_from_wallet(wallet: str) -> str:
    h = hashlib.sha256(wallet.lower().encode()).hexdigest()[:16]
    return f"argus-{h}"


def _normalize_wallet(raw: str) -> str:
    w = (raw or "").strip()
    if w.startswith("0x") and len(w) >= 12:
        return w
    return w[:80]


def _canonical_name(name: str, mode: str) -> str:
    """Strip mode suffixes so live+uni heartbeats share one fleet row."""
    n = (name or "").strip()
    for suf in ("-UNI", " · UNI", " UNI", "-uni", " (uni)", " (UNI)"):
        if n.endswith(suf):
            n = n[: -len(suf)].rstrip(" ·-")
    if mode == "uni" and n.lower().endswith("uni"):
        n = n[: -3].rstrip(" ·-")
    return n[:64] or "ARGUS"


def _mode_label(mode: str) -> str:
    m = (mode or "").strip().lower()
    if m in ("live", "real"):
        return "live"
    if m == "uni":
        return "uni"
    if m == "test":
        return "test"
    return m[:16] if m else ""


def normalize_instance_payload(body: dict[str, Any] | None) -> dict[str, Any]:
    """Extract identity fields from heartbeat / run bodies.

    One wallet ⇒ one fleet agent. Live + UNI containers that share a wallet
    coalesce into a single row (modes/wallets listed on the card).
    """
    b = body if isinstance(body, dict) else {}
    inst = b.get("instance") if isinstance(b.get("instance"), dict) else {}
    wallet = _normalize_wallet(
        str(b.get("wallet") or inst.get("wallet") or b.get("signer") or "")
    )
    mode = _mode_label(str(b.get("mode") or inst.get("mode") or ""))
    # Prefer wallet-derived id so live/uni/state-dir splits don't fork the roster.
    instance_id = None
    if wallet.startswith("0x") and len(wallet) >= 12:
        instance_id = _derive_id_from_wallet(wallet)
    if not instance_id:
        instance_id = _clean_id(b.get("instance_id") or inst.get("id") or b.get("agent_id"))
    if not instance_id:
        rid = _clean_id(b.get("id"))
        if rid:
            instance_id = f"run-{rid}"
    name = _canonical_name(
        str(b.get("display_name") or inst.get("name") or b.get("name") or ""),
        mode,
    )
    if name == "ARGUS" and wallet:
        name = _short_wallet(wallet) or "ARGUS"
    if name == "ARGUS" and instance_id:
        name = instance_id[:24]
    version = str(b.get("version") or inst.get("version") or "").strip()[:32]
    economy_raw = b.get("economy") if "economy" in b else inst.get("economy")
    if isinstance(economy_raw, bool):
        economy = "on" if economy_raw else "off"
    else:
        economy = str(economy_raw or "off").strip().lower()[:8]
        if economy not in ("on", "off"):
            economy = "off"
    host = str(b.get("host") or inst.get("host") or "").strip()[:80]
    return {
        "instance_id": instance_id,
        "display_name": name or "ARGUS",
        "wallet": wallet,
        "version": version,
        "mode": mode,
        "economy": economy,
        "host": host,
    }


def upsert_instance(
    body: dict[str, Any] | None,
    *,
    run: dict[str, Any] | None = None,
    source: str = "heartbeat",
) -> dict[str, Any] | None:
    """Register or refresh an agent. Same wallet → one row (live+uni coalesce)."""
    meta = normalize_instance_payload(body)
    iid = meta["instance_id"]
    if not iid:
        return None
    now = _now()
    with _LOCK:
        # Migrate legacy split ids (Factory vs Factory-UNI) onto wallet key.
        if meta["wallet"]:
            canon = _derive_id_from_wallet(meta["wallet"])
            for old_k, old_v in list(_REG.items()):
                if old_k == canon:
                    continue
                if _normalize_wallet(str(old_v.get("wallet") or "")) == meta["wallet"]:
                    prev_legacy = _REG.pop(old_k)
                    if canon not in _REG:
                        prev_legacy["instance_id"] = canon
                        _REG[canon] = prev_legacy
                    else:
                        modes = set(_REG[canon].get("modes") or [])
                        modes.update(prev_legacy.get("modes") or [])
                        if prev_legacy.get("mode"):
                            modes.add(_mode_label(str(prev_legacy.get("mode"))))
                        _REG[canon]["modes"] = sorted(m for m in modes if m)
            iid = canon
            meta["instance_id"] = canon

        prev = _REG.get(iid) or {}
        spend = _finite((run or {}).get("spendUsd"), prev.get("spend_usd") or 0.0)
        if run is not None:
            spend = max(spend, _finite(run.get("spendUsd")))

        modes = set(prev.get("modes") or [])
        if prev.get("mode"):
            modes.add(_mode_label(str(prev.get("mode"))))
        if meta["mode"]:
            modes.add(meta["mode"])

        # Per-mode wallet marks (same address OK — live Base vs UNI Anvil).
        wallets: list[dict[str, str]] = []
        seen_w: set[tuple[str, str]] = set()
        for wrec in list(prev.get("wallets") or []):
            if not isinstance(wrec, dict):
                continue
            addr = _normalize_wallet(str(wrec.get("address") or ""))
            chain = str(wrec.get("chain") or wrec.get("mode") or "")[:16]
            key = (addr.lower(), chain)
            if addr and key not in seen_w:
                seen_w.add(key)
                wallets.append({"address": addr, "chain": chain, "short": _short_wallet(addr)})
        if meta["wallet"]:
            chain = meta["mode"] or "live"
            key = (meta["wallet"].lower(), chain)
            if key not in seen_w:
                seen_w.add(key)
                wallets.append(
                    {
                        "address": meta["wallet"],
                        "chain": chain,
                        "short": _short_wallet(meta["wallet"]),
                    }
                )

        # Prefer human live name over "Factory-UNI".
        name = meta["display_name"]
        if meta["mode"] == "uni" and prev.get("display_name"):
            name = _canonical_name(str(prev.get("display_name")), "uni")
        elif not name:
            name = prev.get("display_name") or "ARGUS"

        rec = {
            "instance_id": iid,
            "display_name": name or "ARGUS",
            "wallet": meta["wallet"] or prev.get("wallet") or "",
            "wallets": wallets,
            "version": meta["version"] or prev.get("version") or "",
            "mode": meta["mode"] or prev.get("mode") or "",
            "modes": sorted(modes),
            "economy": meta["economy"] if meta["economy"] else prev.get("economy") or "off",
            "host": meta["host"] or prev.get("host") or "",
            "last_seen": now,
            "first_seen": float(prev.get("first_seen") or now),
            "source": source,
            "spend_usd": spend,
            "runs": int(prev.get("runs") or 0) + (1 if run is not None else 0),
            "last_run": run if run is not None else prev.get("last_run"),
            "last_run_id": (run or {}).get("id") if run else prev.get("last_run_id"),
        }
        _REG[iid] = rec
        _evict_locked(now)
        return public_record(rec, now=now)


def heartbeat(body: dict[str, Any] | None) -> dict[str, Any] | None:
    return upsert_instance(body, run=None, source="heartbeat")


def note_run(body: dict[str, Any] | None, cleaned_run: dict[str, Any]) -> dict[str, Any] | None:
    """Upsert from a verifiable run push (identity optional — derived if missing)."""
    return upsert_instance(body, run=cleaned_run, source="run")


def _evict_locked(now: float) -> None:
    """Drop ancient records; if over cap, drop oldest last_seen first."""
    stale = [k for k, v in _REG.items() if now - float(v.get("last_seen") or 0) > STALE_TTL_S]
    for k in stale:
        _REG.pop(k, None)
    if len(_REG) <= MAX_INSTANCES:
        return
    ordered = sorted(_REG.items(), key=lambda kv: float(kv[1].get("last_seen") or 0))
    overflow = len(_REG) - MAX_INSTANCES
    for k, _ in ordered[:overflow]:
        _REG.pop(k, None)


def public_record(rec: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
    ts = now if now is not None else _now()
    last = float(rec.get("last_seen") or 0)
    age = ts - last
    if age <= ACTIVE_TTL_S:
        status = "active"
    elif age <= 3600:
        status = "idle"
    else:
        status = "offline"
    modes = list(rec.get("modes") or [])
    if not modes and rec.get("mode"):
        modes = [_mode_label(str(rec.get("mode")))]
    wallets = rec.get("wallets") if isinstance(rec.get("wallets"), list) else []
    if not wallets and rec.get("wallet"):
        wallets = [
            {
                "address": rec.get("wallet"),
                "chain": modes[0] if modes else (rec.get("mode") or "live"),
                "short": _short_wallet(str(rec.get("wallet") or "")),
            }
        ]
    out = {
        "instance_id": rec["instance_id"],
        "display_name": rec.get("display_name") or "ARGUS",
        "wallet": rec.get("wallet") or "",
        "wallet_short": _short_wallet(str(rec.get("wallet") or "")),
        "wallets": wallets,
        "version": rec.get("version") or "",
        "mode": rec.get("mode") or (modes[0] if modes else ""),
        "modes": modes,
        "economy": rec.get("economy") or "off",
        "host": rec.get("host") or "",
        "status": status,
        "last_seen": datetime.fromtimestamp(last, timezone.utc).isoformat().replace("+00:00", "Z"),
        "last_seen_age_s": int(max(0, age)),
        "first_seen": datetime.fromtimestamp(float(rec.get("first_seen") or last), timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "spend_usd": round(_finite(rec.get("spend_usd")), 6),
        "runs": int(rec.get("runs") or 0),
        "last_run_id": rec.get("last_run_id") or "",
        "has_run": bool(rec.get("last_run")),
    }
    return out


def counts(*, now: float | None = None) -> dict[str, int]:
    ts = now if now is not None else _now()
    with _LOCK:
        total = len(_REG)
        active = sum(
            1 for v in _REG.values() if ts - float(v.get("last_seen") or 0) <= ACTIVE_TTL_S
        )
        economy_on = sum(
            1
            for v in _REG.values()
            if (v.get("economy") == "on") and ts - float(v.get("last_seen") or 0) <= ACTIVE_TTL_S
        )
    return {"total": total, "active": active, "economy_on": economy_on}


def get_instance(instance_id: str) -> dict[str, Any] | None:
    iid = _clean_id(instance_id)
    if not iid:
        return None
    with _LOCK:
        rec = _REG.get(iid)
        if not rec:
            return None
        pub = public_record(rec)
        run = rec.get("last_run")
        if isinstance(run, dict):
            pub["last_run"] = dict(run)
        return pub


def _sort_key(rec: dict[str, Any], sort: str) -> tuple:
    if sort == "name":
        return (str(rec.get("display_name") or "").lower(), rec["instance_id"])
    if sort == "version":
        return (str(rec.get("version") or ""), rec["instance_id"])
    if sort == "spend":
        return (-_finite(rec.get("spend_usd")), rec["instance_id"])
    if sort == "economy":
        return (0 if rec.get("economy") == "on" else 1, -float(rec.get("last_seen") or 0), rec["instance_id"])
    # last_seen default — newest first
    return (-float(rec.get("last_seen") or 0), rec["instance_id"])


def _encode_cursor(sort: str, rec: dict[str, Any]) -> str:
    raw = f"{sort}|{rec['instance_id']}|{rec.get('last_seen')}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> str | None:
    """Return instance_id after which to continue, or None."""
    if not cursor:
        return None
    pad = "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode(cursor + pad).decode()
        parts = raw.split("|")
        if len(parts) >= 2:
            return parts[1]
    except Exception:
        return None
    return None


def list_instances(
    *,
    q: str = "",
    sort: str = "last_seen",
    cursor: str = "",
    limit: int = DEFAULT_PAGE,
    status: str = "",
) -> dict[str, Any]:
    """Searchable, sortable, cursor-paginated roster."""
    sort = sort if sort in _SORTS else "last_seen"
    limit = max(1, min(int(limit or DEFAULT_PAGE), MAX_PAGE))
    needle = (q or "").strip().lower()
    status_f = (status or "").strip().lower()
    now = _now()

    with _LOCK:
        rows = [public_record(r, now=now) for r in _REG.values()]
        # Keep registry refs for sort keys that need raw last_seen/spend.
        reg_snap = {k: dict(v) for k, v in _REG.items()}

    if needle:
        rows = [
            r
            for r in rows
            if needle in r["instance_id"].lower()
            or needle in str(r.get("display_name") or "").lower()
            or needle in str(r.get("wallet") or "").lower()
            or needle in str(r.get("host") or "").lower()
            or needle in str(r.get("version") or "").lower()
        ]
    if status_f in ("active", "idle", "offline"):
        rows = [r for r in rows if r.get("status") == status_f]

    rows.sort(key=lambda r: _sort_key(reg_snap.get(r["instance_id"]) or r, sort))

    start = 0
    after = _decode_cursor(cursor)
    if after:
        for i, r in enumerate(rows):
            if r["instance_id"] == after:
                start = i + 1
                break

    page = rows[start : start + limit]
    next_cursor = ""
    if start + limit < len(rows) and page:
        next_cursor = _encode_cursor(sort, page[-1])

    c = counts(now=now)
    return {
        "instances": page,
        "count": len(page),
        "total": c["total"],
        "active": c["active"],
        "economy_on": c["economy_on"],
        "next_cursor": next_cursor,
        "sort": sort,
        "q": q,
        "status": status_f,
        "limit": limit,
        "has_more": bool(next_cursor),
    }


def apply_roster_to_node(node: dict[str, Any], *, promote_status: bool = True) -> None:
    """Update ARGUS ball metrics from roster counts (label stays the product name)."""
    c = counts()
    active = c["active"]
    total = c["total"]
    # Never embed fleet size in the map label — it reads like the product name
    # (ARGUS-3 vs "ARGUS · 3") and flickers when the roster poll returns.
    node["label"] = "ARGUS-3"
    metrics = dict(node.get("metrics") or {})
    metrics["instances_active"] = active
    metrics["instances_total"] = total
    metrics["instances_economy_on"] = c["economy_on"]
    node["metrics"] = metrics
    node["argus_roster"] = {
        "active": active,
        "total": total,
        "economy_on": c["economy_on"],
    }
    if (
        promote_status
        and active > 0
        and node.get("status") in ("offline", "unknown", None, "")
    ):
        node["status"] = "active"


def clear_roster() -> None:
    """Test helper."""
    with _LOCK:
        _REG.clear()


def seed_demo_instances(n: int = 3) -> None:
    """TEST-mode sample roster so the panel is never empty in demos."""
    now = _now()
    demos = [
        {
            "instance_id": "argus-demo-alpha",
            "display_name": "Alpha (demo)",
            "wallet": "0x1111111111111111111111111111111111111111",
            "version": "0.2.4",
            "mode": "test",
            "economy": "off",
            "host": "demo-local",
            "last_seen": now,
            "first_seen": now - 3600,
            "source": "seed",
            "spend_usd": 0.016,
            "runs": 4,
            "last_run": None,
            "last_run_id": "run_demo_7f3a",
        },
        {
            "instance_id": "argus-demo-beta",
            "display_name": "Beta · economy",
            "wallet": "0x2222222222222222222222222222222222222222",
            "version": "0.2.4",
            "mode": "real",
            "economy": "on",
            "host": "operator-laptop",
            "last_seen": now - 30,
            "first_seen": now - 86400,
            "source": "seed",
            "spend_usd": 1.25,
            "runs": 42,
            "last_run": None,
            "last_run_id": "",
        },
        {
            "instance_id": "argus-demo-gamma",
            "display_name": "Gamma (idle)",
            "wallet": "0x3333333333333333333333333333333333333333",
            "version": "0.2.3",
            "mode": "universe",
            "economy": "off",
            "host": "",
            "last_seen": now - 600,
            "first_seen": now - 7200,
            "source": "seed",
            "spend_usd": 0.0,
            "runs": 1,
            "last_run": None,
            "last_run_id": "",
        },
    ]
    with _LOCK:
        for rec in demos[:n]:
            _REG[rec["instance_id"]] = rec
