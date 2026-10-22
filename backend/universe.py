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
import stat
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from universe_anvil import AnvilStateMixin
from universe_deploy import ContractDeployMixin
from universe_seeding import EntitySeedingMixin
from universe_discovery import DiscoveryMixin
from universe_links import TopologyLinksMixin
from universe_entities import (  # noqa: F401 - re-exported
    ANVIL_DEPLOYER_KEY,
    _MONITOR_ROOT,
    resolve_aicom_root,
    resolve_evm_contracts_dir,
    resolve_lottery_contracts_dir,
    resolve_acex_evm_dir,
    resolve_solana_contracts_dir,
    _MAX_PRODUCT_ENTITIES,
    _norm_peer_url,
    EcosystemEntity,
    foundry_anvil_tmp_dir,
    _path_mtime,
    _path_bytes,
    _unlink_path,
    sweep_foundry_anvil_tmp,
)


def _write_atomic(path: Path, text: str) -> None:
    """Replace ``path`` in one rename, so a crash mid-write leaves the old file, not a torn one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        if path.exists():
            os.chmod(tmp, stat.S_IMODE(path.stat().st_mode))
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _universe_solana_enabled() -> bool:
    """Embedded solana-test-validator for UNI Solana lottery deploy + solana graph node."""
    return os.environ.get("ALIEN_UNIVERSE_ENABLE_SOLANA", "0").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


AICOM_ROOT = resolve_aicom_root()

# Poll Factory catalog every N ticks (~60s at 1.5s/tick) — not every broadcast.
_FACTORY_SYNC_EVERY_TICKS = max(1, int(os.environ.get("ALIEN_FACTORY_SYNC_TICKS", "40")))


#: Colour per discovered group. A federated hub and a capability service are different kinds
#: of thing and must not share a colour — the map is how an operator tells them apart.
_DISCOVERED_COLORS: dict[str, str] = {
    "oracle": "#a64dff",
    "peer_hub": "#38e0ff",
    "peer_hub_node": "#7fd4ff",
    "pending_hub": "#ffcc4d",
}


# Back-compat alias for tests / imports
VirtualEntity = EcosystemEntity


class VirtualUniverse(
    AnvilStateMixin, ContractDeployMixin, EntitySeedingMixin, DiscoveryMixin, TopologyLinksMixin,
):
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

    def start_blockchain(self) -> bool:
        with self._bootstrap_lock:
            return self._start_blockchain_locked()

    def _start_blockchain_locked(self) -> bool:
        started = False
        self._kill_chain_orphans()
        if shutil.which("anvil"):
            with contextlib.suppress(Exception):
                self._quarantine_unreadable_anvil_state()
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
                # `--state` alone writes the chain to disk only on a clean exit, and a container
                # stop that outlasts its grace period kills Anvil first. Everything deployed
                # since the last clean exit was then gone on the next start, so the ACEX stack
                # came back at new addresses after every restart and every consumer pinned to
                # the old ones (UNI hub, ARGUS-UNI) pointed at empty code. Dump on a timer.
                interval = (os.environ.get("ALIEN_ANVIL_STATE_INTERVAL_S", "30") or "0").strip()
                if interval.isdigit() and int(interval) > 0:
                    anvil_args += ["--state-interval", interval]
                # Without it Anvil keeps a state per mined block in memory: ~65 MB/min on the UNI
                # chain at --block-time 2 with no transactions at all, 2 GB in half an hour, and
                # factory-vps went into a host-wide OOM on 2026-10-22 (14 kills the week before).
                # The flag must stay bare: on anvil 1.3.1 `--prune-history N` (0, 16, 64 tried) still
                # grew linearly, the bare form held RSS flat at ~155 MB on the same state. Queries
                # against old block STATE were already refused; blocks, logs and code are unaffected.
                if os.environ.get("ALIEN_ANVIL_PRUNE_HISTORY", "1") != "0":
                    anvil_args.append("--prune-history")
                if os.environ.get("ALIEN_ANVIL_VERBOSE", "0") != "1":
                    anvil_args.append("--silent")
                # stderr went to /dev/null, so "failed to parse json file" read as a 90 s
                # timeout for 14 hours. Keep it, one start per file.
                anvil_log_path = self._anvil_state_dir().parent / "anvil.log"
                anvil_log = None
                if os.environ.get("ALIEN_ANVIL_VERBOSE") != "1":
                    with contextlib.suppress(OSError):
                        anvil_log = anvil_log_path.open("wb")
                self.anvil_proc = subprocess.Popen(
                    anvil_args,
                    stdout=subprocess.DEVNULL,
                    stderr=None if os.environ.get("ALIEN_ANVIL_VERBOSE") == "1" else (
                        anvil_log if anvil_log is not None else subprocess.DEVNULL),
                )
                if anvil_log is not None:
                    anvil_log.close()  # the child holds its own descriptor
                # 20s was a guess that held only while the state was small. Anvil answers
                # nothing until it has parsed the whole state file, so the budget has to scale
                # with what is on disk — and the failure message has to say what it was
                # waiting for, or the next person reads "timeout" and looks at the network.
                ready_budget = int(os.environ.get("ALIEN_ANVIL_READY_TIMEOUT_S", "90") or 90)
                state_mb = self._anvil_state_bytes() / 1_048_576
                if not self._wait_for_anvil_rpc(timeout_sec=ready_budget):
                    detail = (f"anvil rpc timeout after {ready_budget}s "
                              f"(loading {state_mb:.0f}MB of state)")
                    if self.anvil_proc.poll() is not None:
                        tail = ""
                        with contextlib.suppress(OSError):
                            tail = anvil_log_path.read_text(errors="replace").strip()[-300:]
                        detail = (f"anvil exited with code {self.anvil_proc.returncode}"
                                  + (f": {tail}" if tail else ""))
                    print(f"[Universe] {detail}")
                    self._last_deploy_error = detail
                    started = False
                else:
                    started = True
                    print("[Universe] EVM node online (Anvil, chain 31337)")
                    with contextlib.suppress(Exception):
                        self._keep_last_good_anvil_state()
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
                    # anvil writes its whole state on SIGTERM; 5 s killed it mid-dump.
                    proc.wait(timeout=30 if proc is self.anvil_proc else 5)
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
        _write_atomic(self.data_dir / "universe_config.json", json.dumps(config, indent=2))
        self._write_hub_env_snippet()

    def tick_universe(self) -> dict:
        from universe_layers import (
            apply_buyer_health,
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
            chain=layers.get("chain"),
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
        # Sweep Foundry dumps + recycle oversized --state even if the chain is
        # currently down: the dumps accumulate either way, and a huge state.json
        # is why the chain cannot come back.
        self._recycle_anvil_if_oversized()

        if self.blockchain_ready:
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
        apply_buyer_health(summary, scenario_output)

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
