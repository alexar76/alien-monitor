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
