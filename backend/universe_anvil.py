"""The local chain's state on disk: Anvil state files kept, trimmed, quarantined or reset, the
Solana ledger, and chain processes and ports cleaned up.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from universe_entities import sweep_foundry_anvil_tmp


class AnvilStateMixin:
    """Anvil and Solana state on disk, and chain processes and ports."""

    def _anvil_state_dir(self) -> Path:
        raw = (os.environ.get("ALIEN_UNIVERSE_ANVIL_STATE_DIR") or "").strip()
        state_dir = Path(raw) if raw else (self.data_dir / "anvil-state")
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir

    def _solana_ledger_dir(self) -> Path:
        raw = (os.environ.get("ALIEN_UNIVERSE_SOLANA_LEDGER_DIR") or "").strip()
        ledger_dir = Path(raw) if raw else (self.data_dir / "solana-ledger")
        ledger_dir.mkdir(parents=True, exist_ok=True)
        return ledger_dir

    def _solana_validator_args(self) -> list[str]:
        """Lightweight local validator flags (~1.5GB RSS at defaults; smaller ledger helps when enabled)."""
        ledger_size = int(os.environ.get("ALIEN_UNIVERSE_SOLANA_LEDGER_SIZE", "2000"))
        return [
            "solana-test-validator",
            "--reset",
            "--quiet",
            "--rpc-port", "8899",
            "--bind-address", "127.0.0.1",
            "--ledger", str(self._solana_ledger_dir()),
            "--limit-ledger-size", str(max(500, ledger_size)),
        ]

    def _anvil_state_bytes(self) -> int:
        """Size of the persisted chain state, in bytes."""
        total = 0
        state_dir = self._anvil_state_dir()
        if not state_dir.exists():
            return 0
        for child in state_dir.iterdir():
            if child.is_file():
                with contextlib.suppress(OSError):
                    total += child.stat().st_size
        return total

    def _sweep_foundry_anvil_tmp(self) -> None:
        """Drop Foundry dump trees that are not the demo ``--state`` file.

        Anvil writes a full snapshot under ``~/.foundry/anvil/tmp/anvil-state-*``
        and never reaps it. Those trees are independent of
        ``ALIEN_UNIVERSE_ANVIL_STATE_DIR``; the size cap on ``state.json`` never
        sees them. Five of them reached **35 GB** on the oracle host and filled
        the disk. Safe to delete: anvil does not read them back.
        """
        stats = sweep_foundry_anvil_tmp()
        if stats["freed_bytes"] < 8 * 1024 * 1024:
            return
        note = (f"foundry anvil tmp sweep: freed {stats['freed_bytes'] / 1_048_576:.0f}MB "
                f"({stats['removed_dirs']} dump dirs, {stats['removed_files']} files)")
        print(f"[Universe] {note}")
        notes = getattr(self, "_bootstrap_notes", None)
        if isinstance(notes, list):
            notes.append(note)

    def _trim_oversized_anvil_state(self) -> None:
        """Reset the demo chain's state once it is too large to load in time.

        This is the real cause of the `anvil rpc timeout` that had the monitor reporting
        unhealthy 600 checks in a row on 2026-08-24: `--block-time 2` mines forever, so
        `state.json` had reached **331 MB**, and anvil loads the whole file before it answers
        a single RPC. The wait then expired, the universe was marked not-ready, and the next
        restart was slower still — a failure that gets worse on its own.

        A demo chain's value is being reproducible, not retaining six months of empty blocks,
        and `bootstrap` already redeploys the core contracts when the state is cleared. So the
        honest bound is a size cap with a loud line saying what was dropped and why.
        """
        with contextlib.suppress(Exception):
            self._sweep_foundry_anvil_tmp()
        limit_mb = max(1, int(os.environ.get("ALIEN_ANVIL_STATE_MAX_MB", "64") or 64))
        size = self._anvil_state_bytes()
        if size <= limit_mb * 1024 * 1024:
            return
        note = (f"anvil state was {size / 1_048_576:.0f}MB (cap {limit_mb}MB) — reset before "
                f"start; contracts will be redeployed. Raise ALIEN_ANVIL_STATE_MAX_MB to keep "
                f"more history, at the cost of a slower start.")
        print(f"[Universe] {note}")
        self._reset_anvil_state()
        self._bootstrap_notes.append(note)

    def _recycle_anvil_if_oversized(self) -> None:
        """The other half of the size cap: enforce it WHILE RUNNING, not only at start.

        ``_trim_oversized_anvil_state`` runs once, just before anvil is launched. That bounds how
        slow a *start* can be, and nothing else — the file keeps growing for as long as the container
        lives, because ``--block-time 2`` never stops mining. A container up for five days reached
        **1.73 GB** on the oracle host: 3.9 GB of RSS on a box with 12 GB, swap exhausted, and then
        anvil could no longer load its own state inside the readiness timeout, so the chain came back
        dead on the next restart. The start-time cap fired too late to prevent any of that, and would
        have kept firing every restart while the container that produced the file was never the one
        that paid for it.

        So the same bound is checked periodically here and acted on the same way the "stale wallet"
        path already does: stop, wipe, restart, redeploy. That costs a few seconds of chain downtime
        on a DEMO chain whose value is being reproducible, and buys a host that cannot be starved.
        """
        every = max(1, int(os.environ.get("ALIEN_ANVIL_STATE_CHECK_TICKS", "300") or 300))
        if self.tick < 2 or self.tick % every != 0:
            return
        # Foundry tmp dumps grow even when state.json is under the cap — sweep
        # them on this interval regardless of the --state file size.
        with contextlib.suppress(Exception):
            self._sweep_foundry_anvil_tmp()
        with contextlib.suppress(Exception):
            self._keep_last_good_anvil_state()
        limit_mb = max(1, int(os.environ.get("ALIEN_ANVIL_STATE_MAX_MB", "64") or 64))
        size = self._anvil_state_bytes()
        if size <= limit_mb * 1024 * 1024:
            return
        note = (f"anvil state grew to {size / 1_048_576:.0f}MB while running (cap {limit_mb}MB) — "
                f"recycling the demo chain now rather than letting it starve the host; contracts "
                f"will be redeployed.")
        print(f"[Universe] {note}")
        self._bootstrap_notes.append(note)
        with contextlib.suppress(Exception):
            self.stop_blockchain()
            self._reset_anvil_state()
            # bootstrap() takes the same lock and does start + verify + redeploy, which is exactly
            # the sequence a fresh state needs; re-implementing it here would be a second copy to
            # keep in step.
            self.bootstrap()

    def _ensure_anvil_alive(self) -> None:
        """Restart embedded Anvil when the subprocess dies but uvicorn keeps running."""
        every = max(1, int(os.environ.get("ALIEN_ANVIL_WATCHDOG_TICKS", "15") or 15))
        if self.tick < 2 or self.tick % every != 0:
            return
        if time.time() < self._anvil_watchdog_cooldown_until:
            return

        dead = False
        if self.anvil_proc is not None and self.anvil_proc.poll() is not None:
            dead = True
        elif not self._wait_for_anvil_rpc(timeout_sec=4):
            # A live anvil busy writing its state can miss one 4 s probe. Killing it then is
            # what cut a dump short on 2026-10-03; only a second miss in a row means down.
            self._anvil_rpc_misses = getattr(self, "_anvil_rpc_misses", 0) + 1
            dead = self.anvil_proc is None or self._anvil_rpc_misses >= 2
        else:
            self._anvil_rpc_misses = 0

        if not dead:
            if not self.blockchain_ready:
                self.blockchain_ready = True
            return

        cooldown = max(30, int(os.environ.get("ALIEN_ANVIL_WATCHDOG_COOLDOWN_S", "90") or 90))
        self._anvil_watchdog_cooldown_until = time.time() + cooldown
        note = "Anvil watchdog: chain unreachable — restarting UNI bootstrap"
        print(f"[Universe] {note}")
        self._bootstrap_notes.append(note)
        self.blockchain_ready = False
        self._anvil_rpc_misses = 0
        with contextlib.suppress(Exception):
            self.stop_blockchain()
        result = self.bootstrap()
        if not result.get("ok"):
            print(f"[Universe] Anvil watchdog bootstrap failed: {result.get('error')}")

    def _anvil_good_state_path(self) -> Path:
        """Last copy of ``state.json`` that parsed — outside the state dir, so the size cap
        does not count it twice and anvil never sees it."""
        return self._anvil_state_dir().parent / "anvil-state.last-good.json"

    @staticmethod
    def _state_file_readable(path: Path) -> bool:
        try:
            with path.open("rb") as fh:
                json.load(fh)
            return True
        except (OSError, ValueError):
            return False

    def _keep_last_good_anvil_state(self) -> None:
        """Copy ``state.json`` aside while it parses, so a dump cut short has a fallback."""
        state = self._anvil_state_dir() / "state.json"
        if not state.is_file() or not self._state_file_readable(state):
            return
        good = self._anvil_good_state_path()
        tmp = good.with_name(good.name + ".tmp")
        shutil.copyfile(state, tmp)
        # anvil may have rewritten the file mid-copy: keep the copy only if IT parses.
        if self._state_file_readable(tmp):
            os.replace(tmp, good)
        else:
            tmp.unlink(missing_ok=True)

    def _quarantine_unreadable_anvil_state(self) -> None:
        """Never hand anvil a state file it cannot parse.

        2026-10-03 15:44 UTC: the watchdog killed anvil while it was writing ``state.json``
        (``--state-interval`` dumps are not atomic). The file ended mid-string, anvil exited at
        once on every start ("failed to parse json file") with its stderr discarded, and the
        monitor reported "anvil rpc timeout after 90s (loading 4MB of state)" every 90 s for
        14 hours while the UNI demo chain — the charity lottery, ACEX — was gone. Move the
        broken file aside (kept, for whoever looks), fall back to the last good copy, and say
        so; with no good copy the chain starts empty and bootstrap redeploys the contracts.
        """
        state = self._anvil_state_dir() / "state.json"
        if not state.is_file() or self._state_file_readable(state):
            return
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        aside = self._anvil_state_dir().parent / f"anvil-state.unreadable-{stamp}.json"
        os.replace(state, aside)
        good = self._anvil_good_state_path()
        if good.is_file() and self._state_file_readable(good):
            shutil.copyfile(good, state)
            outcome = "restored the last good copy"
        else:
            outcome = "no good copy, so the chain starts empty and the contracts are redeployed"
        note = (f"anvil state.json did not parse (a dump cut short) — moved to {aside.name}; "
                f"{outcome}")
        print(f"[Universe] {note}")
        notes = getattr(self, "_bootstrap_notes", None)
        if isinstance(notes, list):
            notes.append(note)

    def _reset_anvil_state(self) -> None:
        state_dir = self._anvil_state_dir()
        for child in state_dir.iterdir():
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
        # A reset means "start empty": the fallback copy would bring the old chain back.
        self._anvil_good_state_path().unlink(missing_ok=True)
        self._bootstrap_notes.append("anvil state reset")

    def _free_chain_port(self, port: int) -> None:
        """Kill stale listeners on host-network UNI ports (orphans after container restart)."""
        if shutil.which("fuser"):
            with contextlib.suppress(OSError, subprocess.TimeoutExpired):
                subprocess.run(
                    ["fuser", "-k", f"{port}/tcp"],
                    capture_output=True,
                    timeout=5,
                    check=False,
                )

    def _kill_chain_orphans(self) -> None:
        """Drop orphan Anvil/Solana left on the host after unclean monitor restarts."""
        self._free_chain_port(8545)
        self._free_chain_port(8899)
        for pattern in (
            "anvil --host 127.0.0.1 --port 8545",
            "solana-test-validator --reset --quiet --rpc-port 8899",
        ):
            with contextlib.suppress(OSError):
                subprocess.run(["pkill", "-f", pattern], capture_output=True, timeout=5, check=False)
