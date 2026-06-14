"""
Universe runtime — local chain + live polls from deployed AIMarket layers.

UNI mode does not simulate metrics: Hub, Mesh, Factory, Prometheus and the
embedded EVM/Solana nodes are read from real endpoints and RPC.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
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


AICOM_ROOT = resolve_aicom_root()

# Poll Factory catalog every N ticks (~60s at 1.5s/tick) — not every broadcast.
_FACTORY_SYNC_EVERY_TICKS = max(1, int(os.environ.get("ALIEN_FACTORY_SYNC_TICKS", "40")))
_MAX_PRODUCT_ENTITIES = max(50, int(os.environ.get("ALIEN_MAX_PRODUCT_ENTITIES", "400")))


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

    def to_node(self) -> dict:
        return {
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


# Back-compat alias for tests / imports
VirtualEntity = EcosystemEntity


class VirtualUniverse:
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or (Path(__file__).resolve().parent.parent / "data" / "universe")
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.anvil_proc: Optional[subprocess.Popen] = None
        self.solana_proc: Optional[subprocess.Popen] = None

        self.evm_usdt_address: Optional[str] = None
        self.evm_escrow_address: Optional[str] = None
        self.evm_nft_address: Optional[str] = None
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
        self._discovery_events: list[dict] = []
        self._scenario_engine = None
        self._factory_sync_every_ticks = int(os.environ.get("ALIEN_FACTORY_SYNC_TICKS", "40"))
        self._last_deploy_error: str | None = None
        self._bootstrap_notes: list[str] = []

        self.evm_rpc = (os.environ.get("ALIEN_UNIVERSE_EVM_RPC") or "http://127.0.0.1:8545").rstrip("/")
        self.solana_rpc = (os.environ.get("ALIEN_UNIVERSE_SOLANA_RPC") or "http://127.0.0.1:8899").rstrip("/")
        self.chain_label = os.environ.get("ALIEN_UNIVERSE_CHAIN_LABEL", "EVM Network")

    def _anvil_state_dir(self) -> Path:
        raw = (os.environ.get("ALIEN_UNIVERSE_ANVIL_STATE_DIR") or "").strip()
        state_dir = Path(raw) if raw else (self.data_dir / "anvil-state")
        state_dir.mkdir(parents=True, exist_ok=True)
        return state_dir

    def _reset_anvil_state(self) -> None:
        state_dir = self._anvil_state_dir()
        for child in state_dir.iterdir():
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
        self._bootstrap_notes.append("anvil state reset")

    def start_blockchain(self) -> bool:
        started = False
        if shutil.which("anvil"):
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
                if not self._wait_for_anvil_rpc(timeout_sec=20):
                    print("[Universe] Anvil RPC not ready in time")
                    self._last_deploy_error = "anvil rpc timeout"
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

        if shutil.which("solana-test-validator"):
            try:
                self.solana_proc = subprocess.Popen(
                    ["solana-test-validator", "--reset", "--quiet", "--rpc-port", "8899"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                time.sleep(3)
                print("[Universe] Solana node online")
            except Exception as exc:
                print(f"[Universe] Solana start failed: {exc}")

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

    def _all_contracts_verified(self) -> bool:
        return (
            self._contract_has_code(self.evm_usdt_address)
            and self._contract_has_code(self.evm_escrow_address)
            and self._contract_has_code(self.evm_nft_address)
        )

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
        self.payment_recipient = data.get("payment_recipient") or self.payment_recipient
        if data.get("evm_rpc"):
            self.evm_rpc = str(data["evm_rpc"]).rstrip("/")
        return True

    def bootstrap(self) -> dict:
        """Start Anvil, deploy contracts if needed, seed graph. Safe on container restart."""
        self.running = True
        self._bootstrap_notes = []
        self._last_deploy_error = None

        if not self.start_blockchain():
            return {
                "ok": False,
                "blockchain_ready": False,
                "error": self._last_deploy_error or "blockchain_start_failed",
            }

        self._load_config_from_disk()
        if self._all_contracts_verified():
            note = "Contracts already on chain — skip redeploy"
            print(f"[Universe] {note}")
            self._bootstrap_notes.append(note)
        else:
            print("[Universe] Deploying FakeUSDT + Escrow + NFT on Anvil…")
            self.deploy_contracts()
            if not self._all_contracts_verified() and "Insufficient funds" in (self._last_deploy_error or ""):
                print("[Universe] Resetting Anvil state (stale wallet) and redeploying…")
                self._reset_anvil_state()
                self.stop_blockchain()
                if self.start_blockchain():
                    self.deploy_contracts()

        if not self.entities:
            self.seed_entities()

        if self._scenario_engine is None:
            hub_url = os.environ.get("ALIEN_UNIVERSE_HUB_URL") or os.environ.get("HUB_URL") or "http://127.0.0.1:9083"
            from universe_scenario import UniverseScenarioEngine
            self._scenario_engine = UniverseScenarioEngine(hub_url=hub_url)

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

    def _parse_broadcast_address(self, script: str, evm_dir: Path | None = None) -> str | None:
        root = evm_dir or resolve_evm_contracts_dir()
        script_name = Path(script).name
        broadcast_dirs = [
            root / "broadcast" / script / "31337",
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
            "evm_usdt": self.evm_usdt_address,
            "evm_escrow": self.evm_escrow_address,
            "evm_nft": self.evm_nft_address,
            "payment_recipient": self.payment_recipient,
            "chain_id": 31337,
            "chain_label": self.chain_label,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        (self.data_dir / "universe_config.json").write_text(json.dumps(config, indent=2))
        self._write_hub_env_snippet()

    def seed_entities(self):
        """Seed topology skeleton — metrics filled on first tick from live layers."""
        from universe_layers import layer_urls

        urls = layer_urls()
        specs = [
            ("hub", "AIMarket Hub", "core", "core", "hub", {"x": 0, "y": 0, "z": 0}, urls["hub"]),
            ("factory", "AI-Factory", "core", "core", "factory", {"x": 4, "y": 2, "z": -2}, urls["app"]),
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
            ent.position = pos
            ent.url = url
            ent.metrics = {}
            self.entities[eid] = ent
        print(f"[Universe] {len(self.entities)} core nodes ready — awaiting layer poll")

    def sync_factory_catalog(self, app_url: str | None = None) -> int:
        """Import shipped products from Factory API as product planets (idempotent)."""
        from factory_products import fetch_factory_products_sync

        url = app_url or os.environ.get("AICOM_API_URL", "http://127.0.0.1:9081")
        catalog = fetch_factory_products_sync(url)
        if catalog is None:
            print(f"[Universe] Factory catalog sync skipped — API unreachable ({url})")
            return 0

        catalog_ids = {str(p.get("id") or "") for p in catalog if p.get("id")}

        # Drop product nodes removed from Factory (keeps core infra entities).
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
        current: set[str] = set()
        for n in disc.get("nodes", []):
            nid = n.get("id")
            if not nid:
                continue
            ent = self.entities.get(nid)
            if ent is not None and getattr(ent, "type", "") != "federation":
                # id collides with a non-discovery entity (core/product/agent) —
                # never clobber a real node with peer-supplied data.
                continue
            if ent is None:
                ent = EcosystemEntity(
                    nid, str(n.get("label") or nid), "federation", group="oracle",
                    description=str(n.get("description") or ""), icon="oracle",
                )
                self.entities[nid] = ent
            ent.metrics = {k: v for k, v in (n.get("metrics") or {}).items()}
            ent.status = n.get("status", "active")
            ent.url = n.get("url")
            ent.color = "#a64dff"
            ent.parent_id = "federation"
            if n.get("position"):
                ent.position = n["position"]
            current.add(nid)

        # Prune entities that were discovered before but are no longer peers.
        for stale in self._discovered_ids - current:
            ent = self.entities.get(stale)
            if ent is not None and getattr(ent, "type", "") == "federation":
                self.entities.pop(stale, None)
        self._discovered_ids = current

    def tick_universe(self) -> dict:
        from universe_layers import (
            apply_layers_to_entities,
            build_universe_summary,
            fetch_layers_sync,
            sync_agent_entities,
        )

        self.tick += 1

        contracts = {
            "escrow_evm": self.evm_escrow_address,
            "nft_evm": self.evm_nft_address,
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
        self._apply_discovery((layers.get("urls") or {}).get("hub", ""))
        if self.tick == 1 or self.tick % max(1, self._factory_sync_every_ticks) == 0:
            self.sync_factory_catalog()

        if self.blockchain_ready:
            self._fetch_chain_state()

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
        all_activity = sorted(
            onchain_activity + hub_events + self._discovery_events,
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
            hub_url = os.environ.get("ALIEN_UNIVERSE_HUB_URL") or os.environ.get("HUB_URL") or "http://127.0.0.1:9083"
            from universe_scenario import UniverseScenarioEngine
            self._scenario_engine = UniverseScenarioEngine(hub_url=hub_url)
        return self._scenario_engine.tick(self)

    def get_topology_links(self) -> list[dict]:
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
        for prod in self.products:
            links.append({"source": "factory", "target": prod["id"], "label": "created"})
        for ag in self.agents:
            links.append({"source": "mesh", "target": ag["id"], "label": "registered"})
        for did in self._discovered_ids:
            links.append({"source": "federation", "target": did, "label": "Federation peer"})
        return links
