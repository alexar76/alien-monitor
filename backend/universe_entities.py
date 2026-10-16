"""What the universe and its mixins share: the entity type, contract paths in the monorepo, the
Anvil deployer key, peer URL normalisation and the Foundry temp sweep.
"""

from __future__ import annotations

import contextlib
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# Anvil account #0 — standard Foundry dev key (local universe only).
# Foundry/Anvil default mnemonic, account 0 (64-byte hex).
ANVIL_DEPLOYER_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


_MONITOR_ROOT = Path(__file__).resolve().parent.parent


def resolve_aicom_root() -> Path:
    """Monorepo root (dev) or /app (Docker image with bundled contracts)."""
    for key in ("AICOM_ROOT", "AICOM_MONOREPO_ROOT"):
        raw = os.environ.get(key, "").strip()
        if raw:
            return Path(raw)
    bundled = _MONITOR_ROOT / "contracts" / "evm"
    if bundled.is_dir():
        return _MONITOR_ROOT
    parent = _MONITOR_ROOT.parent
    if (parent / "contracts" / "evm").is_dir():
        return parent
    return parent


def resolve_evm_contracts_dir() -> Path:
    override = os.environ.get("AICOM_CONTRACTS_EVM_DIR", "").strip()
    if override:
        return Path(override)
    return resolve_aicom_root() / "contracts" / "evm"


def resolve_lottery_contracts_dir() -> Path | None:
    """Foundry project for AIAgentLottery (monorepo lottery/contracts)."""
    root = resolve_aicom_root()
    for candidate in (
        root / "lottery" / "contracts",
        _MONITOR_ROOT.parent / "lottery" / "contracts",
    ):
        if (candidate / "foundry.toml").is_file():
            return candidate
    return None


def resolve_acex_evm_dir() -> Path | None:
    """Foundry project for ACEX CapShare stack (acex/contracts/evm)."""
    root = resolve_aicom_root()
    for candidate in (
        root / "acex" / "contracts" / "evm",
        _MONITOR_ROOT / "acex" / "contracts" / "evm",
    ):
        if (candidate / "foundry.toml").is_file():
            return candidate
    return None


def resolve_solana_contracts_dir() -> Path | None:
    root = resolve_aicom_root()
    for candidate in (
        root / "contracts" / "solana",
        _MONITOR_ROOT.parent / "contracts" / "solana",
    ):
        if (candidate / "Anchor.toml").is_file():
            return candidate
    return None


_MAX_PRODUCT_ENTITIES = max(50, int(os.environ.get("ALIEN_MAX_PRODUCT_ENTITIES", "400")))


def _norm_peer_url(url: str) -> str:
    """One spelling for one address, so "does the map already draw this" has an answer.

    Scheme and a trailing slash are noise: a node configured as `https://atlas.example` and a
    peer advertising `http://atlas.example/` are the same planet, and treating them as two is
    the whole bug this normalisation exists to prevent.
    """
    text = str(url or "").strip().rstrip("/").lower()
    for prefix in ("https://", "http://"):
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


class EcosystemEntity:
    """A component node in the UNI ecosystem graph."""

    def __init__(
        self,
        eid: str,
        name: str,
        etype: str,
        group: str = "product",
        *,
        description: str = "",
        icon: str = "planet",
    ):
        self.id = eid
        self.name = name
        self.type = etype
        self.group = group
        self.description = description or f"{name} — AIMarket ecosystem component"
        self.icon = icon
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.position = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.metrics: dict = {}
        self.status = "unknown"
        self.parent_id: Optional[str] = None
        self.color = "#00f0ff"
        self.url: Optional[str] = None
        self.role: Optional[str] = None
        self.galaxy: Optional[str] = None
        #: The address this entity's numbers were actually polled from. Separate from
        #: ``url`` (which is the operator-facing link) because on a shared host the two
        #: differ, and that difference is the whole question of whose figures these are.
        self.source_url: Optional[str] = None
        #: True when ``source_url`` is the host's shared service rather than one declared
        #: for this realm — the figures are real, they are just not only this realm's.
        self.source_shared: bool = False
        #: True when this entity is a FIXTURE the UNI scenario invented — a name from a
        #: list, not a component anything polled. Nothing answers for it, so its card must
        #: never offer an address or a figure: an address in a monospace font reads as a
        #: service, and a metric reads as a measurement.
        self.simulated: bool = False
        #: Why it is a fixture, in one clause. The frontend prefers its own localized text
        #: and falls back to this.
        self.simulated_note: Optional[str] = None

    def to_node(self) -> dict:
        node = {
            "id": self.id,
            "label": self.name,
            "group": self.group,
            "icon": self.icon,
            "description": self.description,
            "metrics": self.metrics,
            "status": self.status,
            "position": self.position,
            "url": self.url,
            "children": [],
            "color": self.color,
            "parent_id": self.parent_id,
            "created_at": self.created_at,
        }
        if self.role:
            node["role"] = self.role
        if self.galaxy:
            node["galaxy"] = self.galaxy
        if self.source_url:
            node["source_url"] = self.source_url
            if self.source_shared:
                node["source_shared"] = True
        if self.simulated:
            node["simulated"] = True
            if self.simulated_note:
                node["simulated_note"] = self.simulated_note
        return node


def foundry_anvil_tmp_dir() -> Path:
    """Where Foundry writes dump-state trees. Not the demo ``--state`` directory."""
    raw = (os.environ.get("ALIEN_FOUNDRY_ANVIL_TMP_DIR") or "").strip()
    if raw:
        return Path(raw)
    return Path.home() / ".foundry" / "anvil" / "tmp"


def _path_mtime(path: Path) -> float:
    with contextlib.suppress(OSError):
        return path.stat().st_mtime
    return 0.0


def _path_bytes(path: Path) -> int:
    total = 0
    with contextlib.suppress(OSError):
        if path.is_file():
            return int(path.stat().st_size)
        if not path.is_dir():
            return 0
        for child in path.rglob("*"):
            if child.is_file():
                with contextlib.suppress(OSError):
                    total += child.stat().st_size
    return total


def _unlink_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        return
    with contextlib.suppress(OSError):
        path.unlink()


def sweep_foundry_anvil_tmp(tmp: Path | None = None) -> dict[str, int]:
    """Reap Anvil dump trees under ``~/.foundry/anvil/tmp``.

    ``--state`` (the demo chain) lives in ``ALIEN_UNIVERSE_ANVIL_STATE_DIR``.
    Foundry *also* writes ``anvil-state-*`` dump directories next to its IPC
    cache and never deletes them. On the oracle host five of those trees reached
    **35 GB** and filled the disk — nginx then truncated responses, which is how
    a demo chain took down unrelated public pages.

    Keep the newest dump dir (for a crash you might actually look at) and a
    handful of files inside it. Everything else goes. Never raises: this runs
    on the monitor tick.
    """
    result = {"removed_dirs": 0, "removed_files": 0, "freed_bytes": 0}
    try:
        root = tmp if tmp is not None else foundry_anvil_tmp_dir()
        if not root.is_dir():
            return result
        keep_dirs = max(0, int(os.environ.get("ALIEN_FOUNDRY_ANVIL_TMP_KEEP_DIRS", "1") or 1))
        keep_files = max(0, int(os.environ.get("ALIEN_FOUNDRY_ANVIL_TMP_KEEP_FILES", "3") or 3))
        limit_mb = max(0, int(os.environ.get("ALIEN_FOUNDRY_ANVIL_TMP_MAX_MB", "256") or 256))

        dumps = [p for p in root.iterdir() if p.name.startswith("anvil-state-")]
        dumps.sort(key=_path_mtime, reverse=True)

        for dump in dumps:
            if not dump.is_dir():
                continue
            files = [p for p in dump.iterdir() if p.is_file()]
            files.sort(key=_path_mtime, reverse=True)
            for stale in files[keep_files:]:
                size = _path_bytes(stale)
                _unlink_path(stale)
                result["removed_files"] += 1
                result["freed_bytes"] += size

        for stale in dumps[keep_dirs:]:
            if not stale.exists():
                continue
            size = _path_bytes(stale)
            _unlink_path(stale)
            result["removed_dirs"] += 1
            result["freed_bytes"] += size

        if not limit_mb:
            return result
        limit = limit_mb * 1024 * 1024
        remaining = [
            p for p in root.iterdir()
            if p.name.startswith("anvil-state-") and p.exists()
        ]
        remaining.sort(key=_path_mtime)
        while remaining and _path_bytes(root) > limit:
            victim = remaining.pop(0)
            if victim.is_dir():
                files = [p for p in victim.iterdir() if p.is_file()]
                files.sort(key=_path_mtime)
                if files:
                    f = files[0]
                    size = _path_bytes(f)
                    _unlink_path(f)
                    result["removed_files"] += 1
                    result["freed_bytes"] += size
                    if any(victim.iterdir()):
                        remaining.insert(0, victim)
                    else:
                        _unlink_path(victim)
                        result["removed_dirs"] += 1
                    continue
            size = _path_bytes(victim)
            _unlink_path(victim)
            result["removed_dirs"] += 1
            result["freed_bytes"] += size
    except Exception:
        return result
    return result
