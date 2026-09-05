"""
Universe runtime — local chain + live polls from deployed AIMarket layers.

UNI mode does not simulate metrics: Hub, Mesh, Factory, Prometheus and the
embedded EVM/Solana nodes are read from real endpoints and RPC.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Anvil account #0 — standard Foundry dev key (local universe only).
# Foundry/Anvil default mnemonic, account 0 (64-byte hex).
ANVIL_DEPLOYER_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


def _universe_solana_enabled() -> bool:
    """Embedded solana-test-validator for UNI Solana lottery deploy + solana graph node."""
    return os.environ.get("ALIEN_UNIVERSE_ENABLE_SOLANA", "0").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )

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


AICOM_ROOT = resolve_aicom_root()

# Poll Factory catalog every N ticks (~60s at 1.5s/tick) — not every broadcast.
_FACTORY_SYNC_EVERY_TICKS = max(1, int(os.environ.get("ALIEN_FACTORY_SYNC_TICKS", "40")))
_MAX_PRODUCT_ENTITIES = max(50, int(os.environ.get("ALIEN_MAX_PRODUCT_ENTITIES", "400")))


#: Colour per discovered group. A federated hub and a capability service are different kinds
#: of thing and must not share a colour — the map is how an operator tells them apart.
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


_DISCOVERED_COLORS: dict[str, str] = {
    "oracle": "#a64dff",
    "peer_hub": "#38e0ff",
    "peer_hub_node": "#7fd4ff",
    "pending_hub": "#ffcc4d",
}


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
        return node


# Back-compat alias for tests / imports
VirtualEntity = EcosystemEntity


class VirtualUniverse:
    def __init__(self, data_dir: Optional[Path] = None):
        self._bootstrap_lock = threading.Lock()
        self.data_dir = data_dir or (Path(__file__).resolve().parent.parent / "data" / "universe")
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.anvil_proc: Optional[subprocess.Popen] = None
        self.solana_proc: Optional[subprocess.Popen] = None

        self.evm_usdt_address: Optional[str] = None
        self.evm_escrow_address: Optional[str] = None
        self.evm_nft_address: Optional[str] = None
        self.evm_lottery_address: Optional[str] = None
        self.solana_lottery_program_id: Optional[str] = None
        self.evm_acex_vault_address: Optional[str] = None
        self.evm_acex_registry_address: Optional[str] = None
        self.evm_acex_lending_address: Optional[str] = None
        self.evm_acex_amm_address: Optional[str] = None
        self.evm_acex_audit_pool_address: Optional[str] = None
        self.payment_recipient: Optional[str] = None

        self._w3 = None
        self.entities: dict[str, EcosystemEntity] = {}
        self.products: list[dict] = []
        self.transactions: list[dict] = []
        self.agents: list[dict] = []
        self.chain_analytics: dict = {"blocks": 0, "tx_count": 0, "gas_spent": 0, "addresses": 0}

        self.tick = 0
        self.running = False
        self.blockchain_ready = False
        self._pending_materializations: list[dict] = []
        self._eth_accounts: list[str] = []
        self._last_layers: dict = {}
        self._discovered_ids: set[str] = set()
        self._discovery_links: list[dict] = []
        self._discovery_events: list[dict] = []
        self._scenario_engine = None
        self._factory_sync_every_ticks = int(os.environ.get("ALIEN_FACTORY_SYNC_TICKS", "40"))
        self._last_deploy_error: str | None = None
        self._bootstrap_notes: list[str] = []
        self._anvil_watchdog_cooldown_until: float = 0.0

        self.evm_rpc = (os.environ.get("ALIEN_UNIVERSE_EVM_RPC") or "http://127.0.0.1:8545").rstrip("/")
        self.solana_rpc = (os.environ.get("ALIEN_UNIVERSE_SOLANA_RPC") or "http://127.0.0.1:8899").rstrip("/")
        self.chain_label = os.environ.get("ALIEN_UNIVERSE_CHAIN_LABEL", "EVM Network")

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
            dead = True

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
        with contextlib.suppress(Exception):
            self.stop_blockchain()
        result = self.bootstrap()
        if not result.get("ok"):
            print(f"[Universe] Anvil watchdog bootstrap failed: {result.get('error')}")

    def _reset_anvil_state(self) -> None:
        state_dir = self._anvil_state_dir()
        for child in state_dir.iterdir():
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
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

    def start_blockchain(self) -> bool:
        with self._bootstrap_lock:
            return self._start_blockchain_locked()

    def _start_blockchain_locked(self) -> bool:
        started = False
        self._kill_chain_orphans()
        if shutil.which("anvil"):
            self._trim_oversized_anvil_state()
            try:
                anvil_args = [
                    "anvil",
                    "--host", "127.0.0.1",
                    "--port", "8545",
                    "--chain-id", "31337",
                    "--block-time", "2",
                    "--accounts", "20",
                    "--balance", "1000",
                    "--mnemonic",
                    os.environ.get(
                        "ALIEN_ANVIL_MNEMONIC",
                        "test test test test test test test test test test test junk",
                    ),
                    "--state", str(self._anvil_state_dir()),
                ]
                if os.environ.get("ALIEN_ANVIL_VERBOSE", "0") != "1":
                    anvil_args.append("--silent")
                self.anvil_proc = subprocess.Popen(
                    anvil_args,
                    stdout=subprocess.DEVNULL,
                    stderr=None if os.environ.get("ALIEN_ANVIL_VERBOSE") == "1" else subprocess.DEVNULL,
                )
                # 20s was a guess that held only while the state was small. Anvil answers
                # nothing until it has parsed the whole state file, so the budget has to scale
                # with what is on disk — and the failure message has to say what it was
                # waiting for, or the next person reads "timeout" and looks at the network.
                ready_budget = int(os.environ.get("ALIEN_ANVIL_READY_TIMEOUT_S", "90") or 90)
                state_mb = self._anvil_state_bytes() / 1_048_576
                if not self._wait_for_anvil_rpc(timeout_sec=ready_budget):
                    detail = (f"anvil rpc timeout after {ready_budget}s "
                              f"(loading {state_mb:.0f}MB of state)")
                    print(f"[Universe] {detail}")
                    self._last_deploy_error = detail
                    started = False
                else:
                    started = True
                    print("[Universe] EVM node online (Anvil, chain 31337)")
            except Exception as exc:
                print(f"[Universe] EVM start failed: {exc}")
                self._last_deploy_error = f"anvil start: {exc}"
        else:
            msg = "anvil not found — install Foundry (anvil, forge) on PATH"
            print(f"[Universe] {msg}")
            self._last_deploy_error = msg

        if _universe_solana_enabled() and shutil.which("solana-test-validator"):
            try:
                self.solana_proc = subprocess.Popen(
                    self._solana_validator_args(),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                time.sleep(3)
                print("[Universe] Solana node online")
            except Exception as exc:
                print(f"[Universe] Solana start failed: {exc}")
        elif not _universe_solana_enabled():
            print("[Universe] Solana skipped (ALIEN_UNIVERSE_ENABLE_SOLANA=0)")

        self.blockchain_ready = started
        if started:
            self._fetch_chain_state()
        return started

    def stop_blockchain(self):
        for proc in [self.anvil_proc, self.solana_proc]:
            if proc:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        self.anvil_proc = None
        self.solana_proc = None
        self._kill_chain_orphans()
        self._w3 = None
        self.blockchain_ready = False

    def _wait_for_anvil_rpc(self, timeout_sec: int = 20) -> bool:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            self._init_web3()
            if self._w3 and self._w3.is_connected():
                try:
                    _ = self._w3.eth.chain_id
                    return True
                except Exception:
                    pass
            time.sleep(1)
        return False

    def _init_web3(self):
        try:
            from web3 import Web3
        except ImportError:
            print("[Universe] web3.py missing — pip install web3")
            return
        self._w3 = Web3(Web3.HTTPProvider(self.evm_rpc))
        if self._w3.is_connected():
            self._eth_accounts = self._w3.eth.accounts
            self.payment_recipient = self._eth_accounts[0]
            print(f"[Universe] EVM connected — chain {self._w3.eth.chain_id}")

    def _fetch_chain_state(self):
        if not self._w3 or not self._w3.is_connected():
            return
        try:
            block = self._w3.eth.get_block("latest")
            self.chain_analytics["blocks"] = block["number"]
            self.chain_analytics["tx_count"] = len(self.transactions)
        except Exception:
            pass

    def deploy_contracts(self):
        if not self._w3 or not self._w3.is_connected():
            msg = "EVM not connected — skip deploy"
            print(f"[Universe] {msg}")
            self._last_deploy_error = msg
            return

        deployer = self._eth_accounts[0]
        self._deploy_usdt_forge(deployer)
        if not self.evm_usdt_address:
            return
        self._deploy_escrow_forge(deployer)
        self._deploy_nft_forge(deployer)
        self._fetch_chain_state()
        self._save_config()

    def _contract_has_code(self, address: str | None) -> bool:
        if not address or not self._w3 or not self._w3.is_connected():
            return False
        try:
            code = self._w3.eth.get_code(self._w3.to_checksum_address(address))
            return bool(code and code not in (b"", b"\x00"))
        except Exception:
            return False

    def _core_contracts_verified(self) -> bool:
        return (
            self._contract_has_code(self.evm_usdt_address)
            and self._contract_has_code(self.evm_escrow_address)
            and self._contract_has_code(self.evm_nft_address)
        )

    def _lottery_contract_verified(self) -> bool:
        return self._contract_has_code(self.evm_lottery_address)

    def _all_contracts_verified(self) -> bool:
        return self._core_contracts_verified() and self._lottery_contract_verified()

    def _load_config_from_disk(self) -> bool:
        path = self.data_dir / "universe_config.json"
        if not path.is_file():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[Universe] Could not read {path}: {exc}")
            return False
        self.evm_usdt_address = data.get("evm_usdt") or self.evm_usdt_address
        self.evm_escrow_address = data.get("evm_escrow") or self.evm_escrow_address
        self.evm_nft_address = data.get("evm_nft") or self.evm_nft_address
        self.evm_lottery_address = data.get("evm_lottery") or self.evm_lottery_address
        self.evm_acex_vault_address = data.get("evm_acex_vault") or self.evm_acex_vault_address
        self.evm_acex_registry_address = data.get("evm_acex_registry") or self.evm_acex_registry_address
        self.evm_acex_lending_address = data.get("evm_acex_lending") or self.evm_acex_lending_address
        self.evm_acex_amm_address = data.get("evm_acex_amm") or self.evm_acex_amm_address
        self.evm_acex_audit_pool_address = data.get("evm_acex_audit_pool") or self.evm_acex_audit_pool_address
        self.solana_lottery_program_id = (
            data.get("solana_lottery") or self.solana_lottery_program_id
        )
        self.payment_recipient = data.get("payment_recipient") or self.payment_recipient
        if data.get("evm_rpc"):
            self.evm_rpc = str(data["evm_rpc"]).rstrip("/")
        if data.get("solana_rpc"):
            self.solana_rpc = str(data["solana_rpc"]).rstrip("/")
        return True

    def bootstrap(self) -> dict:
        """Start Anvil, deploy contracts if needed, seed graph. Safe on container restart."""
        with self._bootstrap_lock:
            return self._bootstrap_locked()

    def _bootstrap_locked(self) -> dict:
        self.running = True
        self._bootstrap_notes = []
        self._last_deploy_error = None

        if not self._start_blockchain_locked():
            if not self.entities:
                self.seed_entities()
            return {
                "ok": False,
                "blockchain_ready": False,
                "error": self._last_deploy_error or "blockchain_start_failed",
                "entities": len(self.entities),
            }

        self._load_config_from_disk()
        if self._core_contracts_verified():
            note = "Core contracts already on chain — skip USDT/Escrow/NFT redeploy"
            print(f"[Universe] {note}")
            self._bootstrap_notes.append(note)
        else:
            print("[Universe] Deploying FakeUSDT + Escrow + NFT on Anvil…")
            self.deploy_contracts()
            if not self._core_contracts_verified() and "Insufficient funds" in (self._last_deploy_error or ""):
                print("[Universe] Resetting Anvil state (stale wallet) and redeploying…")
                self._reset_anvil_state()
                self.stop_blockchain()
                if self._start_blockchain_locked():
                    self.deploy_contracts()

        if not self._lottery_contract_verified():
            print("[Universe] Deploying AIAgentLottery on Anvil…")
            self._deploy_lottery_forge()
            self._save_config()

        from acex_uni import acex_uni_enabled, seed_acex_markets

        if acex_uni_enabled():
            if not self._acex_contracts_verified():
                print("[Universe] Deploying ACEX CapShare stack on Anvil…")
                self._deploy_acex_forge()
            if self._acex_contracts_verified():
                try:
                    seed_acex_markets(self)
                except Exception as exc:
                    print(f"[Universe] ACEX market seed skipped: {exc}")

        if not self.solana_lottery_program_id and _universe_solana_enabled():
            self._ensure_solana_deployer_keypair()
            deployed = self._deploy_solana_lottery()
            if deployed:
                self.solana_lottery_program_id = deployed
                self._save_config()
                self._bootstrap_notes.append(f"solana lottery: {deployed}")

        if not self.entities:
            self.seed_entities()

        if self._scenario_engine is None:
            from universe_layers import layer_urls
            from universe_scenario import UniverseScenarioEngine
            self._scenario_engine = UniverseScenarioEngine(hub_url=layer_urls()["hub"])

        try:
            added = self.sync_factory_catalog()
            if added:
                self._bootstrap_notes.append(f"factory catalog: +{added} products")
        except Exception as exc:
            print(f"[Universe] Factory catalog sync skipped: {exc}")

        ok = bool(
            self.blockchain_ready
            and self.evm_usdt_address
            and self.evm_escrow_address
            and self.evm_nft_address
            and self.evm_lottery_address
        )
        if not ok and not self._last_deploy_error:
            self._last_deploy_error = "one or more contracts missing after deploy"

        if ok:
            self._scenario_engine.funding_stream.ensure_hub_liquidity(self)

        return {
            "ok": ok,
            "blockchain_ready": self.blockchain_ready,
            "evm_usdt": self.evm_usdt_address,
            "evm_escrow": self.evm_escrow_address,
            "evm_nft": self.evm_nft_address,
            "evm_lottery": self.evm_lottery_address,
            "solana_lottery": self.solana_lottery_program_id,
            "payment_recipient": self.payment_recipient,
            "entities": len(self.entities),
            "hub_env_snippet": str(self.data_dir / "hub.env.snippet"),
            "notes": list(self._bootstrap_notes),
            "error": None if ok else self._last_deploy_error,
        }

    def _deploy_usdt_forge(self, deployer: str):
        addr = self._forge_run("script/DeployFakeUSDT.s.sol", deployer, {})
        if addr:
            self.evm_usdt_address = addr
            print(f"[Universe] USDT deployed: {self.evm_usdt_address}")
        else:
            print("[Universe] USDT deploy skipped (forge unavailable or failed)")
            if not self._last_deploy_error:
                self._last_deploy_error = "FakeUSDT deploy failed"

    def _forge_run(self, script: str, deployer: str, extra_env: dict) -> str | None:
        if not shutil.which("forge"):
            self._last_deploy_error = "forge not found on PATH"
            return None
        evm_dir = resolve_evm_contracts_dir()
        if not evm_dir.is_dir():
            self._last_deploy_error = f"contracts dir missing: {evm_dir}"
            print(f"[Universe] {self._last_deploy_error}")
            return None
        env = os.environ.copy()
        env["PRIVATE_KEY"] = ANVIL_DEPLOYER_KEY
        env["INITIAL_HUBS"] = deployer
        if self.evm_usdt_address:
            # SCALE CONTRACT: this token must report decimals() == 6. AIMarketEscrow's
            # constructor fails closed (UnsupportedTokenDecimals) on anything else,
            # because MIN_DEPOSIT/MAX_DEPOSIT are 6-decimal literals — so an
            # 18-decimal stand-in here does not misprice anything, it aborts the whole
            # bootstrap at Deploy.s.sol. FakeUSDT is pinned to 6 (contracts/evm/src/
            # FakeUSDT.sol, held by contracts/evm/test/FakeUSDT.t.sol). Any amount
            # sent to this token is therefore in 6-decimal base units — NOT wei.
            env["INITIAL_TOKENS"] = self.evm_usdt_address
        env.update(extra_env)
        try:
            proc = subprocess.run(
                ["forge", "script", script, "--rpc-url", self.evm_rpc, "--broadcast", "--slow"],
                cwd=str(evm_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            self._last_deploy_error = f"forge {script}: {exc}"
            print(f"[Universe] {self._last_deploy_error}")
            return None
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip()[-1500:]
            self._last_deploy_error = f"forge {script} exit {proc.returncode}: {tail}"
            print(f"[Universe] forge {script} failed:\n{tail}")
            return None
        return self._parse_broadcast_address(script, evm_dir)

    def _parse_broadcast_address(
        self,
        script: str,
        evm_dir: Path | None = None,
        *,
        contract_name: str | None = None,
    ) -> str | None:
        root = evm_dir or resolve_evm_contracts_dir()
        script_name = Path(script.split(":")[0]).name
        broadcast_dirs = [
            root / "broadcast" / script.split(":")[0] / "31337",
            root / "broadcast" / script_name / "31337",
        ]
        broadcast = next((d for d in broadcast_dirs if d.is_dir()), None)
        if broadcast is None:
            return None
        runs = sorted(broadcast.glob("run-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for run in runs[:3]:
            try:
                data = json.loads(run.read_text(encoding="utf-8"))
                for tx in data.get("transactions") or []:
                    if contract_name and tx.get("contractName") != contract_name:
                        continue
                    addr = tx.get("contractAddress")
                    if addr and addr.startswith("0x"):
                        return addr
                text = run.read_text(encoding="utf-8")
                m = re.search(r"0x[a-fA-F0-9]{40}", text)
                if m:
                    return m.group(0)
            except (OSError, json.JSONDecodeError):
                continue
        return None

    def _parse_broadcast_contract_map(
        self,
        script: str,
        evm_dir: Path | None = None,
    ) -> dict[str, str]:
        root = evm_dir or resolve_evm_contracts_dir()
        script_name = Path(script.split(":")[0]).name
        broadcast_dirs = [
            root / "broadcast" / script.split(":")[0] / "31337",
            root / "broadcast" / script_name / "31337",
        ]
        broadcast = next((d for d in broadcast_dirs if d.is_dir()), None)
        out: dict[str, str] = {}
        if broadcast is None:
            return out
        runs = sorted(broadcast.glob("run-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for run in runs[:3]:
            try:
                data = json.loads(run.read_text(encoding="utf-8"))
                for tx in data.get("transactions") or []:
                    name = tx.get("contractName")
                    addr = tx.get("contractAddress")
                    if name and addr and str(addr).startswith("0x"):
                        out[str(name)] = str(addr)
                if out:
                    return out
            except (OSError, json.JSONDecodeError):
                continue
        return out

    def _deploy_escrow_forge(self, deployer: str):
        addr = self._forge_run("script/Deploy.s.sol", deployer, {})
        if addr:
            self.evm_escrow_address = addr
            print(f"[Universe] Escrow deployed: {addr}")
        else:
            print("[Universe] Escrow deploy skipped (forge unavailable or failed)")

    def _deploy_nft_forge(self, deployer: str):
        addr = self._forge_run("script/DeployNFT.s.sol", deployer, {})
        if addr:
            self.evm_nft_address = addr
            print(f"[Universe] NFT deployed: {addr}")
        elif not self._last_deploy_error:
            self._last_deploy_error = "NFT deploy failed"

    def _deploy_lottery_forge(self):
        if not self.evm_usdt_address:
            self._last_deploy_error = "USDT required before lottery deploy"
            print(f"[Universe] {self._last_deploy_error}")
            return
        lot_dir = resolve_lottery_contracts_dir()
        if lot_dir is None:
            self._last_deploy_error = "lottery/contracts not found"
            print(f"[Universe] {self._last_deploy_error}")
            return
        extra = {
            # Native ETH tickets — relayer economy engine sends value= on buyTickets/fund.
            "TOKEN": os.environ.get("ALIEN_LOTTERY_TOKEN", "0x0000000000000000000000000000000000000000"),
            "TICKET_PRICE": os.environ.get("ALIEN_LOTTERY_TICKET_PRICE", str(10**15)),
            "ONCHAIN_VDF": os.environ.get("ALIEN_LOTTERY_ONCHAIN_VDF", "false"),
            "PRIZE_BPS": os.environ.get("ALIEN_LOTTERY_PRIZE_BPS", "8000"),
            "OPEX_BPS": os.environ.get("ALIEN_LOTTERY_OPEX_BPS", "1200"),
            "OPERATOR_BPS": os.environ.get("ALIEN_LOTTERY_OPERATOR_BPS", "800"),
            "ENTRY_WINDOW": os.environ.get("ALIEN_LOTTERY_ENTRY_WINDOW", "86400"),
            "MIN_DRAW_DELAY": os.environ.get("ALIEN_LOTTERY_MIN_DRAW_DELAY", "60"),
        }
        addr = self._forge_run_in_dir(
            lot_dir,
            "script/DeployLottery.s.sol:DeployLottery",
            extra,
            contract_name="AIAgentLottery",
        )
        if addr:
            self.evm_lottery_address = addr
            print(f"[Universe] AIAgentLottery deployed: {addr}")
            self._bootstrap_notes.append(f"lottery evm: {addr}")
        elif not self._last_deploy_error:
            self._last_deploy_error = "AIAgentLottery deploy failed"

    def _acex_contracts_verified(self) -> bool:
        return (
            self._contract_has_code(self.evm_acex_amm_address)
            and self._contract_has_code(self.evm_acex_registry_address)
        )

    def _deploy_acex_forge(self) -> None:
        from acex_uni import acex_uni_enabled

        if not acex_uni_enabled():
            return
        if not self.evm_usdt_address:
            self._last_deploy_error = "USDT required before ACEX deploy"
            print(f"[Universe] {self._last_deploy_error}")
            return
        acex_dir = resolve_acex_evm_dir()
        if acex_dir is None:
            self._last_deploy_error = "acex/contracts/evm not found"
            print(f"[Universe] {self._last_deploy_error}")
            return
        if not shutil.which("forge"):
            self._last_deploy_error = "forge not found on PATH"
            return
        env = os.environ.copy()
        env["PRIVATE_KEY"] = ANVIL_DEPLOYER_KEY
        env["DEPLOYER_PRIVATE_KEY"] = ANVIL_DEPLOYER_KEY
        env["USDC_ADDRESS"] = self.evm_usdt_address
        try:
            proc = subprocess.run(
                ["forge", "script", "script/DeployACEX.s.sol:DeployACEX", "--rpc-url", self.evm_rpc, "--broadcast", "--slow"],
                cwd=str(acex_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            self._last_deploy_error = f"forge DeployACEX: {exc}"
            print(f"[Universe] {self._last_deploy_error}")
            return
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip()[-1500:]
            self._last_deploy_error = f"forge DeployACEX exit {proc.returncode}: {tail}"
            print(f"[Universe] forge DeployACEX failed:\n{tail}")
            return
        deployed = self._parse_broadcast_contract_map("script/DeployACEX.s.sol:DeployACEX", acex_dir)
        self.evm_acex_vault_address = deployed.get("AgentCollateralVault") or self.evm_acex_vault_address
        self.evm_acex_registry_address = deployed.get("AgentListingRegistry") or self.evm_acex_registry_address
        self.evm_acex_lending_address = deployed.get("AgentLendingPool") or self.evm_acex_lending_address
        self.evm_acex_amm_address = deployed.get("PulseAMM") or self.evm_acex_amm_address
        self.evm_acex_audit_pool_address = deployed.get("AgentAuditPool") or self.evm_acex_audit_pool_address
        if self.evm_acex_amm_address:
            print(f"[Universe] ACEX deployed — PulseAMM {self.evm_acex_amm_address}")
            self._bootstrap_notes.append(f"acex amm: {self.evm_acex_amm_address}")
            self._save_config()
        elif not self._last_deploy_error:
            self._last_deploy_error = "ACEX deploy produced no addresses"

    def _forge_run_in_dir(
        self,
        project_dir: Path,
        script: str,
        extra_env: dict,
        *,
        contract_name: str | None = None,
    ) -> str | None:
        if not shutil.which("forge"):
            self._last_deploy_error = "forge not found on PATH"
            return None
        if not project_dir.is_dir():
            self._last_deploy_error = f"project dir missing: {project_dir}"
            return None
        env = os.environ.copy()
        env["PRIVATE_KEY"] = ANVIL_DEPLOYER_KEY
        env.update(extra_env)
        try:
            proc = subprocess.run(
                ["forge", "script", script, "--rpc-url", self.evm_rpc, "--broadcast", "--slow"],
                cwd=str(project_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            self._last_deploy_error = f"forge {script}: {exc}"
            print(f"[Universe] {self._last_deploy_error}")
            return None
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip()[-1500:]
            self._last_deploy_error = f"forge {script} exit {proc.returncode}: {tail}"
            print(f"[Universe] forge {script} failed:\n{tail}")
            return None
        return self._parse_broadcast_address(script, project_dir, contract_name=contract_name)

    def _solana_rpc_ready(self) -> bool:
        if not self.solana_rpc:
            return False
        try:
            proc = subprocess.run(
                ["solana", "cluster-version", "--url", self.solana_rpc],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return proc.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False

    def _ensure_solana_deployer_keypair(self) -> None:
        if not shutil.which("solana-keygen"):
            return
        kp = Path.home() / ".config" / "solana" / "id.json"
        if not kp.is_file():
            kp.parent.mkdir(parents=True, exist_ok=True)
            try:
                subprocess.run(
                    ["solana-keygen", "new", "-o", str(kp), "--no-bip39-passphrase", "-s", "-f"],
                    capture_output=True,
                    timeout=30,
                    check=False,
                )
            except (subprocess.TimeoutExpired, OSError):
                return
        if kp.is_file() and self._solana_rpc_ready() and shutil.which("solana"):
            subprocess.run(
                ["solana", "airdrop", "10", "--url", self.solana_rpc, "--keypair", str(kp)],
                capture_output=True,
                timeout=30,
                check=False,
            )

    def _deploy_solana_lottery(self) -> str | None:
        """Build + deploy aimarket-lottery to the local UNI validator when available."""
        if os.environ.get("ALIEN_UNIVERSE_DEPLOY_SOLANA_LOTTERY", "1").strip().lower() in (
            "0",
            "false",
            "no",
            "off",
        ):
            return None
        if not shutil.which("cargo-build-sbf") or not shutil.which("solana"):
            print("[Universe] Solana lottery skipped — cargo-build-sbf/solana not on PATH")
            return None
        if not self._solana_rpc_ready():
            print("[Universe] Solana lottery skipped — RPC not ready")
            return None
        sol_dir = resolve_solana_contracts_dir()
        if sol_dir is None:
            print("[Universe] Solana lottery skipped — contracts/solana missing")
            return None
        keypair = sol_dir / "keys" / "aimarket_lottery-keypair.json"
        if not keypair.is_file():
            print(f"[Universe] Solana lottery skipped — keypair missing: {keypair}")
            return None
        program_so = sol_dir / "target" / "deploy" / "aimarket_lottery.so"
        if not program_so.is_file():
            print("[Universe] Building aimarket-lottery (cargo-build-sbf)…")
            build_env = os.environ.copy()
            build_env["CARGO_TARGET_DIR"] = str(sol_dir / "target")
            try:
                proc = subprocess.run(
                    ["cargo-build-sbf", "--manifest-path", "programs/aimarket-lottery/Cargo.toml"],
                    cwd=str(sol_dir),
                    env=build_env,
                    capture_output=True,
                    text=True,
                    timeout=600,
                    check=False,
                )
            except (subprocess.TimeoutExpired, OSError) as exc:
                print(f"[Universe] Solana lottery build failed: {exc}")
                return None
            if proc.returncode != 0:
                tail = (proc.stderr or proc.stdout or "").strip()[-1500:]
                print(f"[Universe] cargo-build-sbf failed:\n{tail}")
                return None
        if not program_so.is_file():
            print("[Universe] Solana lottery .so missing after build")
            return None
        program_id = subprocess.run(
            ["solana-keygen", "pubkey", str(keypair)],
            capture_output=True,
            text=True,
            check=False,
        )
        expected = (program_id.stdout or "").strip()
        try:
            payer = os.environ.get("SOLANA_DEPLOYER_KEYPAIR", "").strip()
            if not payer:
                payer = str(Path.home() / ".config" / "solana" / "id.json")
            deploy_cmd = [
                "solana",
                "program",
                "deploy",
                str(program_so),
                "--url",
                self.solana_rpc,
                "--program-id",
                str(keypair),
            ]
            if Path(payer).is_file():
                deploy_cmd.extend(["--keypair", payer])
            proc = subprocess.run(
                deploy_cmd,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            print(f"[Universe] Solana lottery deploy failed: {exc}")
            return None
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0 and "already deployed" not in out.lower():
            print(f"[Universe] solana program deploy failed:\n{out[-1500:]}")
            return None
        m = re.search(r"Program Id:\s*([1-9A-HJ-NP-Za-km-z]{32,44})", out)
        deployed = m.group(1) if m else expected
        if deployed:
            print(f"[Universe] aimarket-lottery deployed: {deployed}")
        return deployed or None

    def _write_hub_env_snippet(self) -> None:
        if not self.evm_escrow_address:
            return
        lines = [
            "# Generated by Alien Monitor UNI bootstrap — merge into aicom/.env and restart Hub",
            f"AIMARKET_ESCROW_EVM_ADDRESS={self.evm_escrow_address}",
            f"AIMARKET_NFT_CONTRACT={self.evm_nft_address or ''}",
            f"AIMARKET_PAYMENT_RECIPIENT={self.payment_recipient or ''}",
            "ALIEN_EVM_RPC=http://127.0.0.1:8545",
            "AIMARKET_NFT_CHAIN_RPC=http://127.0.0.1:8545",
            "# Off-chain channel ledger for local UNI (set 0 for full on-chain verify):",
            "AIFACTORY_PAYMENT_VERIFY_STUB=1",
        ]
        if self.evm_usdt_address:
            lines.insert(4, f"# FakeUSDT on Anvil: {self.evm_usdt_address}")
        if self.evm_lottery_address:
            lines.extend(
                [
                    f"HUB_LOTTERY_ADDRESS={self.evm_lottery_address}",
                    f"AIMARKET_CHARITY_LOTTERY_ADDRESS={self.evm_lottery_address}",
                    f"LOTTERY_ADDRESS={self.evm_lottery_address}",
                    "HUB_CHARITY_ENABLED=1",
                    "HUB_TITHE_BPS=2000",
                    "LOTTERY_CHAIN_ID=31337",
                ]
            )
        if self.evm_acex_amm_address:
            lines.extend(
                [
                    f"AIMARKET_ADDR_UNI_PulseAMM={self.evm_acex_amm_address}",
                    f"AIMARKET_ADDR_UNI_AgentListingRegistry={self.evm_acex_registry_address or ''}",
                    f"AIMARKET_ADDR_UNI_AgentLendingPool={self.evm_acex_lending_address or ''}",
                    f"AIMARKET_ADDR_UNI_AgentCollateralVault={self.evm_acex_vault_address or ''}",
                    f"ARGUS_UNI_ACEX_AMM={self.evm_acex_amm_address}",
                    f"ARGUS_UNI_ACEX_REGISTRY={self.evm_acex_registry_address or ''}",
                    f"ARGUS_UNI_LENDING_POOL={self.evm_acex_lending_address or ''}",
                    f"ARGUS_UNI_USDC={self.evm_usdt_address or ''}",
                    "ACEX_AUTO_IPO=1",
                ]
            )
        if self.solana_lottery_program_id:
            lines.extend(
                [
                    f"AIMARKET_LOTTERY_SOLANA_PROGRAM_ID={self.solana_lottery_program_id}",
                    f"SOLANA_RPC_URL={self.solana_rpc}",
                ]
            )
        snippet = self.data_dir / "hub.env.snippet"
        snippet.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[Universe] Hub env snippet: {snippet}")

    def _record_tx(self, tx_hash, receipt, action: str, target: str):
        self.transactions.append(
            {
                "id": tx_hash.hex()[:16],
                "hash": tx_hash.hex(),
                "from": str(receipt.get("from", "0x")),
                "to": str(receipt.get("to") or target),
                "action": action,
                "target": target,
                "amount": 0,
                "token": "ETH",
                "block": receipt.get("blockNumber", 0),
                "gas_used": receipt.get("gasUsed", 0),
                "status": "confirmed",
                "ts": datetime.now(timezone.utc).isoformat(),
                "onchain": True,
            }
        )
        if len(self.transactions) > 100:
            self.transactions = self.transactions[-100:]

    def _save_config(self):
        config = {
            "evm_rpc": self.evm_rpc,
            "solana_rpc": self.solana_rpc,
            "evm_usdt": self.evm_usdt_address,
            "evm_escrow": self.evm_escrow_address,
            "evm_nft": self.evm_nft_address,
            "evm_lottery": self.evm_lottery_address,
            "evm_acex_vault": self.evm_acex_vault_address,
            "evm_acex_registry": self.evm_acex_registry_address,
            "evm_acex_lending": self.evm_acex_lending_address,
            "evm_acex_amm": self.evm_acex_amm_address,
            "evm_acex_audit_pool": self.evm_acex_audit_pool_address,
            "solana_lottery": self.solana_lottery_program_id,
            "payment_recipient": self.payment_recipient,
            "chain_id": 31337,
            "chain_label": self.chain_label,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        (self.data_dir / "universe_config.json").write_text(json.dumps(config, indent=2))
        self._write_hub_env_snippet()

    def seed_entities(self):
        """Seed topology skeleton — metrics filled on first tick from live layers."""
        from lottery_layers import lottery_node_spec
        from factory_products import factory_public_url
        from universe_layers import layer_urls
        from ecosystem_layout import NODE_POSITIONS, node_position

        urls = layer_urls()
        from hub_affiliation import hub_public_url

        specs = [
            # Operator card uses public HTTPS; layer_urls()[\"hub\"] stays the Docker API poll target.
            ("hub", "AIMarket Hub", "core", "core", "hub", {"x": 0, "y": 0, "z": 0}, hub_public_url()),
            ("factory", "AI-Factory", "core", "core", "factory", {"x": 4, "y": 2, "z": -2}, factory_public_url()),
            ("mesh", "AI Service Mesh", "core", "core", "mesh", {"x": -4, "y": -1, "z": 2}, urls["mesh"]),
            ("acex", "ACEX", "core", "core", "exchange", {"x": 2, "y": -3, "z": 4}, None),
            ("evm_escrow", "EVM Escrow", "contract", "contract", "contract", {"x": 6, "y": 3, "z": 1}, None),
            ("solana_escrow", "Solana Escrow", "contract", "contract", "contract", {"x": 5, "y": -2, "z": -3}, None),
            ("nft_contract", "Capability NFT", "contract", "contract", "contract", {"x": 7, "y": 0, "z": -1}, None),
            ("desktop_apps", "Desktop Apps", "client", "client", "client", {"x": -3, "y": 4, "z": -4}, None),
            ("plugins", "Plugins", "infra", "infra", "infra", {"x": 0, "y": -5, "z": -3}, None),
            ("sdk_dart", "Dart SDK", "sdk", "sdk", "sdk", {"x": -5, "y": 1, "z": 5}, None),
            ("sdk_typescript", "TypeScript SDK", "sdk", "sdk", "sdk", {"x": -6, "y": -1, "z": 4}, None),
            ("sdk_rust", "Rust SDK", "sdk", "sdk", "sdk", {"x": -5, "y": 2, "z": -5}, None),
            ("federation", "Federation", "network", "network", "network", {"x": -2, "y": 5, "z": 1}, None),
            ("widget", "Widget", "client", "client", "client", {"x": 3, "y": 5, "z": -2}, None),
            ("ethereum", self.chain_label, "chain", "chain", "chain", {"x": 8, "y": 3, "z": 3}, self.evm_rpc),
            ("solana", "Solana", "chain", "chain", "chain", {"x": 8, "y": -2, "z": -4}, self.solana_rpc),
            ("cli", "CLI Tools", "client", "client", "client", {"x": -3, "y": -4, "z": 5}, None),
        ]
        for eid, name, etype, group, icon, pos, url in specs:
            ent = EcosystemEntity(eid, name, etype, group, icon=icon)
            # Prefer the shared layout anchors — hard-coded UNI slots drifted and
            # stacked Federation on top of factory Agents.
            ent.position = dict(NODE_POSITIONS[eid]) if eid in NODE_POSITIONS else pos
            ent.url = url
            ent.metrics = {}
            if eid == "hub":
                ent.role = "hub"
            if eid == "factory":
                ent.role = "hub"
                ent.color = "#00f0ff"
            self.entities[eid] = ent
        lot_spec = lottery_node_spec()
        lot = EcosystemEntity(
            lot_spec["id"],
            lot_spec["label"],
            "economy",
            lot_spec["group"],
            icon=lot_spec["icon"],
            description=lot_spec["description"],
        )
        lot.position = lot_spec["position"]
        lot.url = lot_spec.get("url")
        lot.metrics = dict(lot_spec.get("metrics") or {})
        lot.color = "#ffd700"
        self.entities[lot.id] = lot
        from argus_layers import argus_node_spec

        arg_spec = argus_node_spec(mode="universe")
        arg = EcosystemEntity(
            arg_spec["id"],
            arg_spec["label"],
            "agent",
            arg_spec["group"],
            icon=arg_spec["icon"],
            description=arg_spec["description"],
        )
        arg.position = arg_spec["position"]
        arg.url = arg_spec["url"]
        arg.metrics = dict(arg_spec.get("metrics") or {})
        arg.status = arg_spec.get("status", "offline")
        arg.color = "#36e6ff"
        self.entities[arg.id] = arg

        # Universe mode renders self.entities, NOT build_topology() — a node seeded
        # only there is invisible here (the lesson MOMUS and LOGOS both taught).
        from factory_agents import factory_agents_node_spec

        fa_spec = factory_agents_node_spec(mode="universe")
        fa = EcosystemEntity(
            fa_spec["id"],
            fa_spec["label"],
            "agent",
            fa_spec["group"],
            icon=fa_spec["icon"],
            description=fa_spec["description"],
        )
        # Always re-anchor from the shared layout (never a stale seed copy).
        fa.position = node_position("factory_agents", fallback=fa_spec["position"])
        fa.url = fa_spec["url"]
        fa.metrics = dict(fa_spec.get("metrics") or {})
        fa.status = fa_spec.get("status", "idle")
        fa.color = "#7ee787"
        self.entities[fa.id] = fa

        from dioscuri_layers import dioscuri_node_spec

        dio_spec = dioscuri_node_spec(mode="universe")
        dio = EcosystemEntity(
            dio_spec["id"],
            dio_spec["label"],
            "community",
            dio_spec["group"],
            icon=dio_spec["icon"],
            description=dio_spec["description"],
        )
        dio.position = dio_spec["position"]
        dio.url = dio_spec["url"]
        dio.metrics = dict(dio_spec.get("metrics") or {})
        dio.status = dio_spec.get("status", "offline")
        dio.color = "#c9a227"
        self.entities[dio.id] = dio
        from helios_layers import helios_node_spec

        hel_spec = helios_node_spec(mode="universe")
        hel = EcosystemEntity(
            hel_spec["id"],
            hel_spec["label"],
            "broadcast",
            hel_spec["group"],
            icon=hel_spec["icon"],
            description=hel_spec["description"],
        )
        hel.position = hel_spec["position"]
        hel.url = hel_spec["url"]
        hel.metrics = dict(hel_spec.get("metrics") or {})
        hel.status = hel_spec.get("status", "offline")
        hel.color = "#ff6b35"
        self.entities[hel.id] = hel
        self._seed_metis_entity()
        self._seed_skopos_entity()
        self._seed_gaia_entity()
        self._seed_atlas_entity()
        self._seed_hephaestus_entity()
        self._seed_momus_entity()
        self._seed_warden_entity()
        self._seed_treasury_entity()
        self._seed_logos_entity()
        self._seed_bridges_entity()
        self._seed_themis_entity()
        self._seed_basanos_entity()
        self._seed_settlement_entity()
        self._seed_competing_lab_entities()
        self._seed_oracle_family()
        print(f"[Universe] {len(self.entities)} nodes ready (incl. oracle family) — awaiting layer poll")

    def _seed_hephaestus_entity(self) -> None:
        """The forge. Universe mode builds its graph from these entities, NOT from
        build_topology(), and the apply_*_graph helpers only DECORATE a node that already
        exists — so a satellite registered only in build_topology() is invisible here."""
        if "hephaestus" in self.entities:
            return
        from hephaestus_layers import hephaestus_node_spec

        spec = hephaestus_node_spec(mode="universe")
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "studio",
            spec["group"],
            icon=spec.get("icon"),
            description=spec.get("description"),
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "offline")
        ent.color = "#ffa94d"
        self.entities[ent.id] = ent

    def _seed_momus_entity(self) -> None:
        """Adversarial-audit red team — the offensive complement to ARGUS's defensive WARDEN.

        Universe mode builds its graph from these entities, NOT from build_topology(), and the
        apply_*_graph helpers only DECORATE a node that already exists. So a satellite that is only
        registered in build_topology() is invisible here — which is exactly what happened: the map
        had no MOMUS node and the assistant, asked "where is momus", reported that it was not part of
        the ecosystem at all.
        """
        if "momus" in self.entities:
            return
        from momus_layers import momus_node_spec

        spec = momus_node_spec(mode="universe")
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "security",
            spec["group"],
            icon=spec.get("icon"),
            description=spec.get("description"),
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "offline")
        ent.color = "#ff2d6f"
        self.entities[ent.id] = ent

    def _seed_warden_entity(self) -> None:
        """The invoke-time firewall, drawn as a LAYER.

        WARDEN is a library — no port, no /health — so it is the one security node with no host of
        its own. It was left off the graph for exactly that reason, and the assistant then answered
        "where is WARDEN?" with "inside ARGUS": a firewall the whole ecosystem depends on, rendered
        as one agent's internal feature. Its telemetry is borrowed from the two ends that do have
        addresses (MOMUS publishes the signed feed, ARGUS enforces it).
        """
        if "warden" in self.entities:
            return
        from warden_layers import warden_node_spec

        spec = warden_node_spec(mode="universe")
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "security",
            spec["group"],
            icon=spec.get("icon"),
            description=spec.get("description"),
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "idle")
        ent.color = "#4ad9c4"
        self.entities[ent.id] = ent

    def _seed_treasury_entity(self) -> None:
        """The separately-keyed payer. A distinct node on purpose: the whole design rests on MOMUS
        and the Treasury being different principals, and a map that drew them as one would show the
        opposite of the property that matters."""
        if "treasury" in self.entities:
            return
        from momus_layers import treasury_node_spec

        spec = treasury_node_spec(mode="universe")
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "security",
            spec["group"],
            icon=spec.get("icon"),
            description=spec.get("description"),
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "offline")
        ent.color = "#f6a92b"
        self.entities[ent.id] = ent

    def _seed_logos_entity(self) -> None:
        """Read-only federation intelligence must exist in the graph before live data decorates it.

        Universe mode renders ``self.entities`` rather than ``build_topology()``.  Keeping LOGOS
        only in the static topology made ``apply_logos_to_nodes`` a silent no-op in this mode and
        left the monitor claiming that a documented, deployed component was absent.
        """
        if "logos" in self.entities:
            return
        from logos_layers import logos_node_spec

        spec = logos_node_spec()
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "analytics",
            spec["group"],
            icon=spec.get("icon"),
            description=spec.get("description"),
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "unknown")
        ent.color = "#00e5ff"
        self.entities[ent.id] = ent

    def _seed_bridges_entity(self) -> None:
        """The third paid invoke channel (hub, mesh, bridges) — framework-native tool export.

        Seeded here and not only in build_topology() for the reason the MOMUS gap taught: universe
        mode renders ``u.entities``, and ``apply_bridges_graph`` only DECORATES, returning early
        when the node is absent. A satellite registered in build_topology() alone is invisible in
        this mode while looking perfectly wired in the diff.

        The entity keeps ``metrics = {}`` from the spec — empty, not zeroed. Nothing in the UNI
        simulator fills it in later either: this channel is uninstrumented everywhere, and the
        simulator inventing a turnover for it would be the worst possible place to do so.
        """
        if "bridges" in self.entities:
            return
        from bridges_layers import bridges_node_spec

        spec = bridges_node_spec(mode="universe")
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "channel",
            spec["group"],
            icon=spec.get("icon"),
            description=spec.get("description"),
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "offline")
        ent.color = "#5ad1ff"
        self.entities[ent.id] = ent

    def _seed_themis_entity(self) -> None:
        """Publish admission gate; must exist because UNI ignores build_topology()."""
        if "themis" in self.entities:
            return
        from themis_layers import themis_node_spec

        spec = themis_node_spec(mode="universe")
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "security",
            spec["group"],
            icon=spec.get("icon"),
            description=spec.get("description"),
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "offline")
        ent.color = spec.get("color", "#66f7c5")
        self.entities[ent.id] = ent

    def _seed_settlement_entity(self) -> None:
        """The settlement node exists in UNI too: the universe has its own escrow, and the
        node's job is to show where an authorisation becomes chain state on whatever chain
        this mode is pointed at."""
        if "settlement" in self.entities:
            return
        from settlement_layers import settlement_node_spec

        spec = settlement_node_spec(mode="universe")
        # An EcosystemEntity, not a dict: the universe calls `.to_node()` on everything in
        # `entities`, so a plain dict here is a 500 on /api/topology — which is exactly what it
        # was until this line was fixed.
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "crypto",
            spec["group"],
            icon=spec.get("icon"),
            description=spec.get("description"),
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "offline")
        ent.color = spec.get("color", "#5ad1a8")
        self.entities[ent.id] = ent

    def _seed_basanos_entity(self) -> None:
        """Solidity touchstone; must exist because UNI ignores build_topology()."""
        if "basanos" in self.entities:
            return
        from basanos_layers import basanos_node_spec

        spec = basanos_node_spec(mode="universe")
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "security",
            spec["group"],
            icon=spec.get("icon"),
            description=spec.get("description"),
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "offline")
        ent.color = spec.get("color", "#e8c36a")
        self.entities[ent.id] = ent

    def _seed_competing_lab_entities(self) -> None:
        """Second galaxy: Competing Lab Hub + Signal Hunt + use-cases portal.

        Far-offset positions live in ecosystem_layout.COMPETING_GALAXY_ANCHOR so the cluster
        does not collapse into the primary federation ring. Universe mode must seed these
        here — build_topology() alone is invisible in UNI.
        """
        from competing_lab_layers import (
            competing_hub_node_spec,
            signal_hunt_hub_node_spec,
            signal_hunt_node_spec,
            use_cases_node_spec,
        )

        colors = {
            "competing_hub": "#ff8c42",
            "signal_hunt_hub": "#d946ef",
            "signal_hunt": "#ff5ec8",
            "use_cases": "#c4f542",
        }
        for spec in (
            competing_hub_node_spec(),
            signal_hunt_hub_node_spec(),
            signal_hunt_node_spec(),
            use_cases_node_spec(),
        ):
            eid = spec["id"]
            if eid in self.entities:
                # Refresh identity so role/icon drift is corrected (hub vs game).
                ent = self.entities[eid]
                if spec.get("role") is not None:
                    ent.role = spec.get("role")
                if spec.get("icon"):
                    ent.icon = spec["icon"]
                if spec.get("group"):
                    ent.group = spec["group"]
                if spec.get("galaxy"):
                    ent.galaxy = spec["galaxy"]
                if colors.get(eid):
                    ent.color = colors[eid]
                if spec.get("description"):
                    ent.description = spec["description"]
                if spec.get("label"):
                    ent.name = spec["label"]
                continue
            ent = EcosystemEntity(
                eid,
                spec["label"],
                "network",
                spec["group"],
                icon=spec.get("icon"),
                description=spec.get("description"),
            )
            ent.position = spec["position"]
            ent.url = spec.get("url")
            ent.metrics = dict(spec.get("metrics") or {})
            ent.status = spec.get("status", "unknown")
            ent.color = colors.get(eid, "#ff8c42")
            # Stash hub role / galaxy on the entity so to_node can forward them.
            ent.role = spec.get("role")
            ent.galaxy = spec.get("galaxy")
            self.entities[eid] = ent

    def _seed_gaia_entity(self) -> None:
        """Physical-oracle gateway — third oracle class (math → METIS → GAIA)."""
        if "gaia" in self.entities:
            return
        from gaia_layers import gaia_node_spec

        spec = gaia_node_spec(mode="universe")
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "physical",
            spec["group"],
            icon=spec["icon"],
            description=spec["description"],
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "offline")
        ent.color = "#43e65a"
        self.entities[ent.id] = ent

    def _seed_atlas_entity(self) -> None:
        """Physical sensor map surface over GAIA live relays."""
        if "atlas" in self.entities:
            return
        from atlas_layers import atlas_node_spec

        spec = atlas_node_spec(mode="universe")
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "physical",
            spec["group"],
            icon=spec["icon"],
            description=spec["description"],
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "offline")
        ent.color = "#3dd6c6"
        self.entities[ent.id] = ent

    def _seed_metis_entity(self) -> None:
        if "metis" in self.entities:
            return
        from metis_layers import metis_node_spec

        met_spec = metis_node_spec(mode="universe")
        met = EcosystemEntity(
            met_spec["id"],
            met_spec["label"],
            "cognition",
            met_spec["group"],
            icon=met_spec["icon"],
            description=met_spec["description"],
        )
        met.position = met_spec["position"]
        met.url = met_spec["url"]
        met.metrics = dict(met_spec.get("metrics") or {})
        met.status = met_spec.get("status", "offline")
        met.color = "#9b59ff"
        self.entities[met.id] = met

    def _seed_skopos_entity(self) -> None:
        if "skopos" in self.entities:
            return
        from skopos_layers import skopos_node_spec

        spec = skopos_node_spec(mode="universe")
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "observability",
            spec["group"],
            icon=spec["icon"],
            description=spec["description"],
        )
        ent.position = spec["position"]
        ent.url = spec["url"]
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "offline")
        ent.color = "#00e5cc"
        self.entities[ent.id] = ent

    def _seed_oracle_family(self) -> None:
        """Seed the 17-oracle family + Platon's UMBRAL cave as always-present nodes.

        These render regardless of deployment (the family is the showcase). Live
        status/metrics are filled later by _poll_oracle_family and federation
        discovery; until an endpoint answers they stay 'declared' — no fake data.
        """
        from oracle_family import CAVE, ORACLE_FAMILY, oracle_node_id, ring_position, scene_url

        n = len(ORACLE_FAMILY)
        for i, o in enumerate(ORACLE_FAMILY):
            eid = oracle_node_id(o["slug"])
            ent = EcosystemEntity(eid, o["name"], "oracle-family", group="oracle", icon="oracle",
                                  description=f"{o['skill']} · caps: {', '.join(o['caps'])}")
            ent.position = ring_position(i, n)
            ent.color = o["accent"]
            ent.url = scene_url(o["slug"])
            ent.parent_id = "federation"
            ent.status = "idle"  # 'active' once a live endpoint answers; metrics.live carries the truth
            ent.metrics = {
                "capability_count": len(o["caps"]),
                "tests": o["tests"],
                "deployed": 1 if o.get("live_url") else 0,
                "live": 0,
            }
            self.entities[eid] = ent

        cave = EcosystemEntity(CAVE["id"], CAVE["name"], "oracle-cave", group="oracle",
                               icon="cave", description=CAVE["skill"])
        plat = self.entities.get(oracle_node_id(CAVE["parent_slug"]))
        if plat:
            cave.position = {"x": plat.position["x"] + 1.6,
                             "y": plat.position["y"] - 1.1,
                             "z": plat.position["z"] + 1.2}
        cave.color = CAVE["accent"]
        cave.url = CAVE["url"]
        cave.parent_id = oracle_node_id(CAVE["parent_slug"])
        cave.status = "idle"
        cave.metrics = {"live": 0}
        self.entities[CAVE["id"]] = cave

    def sync_factory_catalog(
        self,
        app_url: str | None = None,
        *,
        timeout: float | None = None,
    ) -> int:
        """Import shipped products from Factory API as product planets (idempotent)."""
        from factory_products import resolve_factory_catalog

        url = app_url or os.environ.get("AICOM_API_URL", "http://127.0.0.1:9081")
        catalog, authoritative = resolve_factory_catalog(url, timeout=timeout)
        if catalog is None:
            print(f"[Universe] Factory catalog sync skipped — API unreachable ({url})")
            return 0

        catalog_ids = {str(p.get("id") or "") for p in catalog if p.get("id")}

        # Drop product nodes removed from Factory only on authoritative catalog reads.
        if authoritative:
            for eid in list(self.entities.keys()):
                ent = self.entities[eid]
                if ent.group == "product" and eid not in catalog_ids:
                    del self.entities[eid]
            if catalog_ids:
                self.products = [n for n in self.products if str(n.get("id") or "") in catalog_ids]
            elif len(self.products) > _MAX_PRODUCT_ENTITIES:
                self.products = self.products[-_MAX_PRODUCT_ENTITIES:]

        added = 0
        for p in catalog:
            pid = str(p.get("id") or "")
            if not pid or pid in self.entities:
                continue
            self.materialize_product({
                "id": pid,
                "name": p.get("name"),
                "category": p.get("category"),
                "description": p.get("description") or p.get("tagline"),
                "version": p.get("version"),
            })
            added += 1

        if len(self.entities) > _MAX_PRODUCT_ENTITIES + 20:
            product_eids = [eid for eid, ent in self.entities.items() if ent.group == "product"]
            if len(product_eids) > _MAX_PRODUCT_ENTITIES:
                for eid in product_eids[: len(product_eids) - _MAX_PRODUCT_ENTITIES]:
                    self.entities.pop(eid, None)
                self.products = self.products[-_MAX_PRODUCT_ENTITIES:]

        factory = self.entities.get("factory")
        if factory:
            factory.metrics["products"] = len(self.products)
        return added

    def materialize_product(self, product_data: dict) -> EcosystemEntity:
        pid = str(product_data.get("id") or f"product_{self.tick}_{len(self.products)}")
        name = str(product_data.get("name") or f"Product-{self.tick}")
        ptype = str(product_data.get("type") or product_data.get("category") or "fullstack-app")
        entity = EcosystemEntity(pid, name, ptype, "product", icon="planet")
        entity.parent_id = "factory"
        entity.metrics = {
            "version": product_data.get("version", "0.1.0"),
            "price_usdt": product_data.get("price", 0),
            "invocations": 0,
        }
        entity.status = "active"
        fp = self.entities.get("factory")
        if fp:
            entity.position = {
                "x": fp.position["x"] + 2,
                "y": fp.position["y"] + 1,
                "z": fp.position["z"],
            }
        self.entities[pid] = entity
        node = entity.to_node()
        if not any(str(p.get("id") or "") == pid for p in self.products):
            self.products.append(node)
        self._pending_materializations.append(
            {
                "type": "product_materialized",
                "id": pid,
                "name": name,
                "category": ptype,
                "ts": datetime.now(timezone.utc).isoformat(),
                "position": entity.position,
                "color": entity.color,
            }
        )
        return entity

    def get_pending_materializations(self) -> list[dict]:
        events = list(self._pending_materializations)
        self._pending_materializations.clear()
        return events

    def _family_id_for_node(self, n: dict) -> str | None:
        """Map a discovered federation peer onto a node the map already draws.

        Family oracles and first-party satellites (MOMUS, GAIA, …) must enrich
        the canonical entity — a second violet oracle for MOMUS is a duplicate.
        """
        from canonical_peers import canonical_node_id_for_peer

        return canonical_node_id_for_peer(n)

    def _poll_oracle_family(self) -> None:
        """Throttled liveness poll of deployed oracles + the cave. A node flips to
        'live' (with a few real metrics) only when /api/health answers with
        status=ok; otherwise it reverts to idle. Polls the remote oracle host
        (oracles.modelmarket.dev by default), not loopback."""
        import urllib.request

        from oracle_family import CAVE, ORACLE_FAMILY, oracle_node_id

        targets = [(oracle_node_id(o["slug"]), o.get("live_url")) for o in ORACLE_FAMILY]
        targets.append((CAVE["id"], CAVE.get("live_url")))
        for eid, base in targets:
            ent = self.entities.get(eid)
            if ent is None or not base:
                continue
            health: dict | None = None
            try:
                req = urllib.request.Request(
                    f"{base.rstrip('/')}/api/health",
                    headers={"User-Agent": "alien-monitor", "Accept": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=3.0) as resp:  # noqa: S310
                    if getattr(resp, "status", 200) == 200:
                        body = json.loads(resp.read(65536).decode("utf-8", "replace"))
                        if isinstance(body, dict) and body.get("status") == "ok":
                            health = body
            except Exception:
                health = None
            if isinstance(health, dict):
                ent.status = "active"
                live: dict[str, int | float] = {"live": 1}
                for k in ("tick", "viewers", "capabilities", "kappa", "order_parameter"):
                    v = health.get(k)
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        live[k] = v
                caps = health.get("capabilities")
                if isinstance(caps, int) and "capabilities" not in live:
                    live["capabilities"] = caps
                ent.metrics = {**ent.metrics, **live}
            else:
                ent.metrics["live"] = 0

    def _apply_discovery(self, hub_url: str) -> None:
        """Hub-driven federation discovery in UNI mode — render peers (e.g. Platon)
        as oracle entities hydrated with live /api/health metrics. Defensive: any
        failure leaves the universe untouched."""
        if not hub_url:
            return
        try:
            from hub_discovery import discover_cached_sync
            # UNI is a local sim; allow loopback/private peers (spawned hubs etc.).
            disc = discover_cached_sync(hub_url, allow_private=True)
        except Exception:
            return

        self._discovery_events = list(disc.get("events") or [])
        # Edges discovery computed itself — hub-to-hub, and "we both know this node". They
        # connect two entities that already exist, so nothing else in this file would ever
        # produce them: `get_topology_links` builds from the entity table, and an edge
        # between two known nodes is not derivable from either one alone. Dropping them left
        # the federation looking like a star when it is a mesh.
        self._discovery_links = [
            dict(link) for link in (disc.get("links") or [])
            if isinstance(link, dict) and link.get("source") and link.get("target")
        ]
        # Every URL the map ALREADY draws, mapped to the node that draws it. This is the
        # rule; the host/name tables in `canonical_peers` are only the fallback for peers
        # whose URL is spelled differently from the node's own.
        #
        # It has to be derived from the graph rather than listed, because a list needs a
        # human edit every time a satellite gets a seed — and the requirement is the other
        # way round: adding a seed must never add a planet. ARGUS, DIOSCURI, HELIOS and
        # WARDEN do not publish a well-known today, so they cannot duplicate yet; the day
        # one of them does, nothing should have to be remembered.
        drawn_by_url: dict[str, str] = {}
        for eid, existing in self.entities.items():
            if getattr(existing, "type", "") == "federation":
                continue  # a discovered node is not something to fold onto
            url = _norm_peer_url(getattr(existing, "url", "") or "")
            if url:
                drawn_by_url.setdefault(url, eid)

        folded: dict[str, str] = {}
        current: set[str] = set()
        for n in disc.get("nodes", []):
            nid = n.get("id")
            if not nid:
                continue
            # UNI is the sealed universe. An unapproved stranger that announced itself to the
            # live hub has no business appearing in the simulation — and without this filter it
            # arrived styled exactly like a trusted oracle peer, because _apply_discovery gives
            # every unmatched node group="oracle". Strangers belong on the LIVE map only.
            if n.get("group") == "pending_hub" or n.get("status") == "pending":
                continue
            # If this peer is something the map already draws, enrich that node instead of
            # minting a duplicate. URL first — it needs no table and covers every satellite,
            # present and future — then the spelling fallback.
            # Host/name tables first so hunt HTTPS cannot be stolen by Competing
            # Lab Hub when an old env still pointed both suns at the same URL.
            # URL fallback still covers a satellite the tables have never listed.
            fam_id = self._family_id_for_node(n) \
                or drawn_by_url.get(_norm_peer_url(str(n.get("url") or "")))
            if fam_id:
                folded[nid] = fam_id
                if fam_id in self.entities:
                    fam = self.entities[fam_id]
                    fam.status = n.get("status") or "active"
                    fam.metrics = {**fam.metrics, **(n.get("metrics") or {}), "live": 1}
                # Legacy hub peers (e.g. "Platon Shadow Oracle") map onto the
                # family ring — never materialize them as extra federation nodes.
                continue
            ent = self.entities.get(nid)
            if ent is not None and getattr(ent, "type", "") != "federation":
                # id collides with a non-discovery entity (core/product/agent) —
                # never clobber a real node with peer-supplied data.
                continue
            # Honour the node's OWN group. This used to hardcode oracle/oracle/#a64dff for
            # every discovered node, so a peer that is itself a HUB — with peers of its own
            # hanging off it — arrived on the map dressed as an oracle, indistinguishable
            # from a capability service. Emitting a new group upstream was invisible until
            # this line stopped overwriting it.
            group = str(n.get("group") or "oracle")
            icon = str(n.get("icon") or ("hub" if group == "peer_hub" else ("network" if group.startswith("peer_hub") else "oracle")))
            if ent is None:
                ent = EcosystemEntity(
                    nid, str(n.get("label") or nid), "federation", group=group,
                    description=str(n.get("description") or ""), icon=icon,
                )
                self.entities[nid] = ent
            else:
                ent.group = group
                ent.icon = icon
            if n.get("role") or group == "peer_hub":
                ent.role = str(n.get("role") or "hub")
            ent.metrics = {k: v for k, v in (n.get("metrics") or {}).items()}
            ent.status = n.get("status", "active")
            ent.url = n.get("url")
            # The default used to be oracle violet, so every discovered service that was
            # not a hub arrived purple — three unrelated providers under one hub identical,
            # and a second operator's satellites the same purple again. Colour now says what
            # a thing does, from the same table the LIVE path stamps. See node_palette.
            from node_palette import color_for

            ent.color = n.get("color") or color_for(
                group, n.get("categories") or (), role=str(n.get("role") or ""), node_id=nid
            )
            # A hub's own peers hang off that hub, not off our federation node — that is the
            # whole shape the second hop exists to show.
            parent = str(n.get("parent_id") or "federation")
            parent = folded.get(parent, parent)
            fam_parent = self._family_id_for_node({"id": parent, "label": parent})
            if fam_parent and fam_parent in self.entities:
                parent = fam_parent
            ent.parent_id = parent
            if n.get("position"):
                ent.position = n["position"]
            current.add(nid)

        if folded:
            for link in self._discovery_links:
                link["source"] = folded.get(str(link.get("source")), link.get("source"))
                link["target"] = folded.get(str(link.get("target")), link.get("target"))
            self._discovery_links = [
                link for link in self._discovery_links
                if link.get("source") != link.get("target")
            ]

        # Moons of a folded sun were placed around the discovery clone. Pull them
        # onto the seeded planet so the operator can actually see that ecosystem.
        from collections import defaultdict

        from ecosystem_layout import peer_hub_child_position

        moons: dict[str, list] = defaultdict(list)
        for eid in current:
            ent = self.entities.get(eid)
            if ent is None or getattr(ent, "group", "") != "peer_hub_node":
                continue
            pid = str(getattr(ent, "parent_id", "") or "")
            if pid in folded:
                pid = folded[pid]
                ent.parent_id = pid
            moons[pid].append(ent)
        for pid, kids in moons.items():
            parent = self.entities.get(pid)
            if parent is None or not getattr(parent, "position", None):
                continue
            for index, child in enumerate(kids):
                child.position = peer_hub_child_position(parent.position, index, len(kids))

        # Prune entities that were discovered before but are no longer peers.
        for stale in self._discovered_ids - current:
            ent = self.entities.get(stale)
            if ent is not None and getattr(ent, "type", "") == "federation":
                self.entities.pop(stale, None)
        self._discovered_ids = current

    def _ensure_topology_seeded(self) -> None:
        """Graph skeleton must exist even when local Anvil bootstrap fails."""
        if not self.entities or "hub" not in self.entities:
            self.seed_entities()
            return
        if not any(eid.startswith("oracle-") for eid in self.entities):
            self._seed_oracle_family()
        self._seed_metis_entity()
        self._seed_skopos_entity()
        self._seed_gaia_entity()
        self._seed_atlas_entity()
        self._seed_hephaestus_entity()
        self._seed_momus_entity()
        self._seed_warden_entity()
        self._seed_treasury_entity()
        self._seed_logos_entity()
        self._seed_bridges_entity()
        self._seed_themis_entity()
        self._seed_basanos_entity()
        self._seed_settlement_entity()
        self._seed_competing_lab_entities()

    def tick_universe(self) -> dict:
        from universe_layers import (
            apply_layers_to_entities,
            build_universe_summary,
            fetch_layers_sync,
            sync_agent_entities,
        )

        self._ensure_topology_seeded()
        self.tick += 1

        contracts = {
            "escrow_evm": self.evm_escrow_address,
            "nft_evm": self.evm_nft_address,
            "lottery_evm": self.evm_lottery_address,
            "lottery_solana": self.solana_lottery_program_id,
            "payment_recipient": self.payment_recipient,
        }
        layers = fetch_layers_sync(
            evm_rpc=self.evm_rpc,
            contracts=contracts,
            chain_label=self.chain_label,
        )
        self._last_layers = layers

        apply_layers_to_entities(self.entities, layers)
        sync_agent_entities(self.entities, layers.get("agents") or [], self.agents)
        from lottery_layers import apply_lottery_entity

        apply_lottery_entity(
            self.entities,
            hub_hints=layers.get("hub_hints"),
            mesh_stats=layers.get("mesh"),
        )
        self._apply_discovery((layers.get("urls") or {}).get("hub", ""))
        if self.tick == 1 or self.tick % 20 == 0:
            self._poll_oracle_family()
        # Bootstrap already synced catalog; tick-time sync uses a short timeout because
        # GET /api/products can take 20–40s on a cold Factory scan.
        if self.tick > 1 and self.tick % max(1, self._factory_sync_every_ticks) == 0:
            tick_timeout = float(os.environ.get("ALIEN_FACTORY_TICK_TIMEOUT", "5"))
            self.sync_factory_catalog(timeout=tick_timeout)

        self._ensure_anvil_alive()

        if self.blockchain_ready:
            self._recycle_anvil_if_oversized()
            self._fetch_chain_state()
            from acex_uni import acex_metrics_for_monitor, tick_acex_trades

            tick_acex_trades(self)
            acex_ent = self.entities.get("acex")
            if acex_ent is not None:
                acex_ent.metrics.update(acex_metrics_for_monitor(self))
                acex_ent.status = "active" if acex_ent.metrics.get("pools_active") else "idle"

        onchain_activity = [
            {
                "id": tx["id"],
                "ts": tx["ts"],
                "agent": tx.get("from", "")[:12],
                "action": tx.get("action", "tx"),
                "target": tx.get("target", ""),
                "amount": tx.get("amount", 0),
                "token": tx.get("token", "ETH"),
                "onchain": True,
            }
            for tx in self.transactions[-20:]
        ]
        hub_events = layers.get("events") or []
        from live_lottery_feed import lottery_events_if_fresh

        lot_events = lottery_events_if_fresh()
        all_activity = sorted(
            onchain_activity + hub_events + self._discovery_events + lot_events,
            key=lambda x: x.get("ts", ""),
            reverse=True,
        )[:20]

        # Scenario engine tick — drives autonomous evolution
        scenario_output = self._tick_scenario()

        # Merge scenario events into activity feed
        scenario_events = scenario_output.get("events") or []
        if scenario_events:
            all_activity = sorted(
                all_activity + scenario_events,
                key=lambda x: x.get("ts", ""),
                reverse=True,
            )[:30]

        summary = build_universe_summary(
            tick=self.tick,
            layers=layers,
            agents_count=len(self.agents),
            products_count=len(self.products),
            onchain_tx_count=len(self.transactions),
        )
        summary["scenario_phase"] = scenario_output.get("phase", "BOOTSTRAP")

        from factory_products import collapse_graph_products

        raw_nodes = [ent.to_node() for ent in self.entities.values()]
        raw_links = self.get_topology_links()
        graph_nodes, graph_links = collapse_graph_products(raw_nodes, raw_links)
        # One owner for "is this coordinate taken". Positions here come from the hardcoded
        # table, a dozen layer modules and hub discovery, none of which can see the others —
        # so overlap was nobody's job until this line. Runs last, over everything, and only
        # moves a node that genuinely collides.
        from space_map import enforce_spacing

        enforce_spacing(graph_nodes)

        # Every satellite status layer, from the one place that owns the list — the same
        # call the REST route and the connect-time snapshot make, so all three paths now
        # hydrate the graph identically. They did not: this one applied sixteen layers, the
        # snapshot twelve, the route four.
        from satellite_overlays import apply_live_layers

        # The ticking broadcaster is what keeps the shared cache warm, so it never reads it.
        apply_live_layers(
            graph_nodes,
            tick=self.tick,
            escrow=getattr(self, "evm_escrow_address", "") or "",
            rpc=getattr(self, "evm_rpc", "") or "",
            hub_payload=layers.get("hub"),
            allow_cache=False,
        )

        return {
            "tick": self.tick,
            "ts": datetime.now(timezone.utc).isoformat(),
            "nodes": graph_nodes,
            "links": graph_links,
            "events": all_activity,
            "transactions": self.transactions[-20:],
            "channels": [],
            "summary": summary,
            "materializations": self.get_pending_materializations(),
            "chain_analytics": self.chain_analytics,
            "layer_errors": layers.get("errors") or [],
            "scenario": {
                "phase": scenario_output["phase"],
                "phase_progress": scenario_output["phase_progress"],
                "phase_color": scenario_output["phase_color"],
                "tick_count": scenario_output["tick_count"],
                "funding_total": scenario_output["funding_total"],
                "hub_count": scenario_output["hub_count"],
                "buyer_rounds": scenario_output["buyer_rounds"],
            },
            "funding_events": [
                e for e in scenario_events if e.get("type") == "funding_stream"
            ],
        }

    def _tick_scenario(self) -> dict:
        if self._scenario_engine is None:
            from universe_layers import layer_urls
            from universe_scenario import UniverseScenarioEngine
            self._scenario_engine = UniverseScenarioEngine(hub_url=layer_urls()["hub"])
        return self._scenario_engine.tick(self)

    def get_topology_links(self) -> list[dict]:
        from lottery_layers import lottery_financial_links
        from argus_layers import argus_topology_links
        from oracle_family import CAVE, ORACLE_FAMILY, oracle_node_id

        links = [
            {"source": "hub", "target": "factory", "label": "Capability catalog"},
            {"source": "hub", "target": "mesh", "label": "Agent discovery"},
            {"source": "hub", "target": "acex", "label": "Pricing feed"},
            {"source": "hub", "target": "evm_escrow", "label": "Channel settlement"},
            {"source": "hub", "target": "solana_escrow", "label": "Channel settlement"},
            {"source": "hub", "target": "nft_contract", "label": "NFT entitlements"},
            {"source": "hub", "target": "plugins", "label": "Plugin hooks"},
            {"source": "hub", "target": "federation", "label": "Peer crawl"},
            {"source": "hub", "target": "widget", "label": "Search API"},
            {"source": "factory", "target": "mesh", "label": "Orchestration"},
            {"source": "evm_escrow", "target": "ethereum", "label": "EVM RPC"},
            {"source": "solana_escrow", "target": "solana", "label": "Solana RPC"},
            {"source": "acex", "target": "factory", "label": "Capital data"},
        ]
        oracle_draw_ids = [
            oracle_node_id(o["slug"])
            for o in ORACLE_FAMILY
            if o["slug"] in ("platon", "chronos", "lumen")
            and oracle_node_id(o["slug"]) in self.entities
        ]
        if not oracle_draw_ids:
            oracle_draw_ids = ["federation"] if "federation" in self.entities else []
        links.extend(lottery_financial_links(oracle_ids=oracle_draw_ids))
        if "argus" in self.entities:
            oracle_target = oracle_node_id("lumen")
            if oracle_target not in self.entities:
                oracle_target = "federation"
            links.extend(argus_topology_links(oracle_target=oracle_target))
        if "factory_agents" in self.entities:
            from factory_agents import factory_agents_topology_links

            links.extend(
                e
                for e in factory_agents_topology_links()
                if e["source"] in self.entities and e["target"] in self.entities
            )
        if "dioscuri" in self.entities:
            from dioscuri_layers import dioscuri_topology_links

            links.extend(dioscuri_topology_links())
        if "helios" in self.entities:
            from helios_layers import helios_topology_links

            links.extend(helios_topology_links())
        if "metis" in self.entities:
            from metis_layers import metis_topology_links

            links.extend(metis_topology_links())
        if "skopos" in self.entities:
            from skopos_layers import skopos_topology_links

            links.extend(skopos_topology_links())
        if "gaia" in self.entities:
            from gaia_layers import gaia_topology_links

            links.extend(gaia_topology_links())
        if "atlas" in self.entities:
            from atlas_layers import atlas_topology_links

            links.extend(atlas_topology_links())
        if "hephaestus" in self.entities:
            from hephaestus_layers import hephaestus_topology_links

            links.extend(hephaestus_topology_links())
        if "warden" in self.entities:
            from warden_layers import warden_topology_links

            for link in warden_topology_links():
                if link["source"] in self.entities and link["target"] in self.entities:
                    links.append(dict(link))
        if "momus" in self.entities or "treasury" in self.entities:
            from momus_layers import momus_topology_links

            links.extend(momus_topology_links())
        if "logos" in self.entities:
            from logos_layers import logos_topology_links

            links.extend(logos_topology_links())
        if "bridges" in self.entities:
            # Without this the node is seeded but floats unconnected in UNI mode, and the one
            # claim it exists to make — that this is a billed channel INTO the hub, the same
            # category as the mesh — is exactly the thing that goes missing. Seeding the entity
            # and drawing its edge are two separate wirings; the first one alone looks done.
            from bridges_layers import bridges_topology_links

            links.extend(bridges_topology_links())
        if "themis" in self.entities:
            from themis_layers import themis_topology_links

            links.extend(themis_topology_links())
        if "basanos" in self.entities:
            from basanos_layers import basanos_topology_links

            links.extend(basanos_topology_links())
        if "settlement" in self.entities:
            from settlement_layers import settlement_topology_links

            links.extend(settlement_topology_links())
        if any(eid in self.entities for eid in ("competing_hub", "signal_hunt_hub", "signal_hunt", "use_cases")):
            from competing_lab_layers import competing_lab_topology_links

            links.extend(competing_lab_topology_links())
        for prod in self.products:
            links.append({"source": "factory", "target": prod["id"], "label": "created"})
        for ag in self.agents:
            links.append({"source": "mesh", "target": ag["id"], "label": "registered"})
        for link in getattr(self, "_discovery_links", []):
            # Only between nodes that made it onto the map: a link to a peer that failed its
            # own build is an edge to nothing, and the frontend resolves endpoints by id.
            if link["source"] in self.entities and link["target"] in self.entities:
                if link.get("kind") == "shared" or link.get("label") == "its peer":
                    links.append(dict(link))
        for did in self._discovered_ids:
            ent = self.entities.get(did)
            parent = str(getattr(ent, "parent_id", "") or "federation")
            # Seeding an entity and drawing its edge are two separate wirings, and the first
            # one alone looks done: a hub's own peers were entities with a parent_id nothing
            # read, so they floated unconnected. Edge to the parent when it is on the map,
            # otherwise to our federation node.
            if parent != "federation" and parent in self.entities:
                links.append({"source": parent, "target": did, "label": "its peer"})
            else:
                links.append({"source": "federation", "target": did, "label": "Federation peer"})
        # Oracle family — always linked from Federation; the cave hangs off Platon.

        for o in ORACLE_FAMILY:
            oid = oracle_node_id(o["slug"])
            if oid in self.entities:
                links.append({"source": "federation", "target": oid, "label": "oracle family"})
        plat_id = oracle_node_id(CAVE["parent_slug"])
        if plat_id in self.entities and CAVE["id"] in self.entities:
            links.append({"source": plat_id, "target": CAVE["id"], "label": "live product"})
        return links
