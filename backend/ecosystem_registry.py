"""Load alexar76 satellite catalog from scripts/satellite-map.yaml for AI prompts."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_BACKEND_ROOT = Path(__file__).resolve().parent
_MONITOR_ROOT = _BACKEND_ROOT.parent


def _aicom_root() -> Path:
    for key in ("AICOM_ROOT", "AICOM_MONOREPO_ROOT"):
        raw = os.environ.get(key, "").strip()
        if raw:
            return Path(raw)
    return _MONITOR_ROOT.parent


def _map_paths() -> list[Path]:
    root = _aicom_root()
    return [
        root / "scripts" / "satellite-map.yaml",
        _MONITOR_ROOT / "scripts" / "satellite-map.yaml",
        _BACKEND_ROOT / "data" / "satellite-map.yaml",
    ]


@lru_cache(maxsize=1)
def load_satellites() -> list[dict[str, Any]]:
    for path in _map_paths():
        if not path.is_file():
            continue
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        sats = data.get("satellites")
        if isinstance(sats, list):
            return [s for s in sats if isinstance(s, dict) and s.get("id")]
    return []


def build_ecosystem_registry_context(*, max_items: int = 250) -> str:
    # New satellites are appended at the end of satellite-map.yaml, which is exactly
    # where a 48-item cap bit: the registry is the assistant's answer to "does this
    # component exist", and a truncated answer there reads as "no". 250 is far above
    # the current 36 and costs ~230 characters per satellite.
    """Compact satellite list for LLM system prompts."""
    org = "alexar76"
    lines: list[str] = [
        f"GitHub org **{org}** — loosely-coupled AIMarket / AICOM satellites (monorepo source of truth: aicom):",
        "",
    ]
    count = 0
    for sat in load_satellites():
        if count >= max_items:
            lines.append(f"… and {len(load_satellites()) - max_items} more satellites in satellite-map.yaml.")
            break
        sid = str(sat.get("id", ""))
        repo = str(sat.get("repo") or sid)
        desc = str(sat.get("description") or "").strip()
        home = str(sat.get("homepage") or "").strip()
        optional = sat.get("optional") is True
        tag = " (profile README)" if optional else ""
        line = f"- **{sid}** → github.com/{org}/{repo}{tag}: {desc}"
        if home:
            line += f" · {home}"
        lines.append(line)
        count += 1
    if count == 0:
        return ""
    lines.append("")
    lines.append(
        "When users ask about a satellite by name, explain its role and point to its homepage/repo. "
        "On the 3D map, core runtime peers appear as glowing nodes (hub, factory, mesh, argus, "
        "dioscuri, helios, metis, skopos, gaia, oracles, …)."
    )
    return "\n".join(lines)


# ── the central knowledge base ───────────────────────────────────────────────
# docs/ecosystem/knowledge-base.md is the ecosystem's one written source of truth,
# and the assistant did not read it. Its knowledge came from a 13 KB prose block
# hand-maintained inside main.py, which named every satellite except the newest —
# so the assistant told a user that LOGOS "does not exist in the ecosystem" while
# the KB described it, with its live URL, three sections down. Anything documented
# centrally is now known centrally: adding a component to the KB is enough.

_KB_RELATIVE = ("docs", "ecosystem", "knowledge-base.md")


def _kb_paths() -> list[Path]:
    root = _aicom_root()
    return [
        root.joinpath(*_KB_RELATIVE),
        _MONITOR_ROOT.joinpath(*_KB_RELATIVE),
        _BACKEND_ROOT / "data" / "knowledge-base.md",
    ]


@lru_cache(maxsize=1)
def load_knowledge_base(*, max_chars: int = 26000) -> str:
    """The central KB, trimmed to a prompt budget.

    Truncation is stated in the text rather than hidden: a silently cut knowledge
    base is how "I cannot see it" becomes "it does not exist".
    """
    for path in _kb_paths():
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not text:
            continue
        if len(text) <= max_chars:
            return text
        return (
            text[:max_chars].rstrip()
            + f"\n\n… knowledge base truncated at {max_chars} of {len(text)} characters. "
              "Components may be documented in the part not shown — never conclude from this "
              "that something does not exist."
        )
    return ""


# ---------------------------------------------------------------------------
# Live federation — what is actually reachable, as opposed to what is documented
# ---------------------------------------------------------------------------
#
# The two sources answer different questions and neither replaces the other:
#
#   satellite-map.yaml / knowledge-base.md   what a component IS, why it exists, how it fits.
#                                            Curated, durable, and always slightly behind.
#   the hub's own manifest                   what is running and callable RIGHT NOW.
#                                            Never behind, and explains nothing.
#
# Static-only has already failed twice in this file's history: the assistant denied LOGOS
# existed, and then denied CHARON existed — both times because a hand-maintained list had not
# caught up with a deployment. Live-only would be worse: a list of capability ids tells a reader
# nothing about what any of them are for. So: both, labelled, with the live block explicitly
# marked as the one that settles "does this exist right now".

_LIVE_TTL_S = 60
_live_cache: dict[str, Any] = {"at": 0.0, "text": ""}


def _hub_base() -> str:
    return (os.environ.get("ALIEN_LOCAL_HUB_URL")
            or os.environ.get("ALIEN_PUBLIC_HUB_URL")
            or "https://independentai.network/hub").rstrip("/")


def build_live_federation_context(*, timeout_s: float = 4.0) -> str:
    """A compact, current picture of the federation, or an explicit admission of silence.

    Never invents. If the hub does not answer, the block says so — an assistant that quietly
    falls back to the static list would confidently describe a node that has been down for a
    week, which is the failure this whole layer exists to prevent.
    """
    import json as _json
    import time as _time
    import urllib.request as _url

    now = _time.time()
    if _live_cache["text"] and now - float(_live_cache["at"]) < _LIVE_TTL_S:
        return str(_live_cache["text"])

    base = _hub_base()
    lines: list[str] = []
    try:
        with _url.urlopen(base + "/.well-known/ai-market.json", timeout=timeout_s) as r:
            wk = _json.loads(r.read().decode("utf-8", "replace"))
        with _url.urlopen(base + "/ai-market/v2/manifest", timeout=timeout_s) as r:
            mf = _json.loads(r.read().decode("utf-8", "replace"))
    except Exception as exc:
        text = ("The hub at %s did not answer (%s). This block is normally the authority on "
                "what exists right now; treat the static registry above as possibly stale and "
                "say so if asked." % (base, str(exc)[:120]))
        _live_cache.update({"at": now, "text": text})
        return text

    tools = mf.get("tools") if isinstance(mf.get("tools"), list) else []
    local_products: dict[str, int] = {}
    by_peer: dict[str, int] = {}
    for t in tools:
        if not isinstance(t, dict):
            continue
        src = str(t.get("source_hub") or "local")
        if src == "local":
            pid = str(t.get("product_id") or "?")
            local_products[pid] = local_products.get(pid, 0) + 1
        else:
            by_peer[src] = by_peer.get(src, 0) + 1

    lines.append("Read live from %s just now. This is what is reachable; the registry above "
                 "explains what the pieces are." % base)
    lines.append("")
    lines.append("Hub: %s — %s local capabilities, %s federated, %s peers."
                 % (wk.get("name") or "hub", wk.get("capabilities_count"),
                    wk.get("federated_capabilities_count"), len(wk.get("peers") or [])))
    if local_products:
        lines.append("")
        lines.append("Products served BY THIS NODE (its own services, not federated):")
        for pid, n in sorted(local_products.items()):
            lines.append("- %s (%d capabilit%s)" % (pid, n, "y" if n == 1 else "ies"))
    peers = wk.get("peers") or []
    if peers:
        lines.append("")
        lines.append("Peer hubs currently indexed:")
        for p in peers:
            if not isinstance(p, dict):
                continue
            url = str(p.get("url") or "")
            lines.append("- %s — %s (%s capabilities indexed here)"
                         % (str(p.get("name") or url)[:80], url, by_peer.get(url, 0)))

    text = "\n".join(lines)
    _live_cache.update({"at": now, "text": text})
    return text


def live_component_answer(question: str) -> str:
    """Answer about any component the federation currently carries, without a code edit.

    `_fallback_answer` is a chain of hand-written `if "<name>" in q` branches, so a component
    is answerable only if somebody added a branch for it. That is why the assistant denied
    LOGOS, and then denied CHARON: both existed, both were callable, and neither had a branch.
    This looks the question up against what the hub says is live, so the list maintains itself.

    Returns "" when nothing matches — the caller keeps its own wording for "I don't know".
    """
    q = (question or "").lower()
    if len(q) < 3:
        return ""
    ctx = build_live_federation_context()
    if not ctx or "did not answer" in ctx:
        return ""

    hits: list[str] = []
    for line in ctx.split("\n"):
        line = line.strip()
        if not line.startswith("- "):
            continue
        body = line[2:].strip()
        # The name is whatever precedes the first separator: "NAME — tagline" for peers,
        # "product-id (N capabilities)" for local products.
        name = body.split(" — ")[0].split(" (")[0].strip()
        if not name or len(name) < 3:
            continue
        token = name.lower()
        short = token.split(".")[0].split("-")[0]
        if token in q or (len(short) >= 4 and short in q):
            hits.append(body)
    if not hits:
        return ""
    head = ("Reading the hub right now: " if len(hits) == 1
            else "Reading the hub right now, %d live entries match: " % len(hits))
    return head + "; ".join(hits[:4]) + "."
