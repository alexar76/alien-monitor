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
ANVIL_DEPLOYER_KEY = (
    "0xac0974bec39a17e36ba4a6b4d4e5d4e5d4e5d4e5d4e5d4e5d4e5d4e5d4ecafe"
)

AICOM_ROOT = Path(__file__).resolve().parent.parent.parent

# Poll Factory catalog every N ticks (~60s at 1.5s/tick) — not every broadcast.
_FACTORY_SYNC_EVERY_TICKS = max(1, int(os.environ.get("ALIEN_FACTORY_SYNC_TICKS", "40")))
_MAX_PRODUCT_ENTITIES = max(50, int(os.environ.get("ALIEN_MAX_PRODUCT_ENTITIES", "400")))

# Minimal ERC20 bytecode (FakeUSDT) — deployed on local chain for escrow whitelist.
ERC20_BYTECODE = (
    "60806040523480156200001157600080fd5b506040518060400160405280600881526020017f"
    "46616b6555534454000000000000000000000000000000000000000000000000008152506040518060400160405280600481526020017f"
    "555344540000000000000000000000000000000000000000000000000000000081525081600390805190602001906200009092919062000157565b50"
    "508051620000ae90600490602084019062000090565b50506005805460ff1916601217905550620001fe565b828054620000d590620000c3565b"
    "90600052602060002090601f016020900481019282620000f9576000855562000144565b82601f106200011457805160ff191683800117855562000144565b"
    "8280016001018555821562000144579182015b828111156200014357825182559160200191906001019062000126565b5b506200015392915062000154565b"
    "5090565b5b808211156200016f576000815560010162000155565b5090565b6000602082840312156200018757600080fd5b81516001600160a01b03811681146200019f57600080fd5b"
    "9392505050565b600060208284031215620001bb57600080fd5b81518015158114620001cc57600080fd5b9392505050565b600060208284031215620001e757600080fd5b815160ff81168114620001f957600080fd5b9392505050565b"
    "610dda806200020e6000396000f3fe608060405234801561001057600080fd5b50600436106100a35760003560e01c8063313ce56711610074578063"
    "a9059cbb1161004e578063a9059cbb1461013d578063dd62ed3e1461016d578063f2fde38b1461019d57600080fd5b8063313ce56714610115578063"
    "70a082311461013357806395d89b41146100dd57600080fd5b806306fdde03146100a8578063095ea7b3146100c657806318160ddd146100f6578063"
    "23b872dd14610102575b600080fd5b6100b06101b9565b6040516100bd919061080c565b60405180910390f35b6100d96100d4366004610872565b61024b565b005b6100b06102b4565b6100f461010436600461089c565b610342565b005b6002546100f4565b6100f46101103660046108d8565b6103d1565b61011d6104b9565b60405160ff90911681526020016100bd565b6100f46104be565b6100f461014b366004610872565b6104c4565b6100f461017b366004610914565b61054e565b6100f461018b366004610947565b6105b9565b6100f46101ab36600461097a565b610624565b6060600380546101c890610995565b80601f01602080910402602001604051908101604052809291908181526020018280546101f490610995565b80156102415780601f1061021657610100808354040283529160200191610241565b820191906000526020600020905b81548152906001019060200180831161022457829003601f168201915b5050505050905090565b6000338181526001602090815260408083206001600160a01b03871684529091528120805484929061027e9084906109c7565b90915550506001600160a01b0392831660009081526001602090815260408083209490951682529290925291902055565b6060600480546102c390610995565b80601f01602080910402602001604051908101604052809291908181526020018280546102ef90610995565b801561033c5780601f106103115761010080835404028352916020019161033c565b820191906000526020600020905b81548152906001019060200180831161031f57829003601f168201915b5050505050905090565b60025481565b6001600160a01b0383166000908152602081905260408120805484929061036a9084906109da565b90915550506001600160a01b038084166000818152602081905260408082208054870190555190918616907fddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef906103c49087815260200190565b60405180910390a3505050565b6001600160a01b038316600090815260208190526040812080548492906103f99084906109c7565b90915550506001600160a01b038316600090815260208190526040812080548492906104269084906109c7565b90915550506001600160a01b0384811660008181526001602090815260408083208786168452909152902080548592906104619084906109da565b90915550506001600160a01b038381166000818152602081905260408082208054880190555190918716907fddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef906103c49087815260200190565b601281565b60025481565b33600090815260208190526040812080548492906104e39084906109c7565b90915550506001600160a01b038216600090815260208190526040812080548492906105109084906109c7565b90915550506040518281526001600160a01b0383169033907fddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef9060200160405180910390a35050565b6001600160a01b0382811660008181526001602090815260408083208686168452909152808220805486905590519193928516917f8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b9259190a35050565b6001600160a01b0381166000908152602081905260408120545b92915050565b6001600160a01b038116600090815260208190526040812054819061064a9060016109c7565b90505b919050565b600060208083528351808285015260005b8181101561067c57858101830151858201604001528201610660565b8181111561068e576000604083870101525b50601f01601f1916929092016040019392505050565b80356001600160a01b038116811461064d57600080fd5b600080604083850312156106cd57600080fd5b6106d6836106a5565b946020939093013593505050565b6000806000606084860312156106f957600080fd5b610702846106a5565b9250610710602085016106a5565b9150604084013590509250925092565b6000806040838503121561073357600080fd5b61073c836106a5565b915061074a602084016106a5565b90509250929050565b60006020828403121561076557600080fd5b61076e826106a5565b9392505050565b600181811c9082168061078957607f821691505b6020821081036107a957634e487b7160e01b600052602260045260246000fd5b50919050565b601f82111561080757600081815260208120601f850160051c810160208610156107d65750805b601f850160051c820191505b818110156107f5578281556001016107e2565b5050505b505050565b6000815180845260005b8181101561083357602081850181015186830182015201610817565b81811115610845576000602083870101525b50601f01601f19169290920160200192915050565b634e487b7160e01b600052601160045260246000fd5b600082198211156108905761089061085a565b500190565b6000602082840312156108a257600080fd5b5035919050565b634e487b7160e01b600052604160045260246000fd5b634e487b7160e01b600052603260045260246000fd5b6000806000606084860312156108ed57600080fd5b6108f6846106a5565b9250610904602085016106a5565b9150604084013590509250925092565b6000806040838503121561092757600080fd5b610930836106a5565b9150602083013590509250929050565b6000806040838503121561095a57600080fd5b610963836106a5565b9150610971602084016106a5565b90509250929050565b60006020828403121561098c57600080fd5b61076e826106a5565b600181811c908216806109a957607f821691505b6020821081036109c957634e487b7160e01b600052602260045260246000fd5b50919050565b6000828210156109d9576109d961085a565b500390565b600082198211156109ed576109ed61085a565b50019056fea2646970667358221220123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef64736f6c634300080f0033"
)


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
        self._scenario_engine = None
        self._factory_sync_every_ticks = int(os.environ.get("ALIEN_FACTORY_SYNC_TICKS", "40"))

        self.evm_rpc = (os.environ.get("ALIEN_UNIVERSE_EVM_RPC") or "http://127.0.0.1:8545").rstrip("/")
        self.solana_rpc = (os.environ.get("ALIEN_UNIVERSE_SOLANA_RPC") or "http://127.0.0.1:8899").rstrip("/")
        self.chain_label = os.environ.get("ALIEN_UNIVERSE_CHAIN_LABEL", "EVM Network")

    def start_blockchain(self) -> bool:
        started = False
        if shutil.which("anvil"):
            try:
                self.anvil_proc = subprocess.Popen(
                    [
                        "anvil", "--host", "127.0.0.1", "--port", "8545",
                        "--chain-id", "31337", "--block-time", "2",
                        "--accounts", "20", "--balance", "1000", "--silent",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                time.sleep(3)
                started = True
                print("[Universe] EVM node online")
            except Exception as exc:
                print(f"[Universe] EVM start failed: {exc}")
        else:
            print("[Universe] anvil not found — install Foundry")

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
            self._init_web3()
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
            print("[Universe] EVM not connected — skip deploy")
            return

        deployer = self._eth_accounts[0]
        self._deploy_usdt(deployer)
        self._deploy_escrow_forge(deployer)
        self._deploy_nft_forge(deployer)
        self._fetch_chain_state()
        self._save_config()

    def _deploy_usdt(self, deployer: str):
        try:
            abi = [
                {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
                {"constant": False, "inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}], "name": "transfer", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
            ]
            contract = self._w3.eth.contract(abi=abi, bytecode=ERC20_BYTECODE)
            tx_hash = contract.constructor().transact({"from": deployer})
            receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash)
            self.evm_usdt_address = receipt.contractAddress
            self._record_tx(tx_hash, receipt, "deploy", "USDT")
            print(f"[Universe] USDT deployed: {self.evm_usdt_address}")
        except Exception as exc:
            print(f"[Universe] USDT deploy failed: {exc}")

    def _forge_run(self, script: str, deployer: str, extra_env: dict) -> str | None:
        if not shutil.which("forge"):
            return None
        evm_dir = AICOM_ROOT / "contracts" / "evm"
        if not evm_dir.is_dir():
            return None
        env = os.environ.copy()
        env["PRIVATE_KEY"] = ANVIL_DEPLOYER_KEY
        env["INITIAL_HUBS"] = deployer
        if self.evm_usdt_address:
            env["INITIAL_TOKENS"] = self.evm_usdt_address
        env.update(extra_env)
        try:
            subprocess.run(
                ["forge", "script", script, "--rpc-url", self.evm_rpc, "--broadcast", "--slow"],
                cwd=str(evm_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            print(f"[Universe] forge {script}: {exc}")
            return None
        return self._parse_broadcast_address(script)

    def _parse_broadcast_address(self, script: str) -> str | None:
        broadcast = AICOM_ROOT / "contracts" / "evm" / "broadcast" / script / "31337"
        if not broadcast.is_dir():
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
            onchain_activity + hub_events,
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
        return links
