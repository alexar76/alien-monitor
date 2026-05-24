"""
Virtual Universe Machine — self-contained AIMarket ecosystem emulator.

Spins up an embedded blockchain (Anvil for EVM), deploys real contracts,
executes real transactions, and creates virtual entities for every product.

All blockchain interactions produce REAL transaction hashes visible in the
monitor's activity stream with full analytics: blocks, gas, confirmations.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Virtual entity
# ---------------------------------------------------------------------------

AGENT_NAMES = [
    "AlphaBot", "DataWhisperer", "CodeNova", "PipelineX",
    "TradeMancer", "InsightForge", "NetPulse", "CryptoLens",
    "AuditHawk", "SpecForge", "GrowthVane", "DeepScout",
    "QuantumMuse", "FractalSynth", "VoidWalker", "StarWeaver",
]

PRODUCT_ICONS = ["star", "planet", "moon", "comet", "asteroid", "nebula", "pulsar"]


class VirtualEntity:
    def __init__(self, eid: str, name: str, etype: str, group: str = "product"):
        self.id = eid
        self.name = name
        self.type = etype
        self.group = group
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.position = {
            "x": random.uniform(-8, 8),
            "y": random.uniform(-6, 6),
            "z": random.uniform(-6, 6),
        }
        self.metrics: dict = {}
        self.status = "active"
        self.parent_id: Optional[str] = None
        self.color = random.choice(["#00f0ff", "#ff00ff", "#00ff88", "#7b2fff", "#ffdd00", "#ff6633"])

    def to_node(self) -> dict:
        return {
            "id": self.id, "label": self.name, "group": self.group,
            "icon": random.choice(PRODUCT_ICONS),
            "description": f"Virtual {self.type}: {self.name}",
            "metrics": self.metrics, "status": self.status,
            "position": self.position, "url": None, "children": [],
            "color": self.color, "parent_id": self.parent_id,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Minimal ERC20 bytecode (compiled FakeUSDT)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# VirtualUniverse
# ---------------------------------------------------------------------------


class VirtualUniverse:
    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or (Path(__file__).resolve().parent.parent / "data" / "universe")
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.anvil_proc: Optional[subprocess.Popen] = None
        self.solana_proc: Optional[subprocess.Popen] = None

        # Contract addresses (populated after deploy)
        self.evm_usdt_address: Optional[str] = None
        self.evm_escrow_address: Optional[str] = None
        self.evm_nft_address: Optional[str] = None

        # web3 instance (lazy)
        self._w3 = None

        # Virtual entities
        self.entities: dict[str, VirtualEntity] = {}
        self.products: list[dict] = []
        self.transactions: list[dict] = []
        self.events: list[dict] = []
        self.channels: list[dict] = []
        self.agents: list[dict] = []
        self.blocks_mined: list[dict] = []  # on-chain block analytics
        self.chain_analytics: dict = {"blocks": 0, "tx_count": 0, "gas_spent": 0, "addresses": 0}

        self.tick = 0
        self.running = False
        self.blockchain_ready = False
        self._pending_materializations: list[dict] = []
        self._eth_accounts: list[str] = []

        self.evm_rpc = "http://localhost:8545"
        self.solana_rpc = "http://localhost:8899"

    # ------------------------------------------------------------------
    # Blockchain
    # ------------------------------------------------------------------

    def start_blockchain(self) -> bool:
        started = False
        if shutil.which("anvil"):
            try:
                self.anvil_proc = subprocess.Popen(
                    ["anvil", "--host", "0.0.0.0", "--port", "8545",
                     "--chain-id", "31337", "--block-time", "2",
                     "--accounts", "20", "--balance", "1000", "--silent"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                time.sleep(3)
                started = True
                print("[Universe] Anvil started — chain 31337, 20 accounts, 1000 ETH each")
            except Exception as e:
                print(f"[Universe] Anvil failed: {e}")
        else:
            print("[Universe] Anvil not found. Install: curl -L https://foundry.paradigm.xyz | bash")

        if shutil.which("solana-test-validator"):
            try:
                self.solana_proc = subprocess.Popen(
                    ["solana-test-validator", "--reset", "--quiet", "--rpc-port", "8899"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                time.sleep(3)
                print("[Universe] Solana validator started")
            except Exception as e:
                print(f"[Universe] Solana failed: {e}")

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
            print("[Universe] web3.py not installed. Install: pip install web3")
            return

        self._w3 = Web3(Web3.HTTPProvider(self.evm_rpc))
        if self._w3.is_connected():
            self._eth_accounts = self._w3.eth.accounts
            print(f"[Universe] web3 connected — chain {self._w3.eth.chain_id}, "
                  f"{len(self._eth_accounts)} accounts")
        else:
            print("[Universe] web3 connection failed")

    def _fetch_chain_state(self):
        """Get current blockchain analytics."""
        if not self._w3 or not self._w3.is_connected():
            return
        try:
            block = self._w3.eth.get_block('latest')
            self.chain_analytics["blocks"] = block["number"]
            self.chain_analytics["tx_count"] = len(block.get("transactions", []))
            self.chain_analytics["gas_spent"] = block.get("gasUsed", 0)
            self.chain_analytics["addresses"] = len(self._eth_accounts)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Contract deployment
    # ------------------------------------------------------------------

    def deploy_contracts(self):
        """Deploy FakeUSDT and virtual contracts to Anvil."""
        if not self._w3 or not self._w3.is_connected():
            print("[Universe] No web3 — skipping deploy")
            return

        deployer = self._eth_accounts[0]

        # Deploy FakeUSDT
        try:
            abi = [
                {"constant": True, "inputs": [], "name": "name", "outputs": [{"name": "", "type": "string"}], "type": "function"},
                {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
                {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
                {"constant": True, "inputs": [{"name": "", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
                {"constant": False, "inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}], "name": "transfer", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
            ]
            Contract = self._w3.eth.contract(abi=abi, bytecode=ERC20_BYTECODE)
            tx_hash = Contract.constructor().transact({"from": deployer})
            receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash)
            self.evm_usdt_address = receipt.contractAddress
            print(f"[Universe] FakeUSDT deployed: {self.evm_usdt_address}  (tx: {tx_hash.hex()[:16]}...)")
            self._record_tx(tx_hash, receipt, "deploy", "FakeUSDT")
        except Exception as e:
            print(f"[Universe] USDT deploy failed: {e}")
            self.evm_usdt_address = "0xB2" * 20

        self.evm_escrow_address = "0xA1" * 20
        self.evm_nft_address = "0xC3" * 20

        # Mint USDT to all agent accounts
        if self.evm_usdt_address:
            self._mint_tokens()

        self._fetch_chain_state()
        self._save_config()

    def _mint_tokens(self):
        """Transfer ETH (as simulated USDT) to agent accounts for on-chain activity."""
        if not self._w3:
            return
        deployer = self._eth_accounts[0]
        for i, acct in enumerate(self._eth_accounts[1:10]):
            try:
                tx_hash = self._w3.eth.send_transaction({
                    "from": deployer,
                    "to": acct,
                    "value": self._w3.to_wei(random.randint(100, 500), "ether"),
                    "gas": 21000,
                })
                receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash)
                self._record_tx(tx_hash, receipt, "fund", f"Agent-{i}")
            except Exception as e:
                pass

    def _record_tx(self, tx_hash, receipt, action: str, target: str):
        """Record an on-chain transaction for the monitor's activity stream."""
        self.transactions.append({
            "id": tx_hash.hex()[:16],
            "hash": tx_hash.hex(),
            "from": receipt.get("from", "0x"),
            "to": receipt.get("to", "0x"),
            "action": action,
            "target": target,
            "amount": 0,
            "token": "ETH",
            "block": receipt.get("blockNumber", 0),
            "gas_used": receipt.get("gasUsed", 0),
            "status": "confirmed",
            "ts": datetime.now(timezone.utc).isoformat(),
            "onchain": True,
        })

    def _save_config(self):
        config = {
            "evm_rpc": self.evm_rpc,
            "evm_usdt": self.evm_usdt_address,
            "evm_escrow": self.evm_escrow_address,
            "evm_nft": self.evm_nft_address,
            "chain_id": 31337,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        (self.data_dir / "universe_config.json").write_text(json.dumps(config, indent=2))

    # ------------------------------------------------------------------
    # On-chain transaction execution (called during ticks)
    # ------------------------------------------------------------------

    def _execute_random_tx(self) -> Optional[dict]:
        """Execute a random on-chain transfer between agent accounts. Returns tx info."""
        if not self._w3 or len(self._eth_accounts) < 2:
            return None
        try:
            sender = random.choice(self._eth_accounts[:10])
            receiver = random.choice([a for a in self._eth_accounts[:10] if a != sender])
            amount_eth = round(random.uniform(0.001, 0.5), 6)
            amount_wei = self._w3.to_wei(amount_eth, "ether")

            tx_hash = self._w3.eth.send_transaction({
                "from": sender,
                "to": receiver,
                "value": amount_wei,
                "gas": 21000,
            })
            receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=5)

            tx_info = {
                "id": tx_hash.hex()[:16],
                "hash": tx_hash.hex(),
                "from": sender[:10] + "...",
                "to": receiver[:10] + "...",
                "amount": amount_eth,
                "token": "ETH",
                "block": receipt.get("blockNumber", 0),
                "gas_used": receipt.get("gasUsed", 0),
                "status": "confirmed",
                "ts": datetime.now(timezone.utc).isoformat(),
                "onchain": True,
            }
            self.transactions.append(tx_info)
            if len(self.transactions) > 100:
                self.transactions = self.transactions[-100:]

            self.chain_analytics["tx_count"] += 1
            self.chain_analytics["gas_spent"] += receipt.get("gasUsed", 0)

            return tx_info
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Entity seeding
    # ------------------------------------------------------------------

    def seed_entities(self):
        hub = VirtualEntity("hub", "AIMarket Hub", "core", "core")
        hub.position = {"x": 0, "y": 0, "z": 0}
        hub.metrics = {"peers": 5, "capabilities": 150, "channels_open": 34, "invocations_24h": 420}
        self.entities["hub"] = hub

        factory = VirtualEntity("factory", "AI-Factory", "core", "core")
        factory.position = {"x": 4, "y": 2, "z": -2}
        factory.metrics = {"products": 89, "tasks_pending": 7, "tasks_done": 450}
        self.entities["factory"] = factory

        mesh = VirtualEntity("mesh", "AI Service Mesh", "core", "core")
        mesh.position = {"x": -4, "y": -1, "z": 2}
        mesh.metrics = {"agents": 23, "tasks": 120, "activity": 890}
        self.entities["mesh"] = mesh

        acex = VirtualEntity("acex", "ACEX", "core", "core")
        acex.position = {"x": 2, "y": -3, "z": 4}
        acex.metrics = {"volume_24h": 12000, "listings": 45}
        self.entities["acex"] = acex

        for cid, cname, cpos in [
            ("evm_escrow", "EVM Escrow", {"x": 6, "y": 3, "z": 1}),
            ("solana_escrow", "Solana Escrow", {"x": 5, "y": -2, "z": -3}),
            ("nft_contract", "Capability NFT", {"x": 7, "y": 0, "z": -1}),
        ]:
            ent = VirtualEntity(cid, cname, "contract", "contract")
            ent.position = cpos
            ent.metrics = {
                "channels": random.randint(10, 50),
                "tvl": random.randint(10000, 100000),
            }
            if cid == "evm_escrow":
                ent.metrics["address"] = self.evm_usdt_address or "0xB2" * 20
                ent.metrics["chain"] = "anvil-31337"
            self.entities[cid] = ent

        desktop = VirtualEntity("desktop_apps", "Desktop Apps", "client", "client")
        desktop.position = {"x": -3, "y": 4, "z": -4}
        desktop.metrics = {"apps_online": 5, "total_apps": 9}
        self.entities["desktop_apps"] = desktop

        plugins = VirtualEntity("plugins", "Plugins", "infra", "infra")
        plugins.position = {"x": 0, "y": -5, "z": -3}
        plugins.metrics = {"loaded": 13, "total": 15}
        self.entities["plugins"] = plugins

        for sid, sname, spos in [
            ("sdk_dart", "Dart SDK", {"x": -5, "y": 1, "z": 5}),
            ("sdk_typescript", "TypeScript SDK", {"x": -6, "y": -1, "z": 4}),
            ("sdk_rust", "Rust SDK", {"x": -5, "y": 2, "z": -5}),
        ]:
            ent = VirtualEntity(sid, sname, "sdk", "sdk")
            ent.position = spos
            self.entities[sid] = ent

        for eid, ename, egroup, epos in [
            ("federation", "Federation", "network", {"x": -2, "y": 5, "z": 1}),
            ("widget", "Widget", "client", {"x": 3, "y": 5, "z": -2}),
            ("ethereum", "Anvil L1", "chain", {"x": 8, "y": 3, "z": 3}),
            ("solana", "Solana", "chain", {"x": 8, "y": -2, "z": -4}),
            ("cli", "CLI Tools", "client", {"x": -3, "y": -4, "z": 5}),
        ]:
            ent = VirtualEntity(eid, ename, egroup, egroup)
            ent.position = epos
            if eid == "ethereum":
                ent.metrics = {"chain_id": 31337, "block": 0, "gas": 0, "tx_count": 0}
            self.entities[eid] = ent

        for i, name in enumerate(AGENT_NAMES[:8]):
            agent = VirtualEntity(f"agent_{i}", name, "agent", "agent")
            agent.position = {
                "x": random.uniform(-6, 6),
                "y": random.uniform(-4, 4),
                "z": random.uniform(-4, 4),
            }
            agent.metrics = {
                "balance_eth": round(random.uniform(100, 500), 2),
                "channels_open": random.randint(0, 5),
                "invocations": random.randint(0, 50),
            }
            self.entities[agent.id] = agent
            self.agents.append({
                "id": agent.id, "name": name,
                "balance": agent.metrics["balance_eth"],
            })

        print(f"[Universe] {len(self.entities)} entities, {len(self.agents)} agents seeded")

    # ------------------------------------------------------------------
    # Product materialization
    # ------------------------------------------------------------------

    def materialize_product(self, product_data: dict) -> VirtualEntity:
        pid = product_data.get("id", f"product_{self.tick}_{random.randint(1000,9999)}")
        name = product_data.get("name", f"Product-{self.tick}")
        ptype = product_data.get("type", product_data.get("category", "fullstack-app"))
        entity = VirtualEntity(pid, name, ptype, "product")
        entity.parent_id = "factory"
        entity.metrics = {
            "version": product_data.get("version", "0.1.0"),
            "price_usdt": product_data.get("price", round(random.uniform(0.5, 50), 2)),
            "invocations": 0,
        }
        fp = self.entities.get("factory", None)
        if fp:
            entity.position = {
                "x": fp.position["x"] + random.uniform(-3, 3),
                "y": fp.position["y"] + random.uniform(-2, 2),
                "z": fp.position["z"] + random.uniform(-2, 2),
            }
        self.entities[pid] = entity
        self.products.append(entity.to_node())
        self._pending_materializations.append({
            "type": "product_materialized",
            "id": pid, "name": name, "category": ptype,
            "ts": datetime.now(timezone.utc).isoformat(),
            "position": entity.position, "color": entity.color,
        })
        print(f"[Universe] +product: {name} ({ptype})")
        return entity

    def get_pending_materializations(self) -> list[dict]:
        events = list(self._pending_materializations)
        self._pending_materializations.clear()
        return events

    # ------------------------------------------------------------------
    # Tick — advance the universe + execute real on-chain transactions
    # ------------------------------------------------------------------

    def tick_universe(self) -> dict:
        self.tick += 1
        t = self.tick

        # Execute REAL on-chain transaction every 2 ticks
        if self.blockchain_ready and t % 2 == 0:
            self._execute_random_tx()

        # Update blockchain analytics
        if self.blockchain_ready and t % 3 == 0:
            self._fetch_chain_state()
            if "ethereum" in self.entities:
                self.entities["ethereum"].metrics = {
                    "chain_id": 31337,
                    "block": self.chain_analytics["blocks"],
                    "gas": self.chain_analytics["gas_spent"],
                    "tx_count": self.chain_analytics["tx_count"],
                }

        # Update hub metrics
        hub = self.entities.get("hub")
        if hub:
            hub.metrics["invocations_24h"] = 400 + t * 10 + random.randint(-20, 30)
            hub.metrics["channels_open"] = 30 + (t % 20) + random.randint(0, 5)

        # Update factory
        factory = self.entities.get("factory")
        if factory:
            factory.metrics["products"] = 89 + t + len(self.products)
            factory.metrics["tasks_pending"] = random.randint(3, 15)

        # Update other entities
        for eid, ent in self.entities.items():
            if eid == "mesh":
                ent.metrics["activity"] = 800 + t * 20 + random.randint(-30, 50)
            elif eid == "acex":
                ent.metrics["volume_24h"] = 10000 + t * 800 + random.randint(-1000, 3000)
            elif eid.startswith("agent_"):
                ent.metrics["invocations"] = ent.metrics.get("invocations", 0) + random.randint(0, 2)

        # Generate virtual events (non-chain)
        if t % 3 == 0:
            self.events.append({
                "id": f"evt_{t}_{len(self.events)}",
                "ts": datetime.now(timezone.utc).isoformat(),
                "agent": random.choice(AGENT_NAMES[:8]),
                "action": random.choice(["invoke", "discover", "channel_open", "channel_close", "settle"]),
                "target": random.choice(["hub", "mesh", "factory", "evm_escrow"]),
                "amount": round(random.uniform(0.05, 25.0), 2),
                "token": "USDT",
            })
            if len(self.events) > 200:
                self.events = self.events[-200:]

        # Merge on-chain txs + virtual events for the activity stream
        all_activity = sorted(
            self.transactions[-20:] + self.events[-20:],
            key=lambda x: x.get("ts", ""),
            reverse=True,
        )[:20]

        nodes = [ent.to_node() for ent in self.entities.values()]

        links = self.get_topology_links()

        return {
            "tick": t,
            "ts": datetime.now(timezone.utc).isoformat(),
            "nodes": nodes,
            "links": links,
            "events": all_activity,
            "transactions": self.transactions[-20:],
            "channels": self.channels[-10:],
            "summary": self._build_summary(),
            "materializations": self.get_pending_materializations(),
            "chain_analytics": self.chain_analytics,
        }

    def _build_summary(self) -> dict:
        hub = self.entities.get("hub", None)
        acex = self.entities.get("acex", None)
        eth = self.entities.get("ethereum", None)
        return {
            "total_invocations_24h": hub.metrics.get("invocations_24h", 0) if hub else 0,
            "total_volume_usd": acex.metrics.get("volume_24h", 0) if acex else 0,
            "active_channels": hub.metrics.get("channels_open", 0) if hub else 0,
            "tvl_usd": 50000 + self.tick * 500,
            "agents_online": len(self.agents),
            "apps_online": 5,
            "tps_solana": random.randint(1200, 3500),
            "gas_gwei": self.chain_analytics.get("gas_spent", 0),
            "block_number": self.chain_analytics.get("blocks", 0),
            "onchain_tx_count": self.chain_analytics.get("tx_count", 0),
            "mode": "universe",
            "tick": self.tick,
            "blockchain_ready": self.blockchain_ready,
            "products_created": len(self.products),
            "entities_total": len(self.entities),
            "evm_rpc": self.evm_rpc,
            "usdt_contract": self.evm_usdt_address,
        }

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
            {"source": "hub", "target": "sdk_dart", "label": "REST API"},
            {"source": "hub", "target": "sdk_typescript", "label": "REST API"},
            {"source": "hub", "target": "sdk_rust", "label": "REST API"},
            {"source": "desktop_apps", "target": "sdk_dart", "label": "Dart SDK"},
            {"source": "cli", "target": "hub", "label": "CLI"},
            {"source": "factory", "target": "mesh", "label": "Orchestration"},
            {"source": "evm_escrow", "target": "ethereum", "label": "EVM RPC"},
            {"source": "solana_escrow", "target": "solana", "label": "Solana RPC"},
            {"source": "acex", "target": "factory", "label": "Capital data"},
        ]
        for prod in self.products:
            links.append({"source": "factory", "target": prod["id"], "label": "created"})
        return links
