"""Deploying the universe's contracts with forge (USDT, escrow, NFT, lottery, ACEX) and the
Solana lottery, and writing the hub's env snippet.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from universe_entities import ANVIL_DEPLOYER_KEY, resolve_acex_evm_dir, resolve_evm_contracts_dir, resolve_lottery_contracts_dir, resolve_solana_contracts_dir
from evm_dev_key_safety import local_dev_rpc, require_local_dev_chain


class ContractDeployMixin:
    """Forge and Solana deployments of the universe's contracts."""

    def _assert_demo_deployment_rpc(self) -> None:
        if not local_dev_rpc(self.evm_rpc):
            raise RuntimeError("Universe's public deployer key requires a local/private development RPC")
        from web3 import Web3

        w3 = Web3(Web3.HTTPProvider(self.evm_rpc, request_kwargs={"timeout": 5, "allow_redirects": False}))
        require_local_dev_chain(w3, self.evm_rpc)

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
        self._assert_demo_deployment_rpc()
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
                ["forge", "script", script, "--rpc-url", self.evm_rpc, "--chain-id", "31337", "--broadcast", "--slow"],
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
        self._assert_demo_deployment_rpc()
        env = os.environ.copy()
        env["PRIVATE_KEY"] = ANVIL_DEPLOYER_KEY
        env["DEPLOYER_PRIVATE_KEY"] = ANVIL_DEPLOYER_KEY
        env["USDC_ADDRESS"] = self.evm_usdt_address
        try:
            proc = subprocess.run(
                ["forge", "script", "script/DeployACEX.s.sol:DeployACEX", "--rpc-url", self.evm_rpc, "--chain-id", "31337", "--broadcast", "--slow"],
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
        self._assert_demo_deployment_rpc()
        env = os.environ.copy()
        env["PRIVATE_KEY"] = ANVIL_DEPLOYER_KEY
        env.update(extra_env)
        try:
            proc = subprocess.run(
                ["forge", "script", script, "--rpc-url", self.evm_rpc, "--chain-id", "31337", "--broadcast", "--slow"],
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
