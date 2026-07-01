"""
Alien Monitor — Backend data aggregation + WebSocket streaming server.

Three modes:
  TEST     — simulates a vibrant ecosystem with fake agents, channels, tx
  REAL     — queries live hub / mesh / prometheus / blockchain RPCs
  UNIVERSE — local chain + live polls from deployed Hub/Mesh/Factory/Prometheus
             (same presentation as REAL; no simulated metrics)

Environment:
  ALIEN_MODE=test|real|universe   (default: test)
  ALIEN_PORT=9100
  HUB_URL=http://localhost:9083
  MESH_URL=http://localhost:8090
  PROMETHEUS_URL=http://localhost:9090
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from universe import VirtualUniverse
from chain_metrics import (
    apply_chain_metrics_to_nodes,
    build_real_summary,
    fetch_onchain_snapshot,
    hub_events_to_activity,
)
from factory_products import ensure_factory_clusters, resolve_factory_catalog, merge_factory_products
from lottery_layers import apply_lottery_metrics, lottery_financial_links, lottery_node_spec
from argus_layers import argus_node_spec, argus_topology_links
from monitor_auth import (
    cors_allow_origins,
    monitor_control_token_valid,
    require_monitor_auth,
    require_monitor_read_auth,
    require_monitor_state_auth,
)
from monitor_base_path import MonitorBasePathMiddleware
from ai_assistant import (
    EMPTY_QUESTION,
    any_provider_configured,
    build_live_context,
    build_system_prompt,
    generate_answer,
    list_providers,
    normalize_locale,
    resolve_response_locale,
)

_MONITOR_ROOT = Path(__file__).resolve().parent.parent


def _resolve_aicom_root_for_env() -> Path:
    for key in ("AICOM_ROOT", "AICOM_MONOREPO_ROOT"):
        raw = os.environ.get(key, "").strip()
        if raw:
            return Path(raw)
    if (_MONITOR_ROOT / "contracts" / "evm").is_dir():
        return _MONITOR_ROOT
    parent = _MONITOR_ROOT.parent
    if (parent / "contracts" / "evm").is_dir():
        return parent
    return _MONITOR_ROOT


_AICOM_ROOT = _resolve_aicom_root_for_env()
load_dotenv(_AICOM_ROOT / ".env")
load_dotenv(_MONITOR_ROOT / ".env")
load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _normalize_mode(value: str | None) -> str | None:
    if value in ("test", "real", "universe"):
        return value
    return None


SERVER_MODE = _normalize_mode(os.getenv("ALIEN_MODE", "test").strip().lower()) or "test"
# Immutable server default from env — never mutated by browser WebSocket clients.
MODE = SERVER_MODE
_runtime_server_mode: str | None = None
_ws_client_modes: dict[int, str] = {}


def get_server_mode() -> str:
    """Canonical monitor mode for REST/health (env + optional admin override)."""
    return _normalize_mode(_runtime_server_mode) or SERVER_MODE
PORT = int(os.getenv("ALIEN_PORT", "9100"))
HOST = os.getenv("ALIEN_HOST", "127.0.0.1")
HUB_URL = os.getenv("HUB_URL", "http://localhost:9083").rstrip("/")
MESH_URL = os.getenv("MESH_URL", "http://localhost:8090").rstrip("/")
PROM_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090").rstrip("/")
APP_URL = os.getenv("AICOM_API_URL", "http://localhost:9081").rstrip("/")
# LUMEN reputation oracle (or the oracle-family endpoint). When set, the REP
# graph asks the REAL oracle to compute EigenTrust/PageRank; else it falls back
# to the monitor's local PageRank. e.g. http://localhost:9303 or :9400 (family).
LUMEN_URL = os.getenv("LUMEN_URL", "").rstrip("/")

# ---------------------------------------------------------------------------
# Data models (hand-rolled, no pydantic to keep it light)
# ---------------------------------------------------------------------------

ECO_NODES: list[dict] = []
ECO_LINKS: list[dict] = []
ACTIVITY_LOG: list[dict] = []
METRICS_SNAPSHOT: dict = {}
CONNECTED_CLIENTS: set = set()
LAST_MONITOR_STATE: dict | None = None
LAST_MONITOR_STATES: dict[str, dict] = {}
_state_fetch_lock = asyncio.Lock()
STATE_TICK_INTERVAL = float(os.getenv("ALIEN_STATE_TICK_SEC", "1.5"))
logger = logging.getLogger(__name__)
_universe_bootstrap: dict | None = None

# ---------------------------------------------------------------------------
# Ecosystem topology — defines the graph structure
# ---------------------------------------------------------------------------


def build_topology() -> tuple[list[dict], list[dict]]:
    """Return (nodes, links) for the ecosystem graph."""
    nodes: list[dict] = [
        {
            "id": "hub",
            "label": "AIMarket Hub",
            "group": "core",
            "icon": "hub",
            "url": HUB_URL,
            "description": "Federated capability catalog + payment routing",
            "metrics": {"peers": 0, "capabilities": 0, "channels_open": 0, "invocations_24h": 0},
            "status": "unknown",
            "position": {"x": 0, "y": 0, "z": 0},
        },
        {
            "id": "factory",
            "label": "AI-Factory",
            "group": "core",
            "icon": "factory",
            "url": APP_URL,
            "description": "Autonomous pipeline — builds & publishes products",
            "metrics": {"products": 0, "tasks_pending": 0, "tasks_done": 0},
            "status": "unknown",
            "position": {"x": 4, "y": 2, "z": -2},
        },
        {
            "id": "mesh",
            "label": "AI Service Mesh",
            "group": "core",
            "icon": "mesh",
            "url": MESH_URL,
            "description": "Agent discovery, verification, escrow & orchestration",
            "metrics": {"agents": 0, "tasks": 0, "activity": 0},
            "status": "unknown",
            "position": {"x": -4, "y": -1, "z": 2},
        },
        {
            "id": "acex",
            "label": "ACEX",
            "group": "core",
            "icon": "exchange",
            "description": "Agent Capital Exchange — ALP, CapShares, AMM",
            "metrics": {"volume_24h": 0, "listings": 0},
            "status": "unknown",
            "position": {"x": 2, "y": -3, "z": 4},
        },
        {
            "id": "evm_escrow",
            "label": "EVM Escrow",
            "group": "contract",
            "icon": "contract",
            "description": "Payment channels on Ethereum/Base/Arbitrum (USDT/USDC)",
            "metrics": {"channels": 0, "tvl": 0, "chain": "ethereum"},
            "status": "unknown",
            "position": {"x": 6, "y": 3, "z": 1},
        },
        {
            "id": "solana_escrow",
            "label": "Solana Escrow",
            "group": "contract",
            "icon": "contract",
            "description": "Payment channels on Solana (USDC)",
            "metrics": {"channels": 0, "tvl": 0, "chain": "solana"},
            "status": "unknown",
            "position": {"x": 5, "y": -2, "z": -3},
        },
        {
            "id": "nft_contract",
            "label": "Capability NFT",
            "group": "contract",
            "icon": "nft",
            "description": "ERC-721 transferable capability entitlements",
            "metrics": {"minted": 0, "holders": 0},
            "status": "unknown",
            "position": {"x": 7, "y": 0, "z": -1},
        },
        {
            "id": "desktop_apps",
            "label": "Desktop Apps",
            "group": "client",
            "icon": "desktop",
            "description": "8 Flutter + 1 Tauri desktop integrations",
            "metrics": {"apps_online": 0, "total_apps": 9},
            "status": "unknown",
            "children": [
                {"id": "capability_composer", "label": "Capability Composer"},
                {"id": "cold_outreach", "label": "Cold Outreach Coach"},
                {"id": "creator_algo", "label": "Creator Algorithm Coach"},
                {"id": "discovery_prospector", "label": "Discovery Prospector"},
                {"id": "freelance_review", "label": "Freelance Contract Reviewer"},
                {"id": "interview_prep", "label": "Interview Prep Coach"},
                {"id": "personal_finance", "label": "Personal Finance Coach"},
                {"id": "reputation_dash", "label": "Reputation Dashboard"},
                {"id": "security_audit", "label": "Local Security Audit"},
            ],
            "position": {"x": -3, "y": 4, "z": -4},
        },
        {
            "id": "plugins",
            "label": "Plugins",
            "group": "infra",
            "icon": "plugin",
            "description": "15 hub plugins — safety, TEE, channels, ZK, streaming...",
            "metrics": {"loaded": 0, "total": 15},
            "status": "unknown",
            "children": [
                {"id": "plugin_safety", "label": "Safety Gate"},
                {"id": "plugin_tee", "label": "TEE Attestation"},
                {"id": "plugin_channels", "label": "Channels"},
                {"id": "plugin_streaming", "label": "Streaming SSE"},
                {"id": "plugin_reputation", "label": "Reputation"},
                {"id": "plugin_auction", "label": "Auction"},
                {"id": "plugin_orchestrator", "label": "Orchestrator"},
                {"id": "plugin_nft", "label": "NFT"},
                {"id": "plugin_zk", "label": "ZK Proofs"},
                {"id": "plugin_provenance", "label": "Provenance"},
                {"id": "plugin_mcp", "label": "MCP Packager"},
                {"id": "plugin_personas", "label": "Personas"},
                {"id": "plugin_promo", "label": "Promo"},
                {"id": "plugin_dataset", "label": "Dataset"},
                {"id": "plugin_data_cap", "label": "Data Cap"},
            ],
            "position": {"x": 0, "y": -5, "z": -3},
        },
        {
            "id": "sdk_dart",
            "label": "Dart SDK",
            "group": "sdk",
            "icon": "sdk",
            "description": "Flutter/Dart client SDK for AIMarket",
            "metrics": {"version": "0.1.0"},
            "status": "unknown",
            "position": {"x": -5, "y": 1, "z": 5},
        },
        {
            "id": "sdk_typescript",
            "label": "TypeScript SDK",
            "group": "sdk",
            "icon": "sdk",
            "description": "Node.js / browser client SDK",
            "metrics": {"version": "0.1.0"},
            "status": "unknown",
            "position": {"x": -6, "y": -1, "z": 4},
        },
        {
            "id": "sdk_rust",
            "label": "Rust SDK",
            "group": "sdk",
            "icon": "sdk",
            "description": "Rust/Tauri client SDK",
            "metrics": {"version": "0.1.0"},
            "status": "unknown",
            "position": {"x": -5, "y": 2, "z": -5},
        },
        {
            "id": "federation",
            "label": "Federation",
            "group": "network",
            "icon": "globe",
            "description": "BFS peer discovery across federated hubs",
            "metrics": {"peers": 0, "crawls": 0},
            "status": "unknown",
            "position": {"x": -2, "y": 5, "z": 1},
        },
        {
            "id": "widget",
            "label": "Widget",
            "group": "client",
            "icon": "widget",
            "description": "Embeddable storefront widget (one <script> tag)",
            "metrics": {"themes": 6, "impressions": 0},
            "status": "unknown",
            "position": {"x": 3, "y": 5, "z": -2},
        },
        {
            "id": "ethereum",
            "label": "Base",
            "group": "chain",
            "icon": "chain",
            "description": "Primary EVM chain (Base · 8453); relabels live to whatever RPC is connected",
            "metrics": {"gas": 0, "block": 0},
            "status": "unknown",
            "position": {"x": 8, "y": 3, "z": 3},
        },
        {
            "id": "solana",
            "label": "Solana",
            "group": "chain",
            "icon": "chain",
            "description": "Solana L1",
            "metrics": {"slot": 0, "tps": 0},
            "status": "unknown",
            "position": {"x": 8, "y": -2, "z": -4},
        },
        {
            "id": "cli",
            "label": "CLI Tools",
            "group": "client",
            "icon": "terminal",
            "description": "ai_company_cli, ai_market_agent, ai_market_sdk",
            "metrics": {"commands": 0},
            "status": "unknown",
            "position": {"x": -3, "y": -4, "z": 5},
        },
        lottery_node_spec(),
        argus_node_spec(),
    ]

    links: list[dict] = [
        # Hub connections (center of ecosystem)
        {"source": "hub", "target": "factory", "label": "Capability catalog"},
        {"source": "hub", "target": "mesh", "label": "Agent discovery"},
        {"source": "hub", "target": "acex", "label": "Pricing feed"},
        {"source": "hub", "target": "evm_escrow", "label": "Channel settlement"},
        {"source": "hub", "target": "solana_escrow", "label": "Channel settlement"},
        {"source": "hub", "target": "nft_contract", "label": "NFT entitlements"},
        {"source": "hub", "target": "plugins", "label": "Plugin hooks"},
        {"source": "hub", "target": "federation", "label": "Peer crawl"},
        {"source": "hub", "target": "widget", "label": "Search API"},
        # SDK connections
        {"source": "hub", "target": "sdk_dart", "label": "REST API"},
        {"source": "hub", "target": "sdk_typescript", "label": "REST API"},
        {"source": "hub", "target": "sdk_rust", "label": "REST API"},
        # Desktop apps use Dart SDK
        {"source": "desktop_apps", "target": "sdk_dart", "label": "Dart SDK"},
        {"source": "desktop_apps", "target": "hub", "label": "Invoke"},
        {"source": "cli", "target": "hub", "label": "CLI"},
        # Factory ↔ mesh
        {"source": "factory", "target": "mesh", "label": "Agent orchestration"},
        # Escrow ↔ chains
        {"source": "evm_escrow", "target": "ethereum", "label": "EVM RPC"},
        {"source": "solana_escrow", "target": "solana", "label": "Solana RPC"},
        # ACEX ↔ hub + factory
        {"source": "acex", "target": "factory", "label": "Capital data"},
    ]
    links.extend(lottery_financial_links(oracle_ids=["federation"]))
    links.extend(argus_topology_links())

    return nodes, links


# ---------------------------------------------------------------------------
# Simulator — generates fake but realistic ecosystem activity
# ---------------------------------------------------------------------------


# ── Live lottery feed (real AI-Agent Oracle Lottery relayer) ───────────────────
from live_lottery_feed import (
    LIVE_LOTTERY_TTL,
    live_lottery_fresh,
    set_live_lottery,
)


def apply_live_lottery(sim: "EcosystemSimulator") -> bool:
    """If a fresh real feed exists, copy it into sim.lottery + merge its events."""
    from live_lottery_feed import _LIVE_LOTTERY

    if not live_lottery_fresh():
        return False
    m = _LIVE_LOTTERY["metrics"]
    sim.lottery.update({
        "pool": m.get("prize_pool_usd", 0), "round": m.get("round", 0),
        "players": m.get("players", 0), "payouts": m.get("payouts_24h", 0),
        "opex": m.get("opex_24h", 0), "funding": m.get("funding_24h", 0),
        "last_winner": _LIVE_LOTTERY["last_winner"],
    })
    existing = {e.get("id") for e in sim.events}
    for ev in _LIVE_LOTTERY["events"]:
        if ev.get("id") not in existing:
            sim.events.append(ev)
    if len(sim.events) > 200:
        sim.events = sim.events[-200:]
    return True


class EcosystemSimulator:
    """Generates realistic-looking activity for TEST mode."""

    def __init__(self) -> None:
        self.tick = 0
        self.agent_names = [
            "AlphaBot", "DataWhisperer", "CodeNova", "PipelineX",
            "TradeMancer", "InsightForge", "NetPulse", "CryptoLens",
            "AuditHawk", "SpecForge", "GrowthVane", "DeepScout",
        ]
        self.transactions: list[dict] = []
        self.channels: list[dict] = []
        self.events: list[dict] = []
        # Lottery economic actor (TEST-mode live financial flows for the monitor).
        self.lottery = {
            "round": 1, "pool": 0.0, "payouts": 0.0, "players": 0,
            "opex": 0.0, "funding": 0.0, "last_winner": "",
        }

    def _lot_event(self, agent: str, action: str, target: str, amount: float, t: int) -> None:
        """Emit a lottery financial-flow event into the activity stream."""
        self.events.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "agent": agent, "action": action, "target": target,
            "amount": round(float(amount), 4), "token": "USDC",
            "id": f"lot_{t}_{len(self.events)}",
        })
        if len(self.events) > 200:
            self.events = self.events[-200:]

    def step(self) -> dict:
        """Advance simulation one tick, return full state snapshot."""
        self.tick += 1
        t = self.tick

        # ---- HUB metrics ----
        peers = 3 + (t % 7)
        capabilities = 120 + t * 2 + random.randint(-3, 5)
        channels_open = 45 + (t % 20) + random.randint(0, 3)
        invocations = 340 + t * 12 + random.randint(-20, 30)

        # ---- FACTORY metrics ----
        products = 89 + t + random.randint(0, 2)
        tasks_pending = random.randint(3, 15)
        tasks_done = 450 + t * 3 + random.randint(-5, 10)

        # ---- MESH metrics ----
        agents = 23 + (t % 5)
        tasks = 120 + t * 2
        activity = 890 + t * 20 + random.randint(-30, 50)

        # ---- ESCROW metrics ----
        evm_channels = 32 + (t % 8)
        evm_tvl = 45000 + t * 500 + random.randint(-2000, 3000)
        sol_channels = 18 + (t % 5)
        sol_tvl = 22000 + t * 300 + random.randint(-1000, 2000)

        # ---- NFT ----
        minted = 15 + (t // 3)
        holders = 8 + (t // 4)

        # ---- Desktop ----
        apps_online = random.randint(2, 9)

        # ---- ACEX ----
        volume = 12000 + t * 800 + random.randint(-1000, 3000)
        listings = 45 + (t // 2)

        # ---- Federation ----
        fed_peers = 4 + (t % 6)
        crawls = 12 + t

        # ---- Blockchains ----
        gas = random.randint(15, 80)
        block = 21000000 + t * 5 + random.randint(0, 2)
        slot = 280000000 + t * 20 + random.randint(0, 10)
        tps = random.randint(1200, 3500)

        # ---- Generate new activity events ----
        if t % 3 == 0:
            agent = random.choice(self.agent_names)
            action = random.choice(["invoke", "discover", "channel_open", "channel_close", "settle"])
            target = random.choice(["hub", "mesh", "factory", "evm_escrow", "solana_escrow"])
            amount = round(random.uniform(0.05, 25.0), 2) if action in ("invoke", "settle", "channel_open") else 0
            self.events.append({
                "ts": datetime.now(timezone.utc).isoformat(),
                "agent": agent,
                "action": action,
                "target": target,
                "amount": amount,
                "token": random.choice(["USDT", "USDC"]),
                "id": f"evt_{t}_{len(self.events)}",
            })
            # Keep last 200 events
            if len(self.events) > 200:
                self.events = self.events[-200:]

        # ---- Simulate transactions flowing ----
        if t % 2 == 0:
            tx = {
                "id": f"tx_{t}_{random.randint(1000, 9999)}",
                "from": random.choice(self.agent_names),
                "to": random.choice(["hub", "CapabilityComposer", "CodeNova", "DataWhisperer"]),
                "amount": round(random.uniform(0.1, 50.0), 2),
                "token": random.choice(["USDT", "USDC"]),
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            self.transactions.append(tx)
            if len(self.transactions) > 100:
                self.transactions = self.transactions[-100:]

        # ---- LOTTERY (economic actor: Hub-sponsored, consumes oracles, agents play) ----
        # A real relayer feed (POST /api/lottery/update) overrides the simulation.
        lot = self.lottery
        if not apply_live_lottery(self):
            lot["players"] = 3 + (t % 9)
            ticket_in = round(random.uniform(0.5, 3.0), 2)
            lot["pool"] = round(lot["pool"] + ticket_in * 0.8, 2)    # 80% of tickets → prize
            lot["opex"] = round(lot["opex"] + ticket_in * 0.12, 4)   # 12% → opex (pays oracles)
            if t % 2 == 0:
                self._lot_event(random.choice(self.agent_names), "ticket", "lottery", round(random.uniform(1, 3), 2), t)
            if t % 4 == 0:  # Hub altruistic sponsor tithe → its bound lottery only
                tithe = round(2 + (t % 7) * 1.5, 2)
                lot["pool"] = round(lot["pool"] + tithe, 2)
                lot["funding"] = round(lot["funding"] + tithe, 2)
                self._lot_event("Hub", "sponsor", "lottery", tithe, t)
            if t % 5 == 0:  # opex out → pays an oracle for the draw
                self._lot_event("lottery", "invoke", random.choice(["Chronos", "Platon", "Lumen"]), round(random.uniform(0.004, 0.02), 3), t)
            if t % 10 == 0 and lot["pool"] > 0:  # draw → pay the winner (prize flow)
                winner = random.choice(self.agent_names)
                prize = lot["pool"]
                lot["payouts"] = round(lot["payouts"] + prize, 2)
                lot["last_winner"] = winner
                self._lot_event("lottery", "prize", winner, prize, t)
                lot["pool"] = 0.0
                lot["round"] += 1

        # Build nodes with updated metrics
        nodes, links = build_topology()
        from oracle_family import append_oracle_family_graph

        append_oracle_family_graph(nodes, links)
        ensure_factory_clusters(nodes, links, APP_URL, catalog_timeout=8.0)
        for node in nodes:
            nid = node["id"]
            if nid == "hub":
                node["metrics"] = {
                    "peers": peers, "capabilities": capabilities,
                    "channels_open": channels_open, "invocations_24h": invocations,
                }
                node["status"] = "active"
            elif nid == "factory":
                node["metrics"] = {
                    "products": products, "tasks_pending": tasks_pending, "tasks_done": tasks_done,
                }
                node["status"] = "active"
            elif nid == "mesh":
                node["metrics"] = {"agents": agents, "tasks": tasks, "activity": activity}
                node["status"] = "active"
            elif nid == "acex":
                node["metrics"] = {"volume_24h": volume, "listings": listings}
                node["status"] = "active"
            elif nid == "evm_escrow":
                node["metrics"] = {"channels": evm_channels, "tvl": evm_tvl, "chain": "ethereum"}
                node["status"] = "active"
            elif nid == "solana_escrow":
                node["metrics"] = {"channels": sol_channels, "tvl": sol_tvl, "chain": "solana"}
                node["status"] = "active"
            elif nid == "nft_contract":
                node["metrics"] = {"minted": minted, "holders": holders}
                node["status"] = "active"
            elif nid == "desktop_apps":
                node["metrics"]["apps_online"] = apps_online
                node["status"] = "active" if apps_online > 0 else "idle"
            elif nid == "plugins":
                node["metrics"]["loaded"] = 12 + (t % 4)
                node["status"] = "active"
            elif nid == "federation":
                node["metrics"] = {"peers": fed_peers, "crawls": crawls}
                node["status"] = "active"
            elif nid == "widget":
                node["metrics"]["impressions"] = 1500 + t * 50 + random.randint(-100, 200)
                node["status"] = "active"
            elif nid == "ethereum":
                node["metrics"] = {"gas": gas, "block": block}
                node["status"] = "active"
            elif nid == "solana":
                node["metrics"] = {"slot": slot, "tps": tps}
                node["status"] = "active"
            elif nid == "cli":
                node["metrics"]["commands"] = 45 + t * 2
                node["status"] = "active"
            elif nid.startswith("sdk_"):
                node["status"] = "active"
            elif nid == "lottery":
                node["metrics"] = {
                    "prize_pool_usd": round(self.lottery["pool"], 2),
                    "round": self.lottery["round"],
                    "players": self.lottery["players"],
                    "payouts_24h": round(self.lottery["payouts"], 2),
                    "opex_24h": round(self.lottery["opex"], 2),
                    "funding_24h": round(self.lottery["funding"], 2),
                }
                node["status"] = "active"

        # Add some random "pulse" events
        if t % 7 == 0:
            # Simulate a channel opening
            channel_id = f"ch_{t}_{random.randint(100, 999)}"
            self.channels.append({
                "id": channel_id,
                "agent": random.choice(self.agent_names),
                "amount": round(random.uniform(10, 200), 2),
                "token": random.choice(["USDT", "USDC"]),
                "status": "open",
                "ts": datetime.now(timezone.utc).isoformat(),
            })
            if len(self.channels) > 50:
                self.channels = self.channels[-50:]

        return {
            "tick": t,
            "ts": datetime.now(timezone.utc).isoformat(),
            "nodes": nodes,
            "links": links,
            "events": self.events[-20:],
            "transactions": self.transactions[-20:],
            "channels": self.channels[-10:],
            "summary": {
                "total_invocations_24h": invocations,
                "total_volume_usd": volume,
                "active_channels": channels_open + evm_channels + sol_channels,
                "tvl_usd": evm_tvl + sol_tvl,
                "agents_online": agents,
                "apps_online": apps_online,
                "tps_solana": tps,
                "gas_gwei": gas,
                "mode": "test",
                "tick": t,
            },
        }


# ---------------------------------------------------------------------------
# Real-mode data fetcher
# ---------------------------------------------------------------------------


def _merge_discovered(nodes: list[dict], links: list[dict], disc: dict) -> None:
    """Fold hub-discovered federation nodes/links into the graph (dedupe by id)."""
    from oracle_family import merge_discovered_peers

    merge_discovered_peers(nodes, links, disc)


async def fetch_real_metrics() -> dict:
    """Gather live metrics from ecosystem HTTP APIs + on-chain RPC."""
    global _real_tick
    _real_tick += 1
    t = _real_tick

    result: dict = {"mode": "real", "errors": [], "components": {}}

    async with httpx.AsyncClient(timeout=8.0) as client:
        # Hub stats
        try:
            r = await client.get(f"{HUB_URL}/ai-market/v2/stats/live")
            if r.status_code == 200:
                result["components"]["hub"] = r.json()
            else:
                result["errors"].append(f"hub returned {r.status_code}")
        except Exception as e:
            result["errors"].append(f"hub unreachable: {e}")

        # Mesh stats
        try:
            r = await client.get(f"{MESH_URL}/v1/stats")
            if r.status_code == 200:
                result["components"]["mesh"] = r.json()
            else:
                result["errors"].append(f"mesh returned {r.status_code}")
        except Exception as e:
            result["errors"].append(f"mesh unreachable: {e}")

        # App health
        try:
            r = await client.get(f"{APP_URL}/api/health")
            if r.status_code == 200:
                result["components"]["factory"] = r.json()
            else:
                result["errors"].append(f"factory returned {r.status_code}")
        except Exception as e:
            result["errors"].append(f"factory unreachable: {e}")

        # Prometheus query — pipeline tasks
        try:
            r = await client.get(
                f"{PROM_URL}/api/v1/query",
                params={"query": "pipeline_tasks_total"},
            )
            if r.status_code == 200:
                result["components"]["prometheus"] = r.json()
            else:
                result["errors"].append(f"prometheus returned {r.status_code}")
        except Exception as e:
            result["errors"].append(f"prometheus unreachable: {e}")

    # On-chain RPC (EVM + Solana) — same env as AI-Factory
    try:
        chain_snapshot = await fetch_onchain_snapshot()
        result["components"]["blockchain"] = chain_snapshot
        result["errors"].extend(chain_snapshot.get("errors") or [])
    except Exception as e:
        chain_snapshot = {"errors": [f"blockchain poll failed: {e}"]}
        result["components"]["blockchain"] = chain_snapshot
        result["errors"].append(str(e))

    nodes, links = build_topology()
    from oracle_family import append_oracle_family_graph, poll_oracle_family_nodes

    append_oracle_family_graph(nodes, links)
    for node in nodes:
        node["status"] = "unknown"
        cid = node["id"]
        if cid in result.get("components", {}):
            node["status"] = "active"

    hub_payload = result["components"].get("hub") or {}
    events, hub_hints = hub_events_to_activity(hub_payload if isinstance(hub_payload, dict) else {})
    mesh_stats = result["components"].get("mesh")
    if isinstance(mesh_stats, dict) and "hub" in {n["id"] for n in nodes}:
        hub_node = next(n for n in nodes if n["id"] == "hub")
        if hub_hints.get("invocations_24h"):
            hub_node["metrics"]["invocations_24h"] = hub_hints["invocations_24h"]
        if hub_hints.get("channels_open"):
            hub_node["metrics"]["channels_open"] = hub_hints["channels_open"]
        if result["components"].get("hub"):
            hub_node["status"] = "active"

    if isinstance(mesh_stats, dict):
        mesh_node = next((n for n in nodes if n["id"] == "mesh"), None)
        if mesh_node:
            mesh_node["status"] = "active"
            mesh_node["metrics"]["agents"] = int(
                mesh_stats.get("agents") or mesh_stats.get("agents_online") or 0
            )
            mesh_node["metrics"]["tasks"] = int(mesh_stats.get("tasks") or mesh_stats.get("tasks_total") or 0)
            mesh_node["metrics"]["activity"] = int(mesh_stats.get("activity") or 0)

    if result["components"].get("factory"):
        factory_node = next((n for n in nodes if n["id"] == "factory"), None)
        if factory_node:
            factory_node["status"] = "active"

    # Fail fast on slow /api/products — /categories fallback is ~300ms.
    ensure_factory_clusters(nodes, links, APP_URL, catalog_timeout=3.0)

    apply_chain_metrics_to_nodes(nodes, chain_snapshot)

    # Federation auto-discovery — render hub peers (e.g. Platon) as graph nodes
    # with live /api/health metrics. Never let discovery break the snapshot.
    try:
        from hub_discovery import discover_cached_async
        disc = await discover_cached_async(HUB_URL)
        _merge_discovered(nodes, links, disc)
        if disc.get("events"):
            events = list(disc["events"]) + events
        result["errors"].extend(disc.get("errors") or [])
    except Exception as e:  # pragma: no cover - defensive
        result["errors"].append(f"discovery failed: {e}")

    if t == 1 or t % 4 == 0:
        poll_oracle_family_nodes(nodes)

    apply_lottery_metrics(nodes, hub_hints=hub_hints, mesh_stats=mesh_stats if isinstance(mesh_stats, dict) else None)

    from argus_status import apply_argus_graph

    apply_argus_graph(nodes, mode="real")

    summary = build_real_summary(
        tick=t,
        hub_hints=hub_hints,
        mesh_stats=mesh_stats if isinstance(mesh_stats, dict) else None,
        chain=chain_snapshot,
    )

    return {
        "tick": t,
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": "real",
        "errors": result["errors"],
        "components": result["components"],
        "nodes": nodes,
        "links": links,
        "events": events,
        "transactions": [],
        "channels": [],
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# AI Assistant
# ---------------------------------------------------------------------------

ECOSYSTEM_CONTEXT = """
You are the Alien Monitor AI — navigator and expert for the real-time 3D
ecosystem map (AIMarket / AI-Factory). You know every node, link, mode, and
metric. Guide the user: what to click, where clusters sit, what LIVE vs UNI
means, and how factory catalog maps to orange star clusters near Factory.

## Ecosystem components you know about:

### AIMarket Hub (port 9083)
Federated capability catalog + micropayment routing. Endpoints:
- GET /.well-known/ai-market.json — root discovery
- GET /ai-market/v2/manifest — signed capability catalog
- GET /ai-market/v2/search?intent=...&budget=... — NL federated search
- POST /ai-market/v2/invoke — invoke capability (plugin hooks, safety gate)
- POST /ai-market/v2/channel/open — open pre-funded payment channel
- POST /ai-market/v2/channel/close — close channel, settle + refund
- GET /ai-market/v2/federation/peers — known peers + trust scores
- GET /ai-market/v2/stats/live — real-time invocation feed
- GET /ai-market/v2/plugins — loaded plugin catalog

### AI-Factory (web/backend, port 9081)
Autonomous pipeline that designs, builds, tests, and publishes products.
- GET /api/health — health check
- GET /metrics — Prometheus metrics
- WS /api/admin/ws/metrics — admin metrics WebSocket

### AI Service Mesh (port 8090)
Autonomous agent discovery, zero-trust verification, escrow, and payment.
- GET /v1/stats — mesh statistics
- GET /v1/agents — list agents
- POST /v1/tasks — create task
- GET /v1/activity/stream — SSE activity stream

### ACEX (Agent Capital Exchange)
Capital markets for AI agents — ALP listings, CapShares, AgentNotes, Pulse AMM.

### Smart Contracts
- AIMarketEscrow (EVM): USDT/USDC payment channels, EIP-712 signatures
- AIMarketCapabilityNFT (EVM): ERC-721 transferable entitlements
- aimarket-escrow (Solana): Anchor-based payment channels (USDC)
- ZK Circuits: input-validity proofs (Circom + Groth16)

### Desktop Integrations (9 apps)
Flutter apps: Capability Composer, Cold Outreach Coach, Creator Algorithm Coach,
Discovery Prospector, Freelance Contract Reviewer, Interview Prep Coach,
Personal Finance Coach, Reputation Dashboard. Rust/Tauri: Local Security Audit.

### Plugins (15 total)
safety, tee, channels, streaming, reputation, auction, orchestrator,
nft, zk, provenance, mcp-packager, personas, promo, dataset, data-cap.

### SDKs
Dart (Flutter), TypeScript (Node/web), Rust (Tauri/CLI).

### Blockchains
EVM chains (Ethereum, Base, Arbitrum, Optimism, Polygon) + Solana.

### Federation-discovered nodes (group=oracle, violet)
Nodes that are NOT hardcoded — discovered automatically from the Hub's
GET /ai-market/v2/federation/peers and rendered when their /.well-known
categories include oracle / simulation / math-viz / randomness-beacon. Each
orbits the Federation node and shows live /api/health metrics. Example: the
**Platon Shadow Oracle** (external, http://78.17.126.214) — a 32D dynamical
shadow oracle whose metrics include κ (kappa, coupling) and order_parameter.

### Oracle family — 17 math-as-a-service oracles (group=oracle, violet)
All speak AIMarket Protocol v2 (signed manifest, /.well-known/ai-market.json,
/ai-market/v2/invoke, signed receipts, measured metrics). Six are built on a
shared oracle-core; Platon is a standalone federated service proxied in. A
unified **oracle-family** manifest (port 9400) aggregates all of them (~41
capabilities) — each capability keeps its product_id so receipts attribute per
oracle. Public portal: oracles.modelmarket.dev.
- **Platon** (port 9200) — a 32D coupled Stuart–Landau / Kuramoto "shadow
  universe": verifiable randomness (chaos-VRF), hash-chained beacon, commit→reveal
  (bias-resistant), 32D state snapshots, semantic steering (text → bifurcation
  params), Stiefel projection, chaos-prediction "dream", LLM math witness.
  Caps: platon.random/beacon/commit/reveal/state/steer/project/dream/oracle/ask/
  witnesses. Metrics κ (coupling) + order_parameter. NOTE: the Platon ORACLE is
  the engine; the "UMBRAL cave" is its separate frontend app — same engine, different surface.
- **Chronos** (9300) — Wesolowski Verifiable Delay Function (VDF) over an
  RSA-2048 modulus: enforced sequential squarings + Fiat–Shamir proof verifiable
  in ~15 ms. Caps: chronos.eval@v1 ($0.01), chronos.verify@v1 ($0.001). Non-parallelizable time / unbiasable beacon.
- **Lattice** (9301) — Halton / van der Corput low-discrepancy (quasi-random)
  sequences via radical inverse. Cap: lattice.sequence@v1 ($0.002). For
  quasi-Monte-Carlo and even space-filling sampling (no clumping).
- **Murmuration** (9302) — robust consensus aggregation: median, trimmed mean,
  Tukey biweight M-estimator + DeGroot power-iteration. Cap:
  murmuration.aggregate@v1 ($0.002). Byzantine / outlier-resistant fusion of agent estimates.
- **Lumen** (9303) — EigenTrust / PageRank reputation (this is exactly what the
  monitor's REP button visualizes). Cap: lumen.reputation@v1 ($0.005).
- **Colony** (9304) — Euclidean TSP: nearest-neighbour + 2-opt with an
  optimality-gap certificate against a recomputable lower bound. Cap:
  colony.optimize@v1 ($0.005).
- **Turing** (9305) — blue-noise sampling via Mitchell's best-candidate
  (max–min distance). Cap: turing.bluenoise@v1 ($0.002). Aliasing-free, low-variance point sets.

## Reputation & LUMEN (trust scoring)
The ecosystem scores trust with **LUMEN**, a reputation oracle that runs
**EigenTrust / PageRank** over a directed weighted trust graph (i trusts j):
reputation is the stationary distribution of a damped random walk (damping
d=0.85), so nodes *trusted by trusted nodes* rank highest and the (1-d) teleport
keeps sybil cliques from trapping rank mass. LUMEN is the oracle capability
`lumen.reputation@v1` (port 9303, ~$0.005/call): the caller supplies nodes +
weighted edges and LUMEN returns the PageRank score vector.

Scalar trust also lives in two places:
- the **reputation** plugin — a provider score from bond, success-rate, quality,
  disputes and slashes; and
- each federation peer's **trust_score** (age + bond + success-rate + volume),
  served at GET /ai-market/v2/federation/peers.

In this monitor UI there is a **Reputation button (REP)** next to the AI button.
It opens a LUMEN-style graph (glowing directed trust edges, light pulses flowing
toward the most-trusted "sun" node) computed by running the same PageRank kernel
over the LIVE ecosystem graph for the current mode. In LIVE/UNI the monitor's
GET /api/reputation/peers enriches it with real federation trust_score; in TEST
the graph is simulated, so the ranking is illustrative only. The graph hot-
switches whenever the user toggles TEST / UNI / LIVE.

## Current monitor modes
- TEST mode: Simulated vibrant ecosystem with fake agents, transactions, channels.
- UNI mode: Self-evolving universe — local chain + live Hub/Mesh/Factory. Phases:
  BOOTSTRAP (hub seeded, first products), EXPANSION (buyer active, funding),
  FEDERATION (new hubs spawn), MATURITY (steady-state economy).
  External AI buyer creates real demand. External funding injected periodically.
  Only the funding source is synthetic — everything else uses real infrastructure.
- LIVE mode: Real production infrastructure with on-chain RPC.

## 3D map navigation (Alien Monitor UI)
- Click any glowing node to fly the camera there and keep focus until the panel closes.
- Hub is the center; Factory sits in the core nebula. Factory catalog items appear as
  **star clusters** (group=cluster): one nebula per category/templates, many small
  stars inside, spaced on a spiral so clusters never overlap. Open a cluster panel
  to see up to 80 product names in children[].
- LIVE: clusters sync from GET {factory}/api/products each tick.
- UNI: catalog imported on start; new pipeline products via materialize API, then collapsed to clusters.
- TEST: simulated nodes only.

Answer concisely but thoroughly. You receive a LIVE MONITOR SNAPSHOT JSON on every
request — treat it as ground truth for tick, mode, per-node metrics, and recent
transactions/events. If monitor_mode is test, note simulated data. In universe
mode, use scenario.phase from the snapshot.
"""


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Alien Monitor", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(MonitorBasePathMiddleware)

_MONITOR_AUTH = [Depends(require_monitor_auth)]

simulator = EcosystemSimulator()
_real_tick = 0

# Universe mode
universe: VirtualUniverse | None = None

def get_universe() -> VirtualUniverse:
    global universe
    if universe is None:
        universe = VirtualUniverse()
    return universe

# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health():
    sm = get_server_mode()
    body: dict = {"status": "ok", "mode": sm}
    if sm == "universe":
        u = get_universe()
        body["blockchain_ready"] = u.blockchain_ready
        body["contracts"] = {
            "evm_usdt": u.evm_usdt_address,
            "evm_escrow": u.evm_escrow_address,
            "evm_nft": u.evm_nft_address,
            "evm_lottery": u.evm_lottery_address,
            "solana_lottery": u.solana_lottery_program_id,
        }
        if _universe_bootstrap is not None:
            body["bootstrap"] = _universe_bootstrap
    return body


@app.get("/api/chain/status")
async def chain_status():
    """On-chain RPC + contract deployment snapshot (LIVE mode helper)."""
    return await fetch_onchain_snapshot()


def _universe_fast_snapshot() -> dict:
    """Seed graph without network polls — used while the broadcaster warms up."""
    u = get_universe()
    from argus_status import apply_argus_graph
    from factory_products import collapse_graph_products

    raw_nodes = [ent.to_node() for ent in u.entities.values()]
    raw_links = u.get_topology_links()
    graph_nodes, graph_links = collapse_graph_products(raw_nodes, raw_links)
    apply_argus_graph(graph_nodes, mode="universe")
    ensure_factory_clusters(graph_nodes, graph_links, APP_URL, catalog_timeout=5.0)
    return {
        "tick": u.tick,
        "ts": datetime.now(timezone.utc).isoformat(),
        "nodes": graph_nodes,
        "links": graph_links,
        "events": [],
        "transactions": [],
        "channels": [],
        "summary": {
            "mode": "universe",
            "tick": u.tick,
            "blockchain_ready": u.blockchain_ready,
            "entities_total": len(u.entities),
        },
    }


async def _fetch_monitor_state(effective_mode: str | None = None) -> dict:
    """Current ecosystem snapshot for REST, WebSocket, and AI context."""
    mode = _normalize_mode(effective_mode) or get_server_mode()
    async with _state_fetch_lock:
        if mode == "universe":
            state = await asyncio.to_thread(get_universe().tick_universe)
        elif mode == "real":
            state = await fetch_real_metrics()
        else:
            state = await asyncio.to_thread(simulator.step)
        return state


def _cached_monitor_state(mode: str | None = None) -> dict | None:
    effective = _normalize_mode(mode) or get_server_mode()
    cached = LAST_MONITOR_STATES.get(effective)
    if cached and cached.get("nodes"):
        return cached
    return None


def _slim_state_for_ws(state: dict) -> dict:
    """Drop bulky debug fields from WebSocket payloads (REST /api/state unchanged)."""
    if not isinstance(state, dict):
        return state
    slim = dict(state)
    slim.pop("components", None)
    return slim


async def _monitor_broadcaster() -> None:
    """Single background ticker — avoids blocking HTTP/AI on sync universe ticks."""
    await asyncio.sleep(0.3)
    while True:
        try:
            global LAST_MONITOR_STATE, LAST_MONITOR_STATES
            modes_needed: set[str] = {get_server_mode()}
            modes_needed.update(_ws_client_modes.values())
            states: dict[str, dict] = {}
            for tick_mode in modes_needed:
                states[tick_mode] = await _fetch_monitor_state(tick_mode)
            LAST_MONITOR_STATES.update(states)
            LAST_MONITOR_STATE = states.get(get_server_mode())
            dead: list = []
            for ws in list(CONNECTED_CLIENTS):
                client_mode = _ws_client_modes.get(id(ws), get_server_mode())
                state = states.get(client_mode) or LAST_MONITOR_STATE
                if not state:
                    continue
                payload = json.dumps(
                    {"type": "state_update", "data": _slim_state_for_ws(state)},
                    default=str,
                )
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                CONNECTED_CLIENTS.discard(ws)
                _ws_client_modes.pop(id(ws), None)
        except Exception:
            pass
        await asyncio.sleep(STATE_TICK_INTERVAL)


def _broadcaster_enabled() -> bool:
    return os.getenv("ALIEN_DISABLE_BROADCASTER", "").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    )


@app.on_event("startup")
async def _on_startup() -> None:
    global _universe_bootstrap
    if get_server_mode() == "test":
        logger.warning(
            "Alien Monitor running in TEST mode (ALIEN_MODE=test): all nodes, "
            "agents, transactions, channels and summary metrics are SIMULATED "
            "(random data) — do NOT treat these numbers as real ecosystem "
            "activity. Set ALIEN_MODE=real or ALIEN_MODE=universe for live data."
        )
    if get_server_mode() == "universe" and os.getenv("ALIEN_UNIVERSE_AUTO_START", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    ):
        try:
            _universe_bootstrap = await asyncio.to_thread(get_universe().bootstrap)
            if not _universe_bootstrap.get("ok"):
                logger.error("UNI bootstrap failed: %s", _universe_bootstrap.get("error"))
            else:
                logger.info(
                    "UNI bootstrap OK — escrow=%s usdt=%s",
                    _universe_bootstrap.get("evm_escrow"),
                    _universe_bootstrap.get("evm_usdt"),
                )
        except Exception as exc:
            _universe_bootstrap = {"ok": False, "error": str(exc)}
            logger.exception("UNI bootstrap crashed")
    if _broadcaster_enabled():
        asyncio.create_task(_monitor_broadcaster())


@app.on_event("shutdown")
async def _on_shutdown() -> None:
    """Stop host-network Anvil/Solana so restarts do not accumulate orphans."""
    if get_server_mode() == "universe":
        try:
            await asyncio.to_thread(get_universe().stop_blockchain)
        except Exception:
            logger.exception("UNI chain shutdown failed")


@app.get("/api/state", dependencies=[Depends(require_monitor_state_auth)])
async def get_state(mode: str | None = None):
    """Return current full state snapshot (optional ?mode= for UI session override)."""
    effective = _normalize_mode(mode) or get_server_mode()
    cached = _cached_monitor_state(effective)
    if cached:
        return cached
    if effective == "universe" and get_universe().entities:
        return await asyncio.to_thread(_universe_fast_snapshot)
    return await _fetch_monitor_state(effective)


@app.get("/api/summary", dependencies=[Depends(require_monitor_read_auth)])
async def get_summary():
    """Return lightweight summary for headers/badges."""
    if LAST_MONITOR_STATE and isinstance(LAST_MONITOR_STATE.get("summary"), dict):
        return LAST_MONITOR_STATE["summary"]
    sm = get_server_mode()
    if sm == "universe":
        state = await asyncio.to_thread(get_universe().tick_universe)
        return state["summary"]
    if sm == "real":
        data = await fetch_real_metrics()
        return data.get("summary", {"mode": "real"})
    state = await asyncio.to_thread(simulator.step)
    return state["summary"]


@app.get("/api/topology", dependencies=[Depends(require_monitor_read_auth)])
async def get_topology():
    """Return graph topology (nodes + links) with current metrics."""
    sm = get_server_mode()
    if sm == "universe":
        u = get_universe()
        nodes = [e.to_node() for e in u.entities.values()]
        links = u.get_topology_links()
        return {"nodes": nodes, "links": links}

    nodes, links = build_topology()
    if sm == "test":
        state = simulator.step()
        smap = {n["id"]: n for n in state["nodes"]}
        for node in nodes:
            if node["id"] in smap:
                node["metrics"] = smap[node["id"]]["metrics"]
                node["status"] = smap[node["id"]]["status"]
    elif sm == "real":
        data = await fetch_real_metrics()
        smap = {n["id"]: n for n in data["nodes"]}
        for node in nodes:
            if node["id"] in smap:
                node["metrics"] = smap[node["id"]]["metrics"]
                node["status"] = smap[node["id"]]["status"]
    return {"nodes": nodes, "links": links}


@app.get("/api/universe/status", dependencies=_MONITOR_AUTH)
async def universe_status():
    """Status of the UNI ecosystem runtime."""
    u = get_universe()
    status = {
        "running": u.running,
        "blockchain_ready": u.blockchain_ready,
        "tick": u.tick,
        "entities": len(u.entities),
        "products": len(u.products),
        "agents": len(u.agents),
        "transactions": len(u.transactions),
        "evm_rpc": u.evm_rpc if u.blockchain_ready else None,
        "solana_rpc": u.solana_rpc if u.blockchain_ready else None,
        "evm_escrow": u.evm_escrow_address,
        "mode": get_server_mode(),
    }
    if u._scenario_engine is not None:
        status["scenario"] = {
            "phase": u._scenario_engine.phase,
            "phase_progress": u._scenario_engine.get_phase_progress(u),
            "tick_count": u._scenario_engine.tick_count,
            "funding_total": u._scenario_engine.funding_stream.total_funding,
            "hub_count": len(u._scenario_engine.hub_spawner.spawned_hubs),
            "buyer_rounds": u._scenario_engine.external_buyer.rounds_completed,
        }
    try:
        import httpx

        r = httpx.get(f"{APP_URL}/api/uni/economy/summary", timeout=4.0)
        if r.status_code == 200:
            status["uni_economy"] = r.json()
    except Exception:
        pass
    return status


@app.get("/api/universe/scenario", dependencies=_MONITOR_AUTH)
async def universe_scenario():
    """Scenario engine status and configuration."""
    u = get_universe()
    if u._scenario_engine is None:
        return {"ok": False, "error": "Scenario engine not initialized"}
    se = u._scenario_engine
    return {
        "ok": True,
        "phase": se.phase,
        "phase_color": se.phase if hasattr(se, 'phase') else "#00f0ff",
        "phase_progress": se.get_phase_progress(u),
        "tick_count": se.tick_count,
        "funding_total": se.funding_stream.total_funding,
        "hub_count": len(se.hub_spawner.spawned_hubs),
        "buyer_rounds": se.external_buyer.rounds_completed,
        "total_invocations": se.total_invocations,
        "funding_stats": se.funding_stream.get_stats(),
        "spawned_hubs": se.hub_spawner.spawned_hubs,
    }


@app.get("/api/universe/funding/history", dependencies=_MONITOR_AUTH)
async def universe_funding_history():
    """Funding stream history."""
    u = get_universe()
    if u._scenario_engine is None:
        return {"ok": False, "error": "Scenario engine not initialized"}
    fs = u._scenario_engine.funding_stream
    return {
        "ok": True,
        "total_funding": fs.total_funding,
        "rounds": fs.rounds,
        "stats": fs.get_stats(),
    }


@app.post("/api/universe/start", dependencies=_MONITOR_AUTH)
async def universe_start():
    """Start UNI: local chain, contract deploy, live layer polling."""
    global _runtime_server_mode, _universe_bootstrap
    _runtime_server_mode = "universe"
    _universe_bootstrap = await asyncio.to_thread(get_universe().bootstrap)
    return _universe_bootstrap


@app.post("/api/universe/stop", dependencies=_MONITOR_AUTH)
async def universe_stop():
    """Stop UNI runtime and local chain processes."""
    global _runtime_server_mode
    _runtime_server_mode = "test"
    u = get_universe()
    u.stop_blockchain()
    u.running = False
    return {"ok": True}


@app.post("/api/universe/materialize", dependencies=_MONITOR_AUTH)
async def universe_materialize(body: dict):
    """
    Factory webhook — called when AI-Factory creates a product.
    A new planet materializes in the 3D universe.

    Body: { "name": "...", "type": "...", "category": "...", ... }
    """
    u = get_universe()
    entity = u.materialize_product(body)
    return {
        "ok": True,
        "entity": entity.to_node(),
        "total_products": len(u.products),
    }


@app.post("/api/universe/materialize/batch", dependencies=_MONITOR_AUTH)
async def universe_materialize_batch(body: dict):
    """Materialize multiple products at once."""
    u = get_universe()
    products = body.get("products", [])
    results = []
    for p in products:
        entity = u.materialize_product(p)
        results.append(entity.to_node())
    return {"ok": True, "entities": results, "total_products": len(u.products)}


@app.get("/api/universe/state", dependencies=_MONITOR_AUTH)
async def universe_state():
    """Get full UNI ecosystem state snapshot."""
    u = get_universe()
    return u.tick_universe()


@app.post("/api/lottery/update", dependencies=_MONITOR_AUTH)
async def lottery_update(body: dict):
    """Ingest a live economy snapshot + recent financial-flow events from the
    AI-Agent Oracle Lottery relayer. While the feed is fresh (< LIVE_LOTTERY_TTL),
    the monitor renders these REAL values on the `lottery` node instead of the
    simulation, so the lottery's money flows are visible live.

    Body: {mode, last_winner,
           metrics:{prize_pool_usd, round, players, payouts_24h, opex_24h, funding_24h},
           events:[{ts, agent, action, target, amount, token, id}, …]}
    """
    set_live_lottery(body)
    from live_lottery_feed import _LIVE_LOTTERY

    return {"ok": True, "fresh_ttl_s": LIVE_LOTTERY_TTL, "round": _LIVE_LOTTERY["metrics"].get("round", 0)}


@app.post("/api/argus/run", dependencies=_MONITOR_AUTH)
async def argus_run_update(body: dict):
    """Ingest a live verifiable run from ARGUS for the graph node detail panel."""
    from argus_feed import ARGUS_RUN_TTL, set_argus_run

    set_argus_run(body)
    return {"ok": True, "fresh_ttl_s": ARGUS_RUN_TTL, "run_id": str(body.get("id", ""))[:64]}


@app.get("/api/reputation/peers", dependencies=_MONITOR_AUTH)
async def reputation_peers():
    """Federation trust enrichment for the monitor's reputation graph.

    Passthrough to the Hub's federated peer list, surfacing each peer's real
    scalar ``trust_score`` (age + bond + success-rate + volume) so the reputation
    graph can weight LIVE/UNI nodes by real trust, not topology alone. Fail-soft:
    any Hub error returns an empty peer list and the client falls back to pure
    structural PageRank. Disabled in TEST (the graph is simulated there anyway).
    """
    sm = get_server_mode()
    if sm == "test":
        return {"peers": [], "count": 0, "mode": sm, "source": "disabled-in-test"}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(f"{HUB_URL}/ai-market/v2/federation/peers")
        if r.status_code != 200:
            return {"peers": [], "count": 0, "mode": sm, "error": f"hub returned {r.status_code}"}
        data = r.json()
    except Exception as e:  # pragma: no cover - defensive, viz must not hard-fail
        return {"peers": [], "count": 0, "mode": sm, "error": f"hub unreachable: {e}"}

    peers = data.get("peers", []) if isinstance(data, dict) else []
    slim = [
        {
            "url": p.get("url"),
            "name": p.get("name"),
            "well_known_url": p.get("well_known_url"),
            "trust_score": p.get("trust_score"),
            "categories": p.get("categories"),
        }
        for p in peers
        if isinstance(p, dict)
    ]
    return {
        "peers": slim,
        "count": len(slim),
        "mode": sm,
        "source": f"{HUB_URL}/ai-market/v2/federation/peers",
    }


@app.get("/api/reputation/lumen", dependencies=_MONITOR_AUTH)
async def reputation_lumen():
    """Real consumer of the LUMEN reputation oracle (lumen.reputation@v1).

    Builds the current ecosystem trust graph (nodes + directed links) and asks the
    LUMEN oracle to compute EigenTrust / PageRank over it. The monitor's REP graph
    uses these real oracle scores when available and falls back to its local
    PageRank otherwise. Configure LUMEN_URL (the LUMEN oracle or the oracle-family
    endpoint). Fail-soft so the viz never hard-fails.
    """
    if not LUMEN_URL:
        return {"ok": False, "error": "LUMEN_URL not configured", "scores": [], "ids": []}
    state = LAST_MONITOR_STATE
    if not state:
        try:
            state = await _fetch_monitor_state()
        except Exception:
            state = None
    nodes = (state or {}).get("nodes") or []
    links = (state or {}).get("links") or []
    if not nodes:
        return {"ok": False, "error": "no monitor state", "scores": [], "ids": []}

    ids = [n.get("id") for n in nodes]
    index = {nid: i for i, nid in enumerate(ids)}
    edges: list[list] = []
    seen: set = set()
    for link in links:
        i = index.get(link.get("source"))
        j = index.get(link.get("target"))
        if i is None or j is None or i == j:
            continue
        key = (i, j)
        if key in seen:
            continue
        seen.add(key)
        edges.append([i, j, 1.0])

    payload = {"capability_id": "lumen.reputation@v1", "input": {"nodes": len(ids), "edges": edges, "damping": 0.85}}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{LUMEN_URL}/ai-market/v2/invoke", json=payload)
        if r.status_code != 200:
            return {"ok": False, "error": f"lumen returned {r.status_code}", "scores": [], "ids": ids}
        data = r.json() if r.content else {}
    except Exception as e:  # pragma: no cover - defensive, viz must not hard-fail
        return {"ok": False, "error": f"lumen unreachable: {e}", "scores": [], "ids": ids}

    out = {}
    if isinstance(data, dict):
        out = data.get("output") or data.get("result") or (data if "scores" in data else {})
    scores = out.get("scores") if isinstance(out, dict) else None
    if not isinstance(scores, list) or not scores:
        return {"ok": False, "error": "lumen returned no scores", "scores": [], "ids": ids}
    return {
        "ok": True,
        "scores": scores,
        "ids": ids,
        "source": f"{LUMEN_URL} · lumen.reputation@v1",
        "converged": out.get("converged"),
        "iterations": out.get("iterations"),
    }


@app.get("/api/ai/providers")
async def ai_providers():
    """LLM providers (same registry as aicom model_providers.yaml)."""
    return list_providers()


@app.post("/api/ai/ask", dependencies=_MONITOR_AUTH)
async def ai_ask(body: dict):
    """AI assistant — live state + multi-provider LLM (default: deepseek-v4-pro)."""
    question = (body.get("question") or "").strip()
    ui_locale = normalize_locale(body.get("locale", "en"))
    if not question:
        return {"answer": EMPTY_QUESTION[ui_locale]}

    response_locale = resolve_response_locale(question, ui_locale)

    state = body.get("state") if isinstance(body.get("state"), dict) else None
    if not state:
        state = LAST_MONITOR_STATE
    if state is None:
        try:
            state = await _fetch_monitor_state()
        except Exception:
            state = None

    selected_node = body.get("selected_node_id") or body.get("selected_node")
    live_ctx = build_live_context(state, MODE, str(selected_node) if selected_node else None)
    system = build_system_prompt(ECOSYSTEM_CONTEXT, response_locale, live_ctx)
    provider_id = body.get("provider") or body.get("provider_id")
    model_role = body.get("model_role") or "heavy"

    if not any_provider_configured():
        return {
            "answer": _fallback_answer(question, response_locale, state, MODE),
            "meta": {"provider": "fallback", "live_state": state is not None, "response_locale": response_locale},
        }

    try:
        answer, meta = await generate_answer(
            question=question,
            locale=response_locale,
            system_prompt=system,
            provider_id=provider_id,
            model_role=model_role,
        )
        meta["live_state"] = state is not None
        meta["ui_locale"] = ui_locale
        meta["response_locale"] = response_locale
        return {"answer": answer, "meta": meta}
    except Exception as e:
        fb = _fallback_answer(question, response_locale, state, MODE)
        return {
            "answer": fb + f"\n\n(LLM error: {e})",
            "meta": {"provider": "fallback", "error": str(e), "response_locale": response_locale},
        }


def _fallback_answer(
    question: str,
    locale: str = "en",
    state: dict | None = None,
    mode: str | None = None,
) -> str:
    q = question.lower()
    live_hint = ""
    if state:
        summary = state.get("summary") or {}
        tick = state.get("tick", summary.get("tick", "?"))
        m = (mode or summary.get("mode") or "unknown").upper()
        live_hint = f" [Сейчас: режим {m}, tick {tick}.]" if locale == "ru" else (
            f" [Now: mode {m}, tick {tick}.]" if locale == "en" else f" [Ahora: modo {m}, tick {tick}.]"
        )
    if locale == "ru":
        if "lumen" in q or "репутац" in q or "довер" in q or "trust" in q:
            return (
                "LUMEN — оракул репутации: EigenTrust/PageRank по графу доверия (i доверяет j), "
                "демпфирование d=0.85 — узлы, которым доверяют доверенные, ранжируются выше. "
                "Скалярный trust: плагин reputation + trust_score пиров федерации "
                "(/ai-market/v2/federation/peers). Кнопка РЕП в мониторе открывает этот граф "
                "по текущему режиму (TEST — симуляция, LIVE/UNI — реальный trust)."
                + live_hint
            )
        if "оракул" in q or "oracle" in q:
            return (
                "7 оракулов math-as-a-service (AIMarket v2, единый oracle-family порт 9400): "
                "Platon (32D-хаос: рандом/beacon/steering, 9200), Chronos (Wesolowski VDF, 9300), "
                "Lattice (последовательности Холтона, 9301), Murmuration (робастный консенсус, 9302), "
                "Lumen (репутация EigenTrust/PageRank, 9303), Colony (TSP с гарантией зазора, 9304), "
                "Turing (blue-noise сэмплинг, 9305). Портал: oracles.modelmarket.dev."
                + live_hint
            )
        if "hub" in q or "хаб" in q:
            return "AIMarket Hub — федеративный каталог AI-возможностей с маршрутизацией микроплатежей. Порт 9083. discover → channel → invoke → settle. 15 плагинов."
        if "channel" in q or "payment" in q or "канал" in q or "платеж" in q or "платёж" in q or "микроплат" in q:
            return (
                "Платёжные каналы — off-chain линии USDT/USDC: open (предоплата) → invoke → close (расчёт + возврат остатка). "
                "EVM: AIMarketEscrow + EIP-712; Solana: aimarket-escrow (Anchor, USDC). "
                "Эндпоинты Hub: POST /ai-market/v2/channel/open и /channel/close."
                + live_hint
            )
        if "contract" in q or "контракт" in q or "escrow" in q:
            return "Два эскроу: AIMarketEscrow (EVM) и aimarket-escrow (Solana). Каналы USDT/USDC. NFT ERC-721 для entitlements."
        if "plugin" in q or "плагин" in q:
            return "15 плагинов через entry_points 'aimarket.plugins': safety, TEE, channels, streaming, reputation, auction, orchestrator, NFT, ZK, provenance, MCP, personas, promo, dataset, data-cap."
        if "desktop" in q or "app" in q or "flutter" in q:
            return "9 десктопных приложений: 8 Flutter + 1 Rust/Tauri (Local Security Audit). Dart SDK к хабу."
        if "mesh" in q or "меш" in q:
            return "AI Service Mesh (8090): discovery, zero-trust, escrow, оркестрация агентов."
        if "acex" in q:
            return "ACEX — рынок капитала AI-агентов: ALP, CapShares, AgentNotes, Pulse AMM."
        if "sdk" in q:
            return "SDK: Dart, TypeScript, Rust. Протокол: discover → open_channel → invoke → close_channel → verify."
        if "mode" in q or "режим" in q or "test" in q or "tick" in q or "метрик" in q:
            return (
                f"Режим монитора: {(mode or MODE).upper()}. TEST — симуляция. UNI — локальная сеть + живые слои. LIVE — production."
                + live_hint
            )
        return "Спросите о хабе, контрактах, плагинах, десктопе, mesh, ACEX или SDK." + live_hint
    if locale == "es":
        if "lumen" in q or "reputac" in q or "confian" in q or "trust" in q:
            return (
                "LUMEN: oráculo de reputación con EigenTrust/PageRank sobre un grafo de confianza "
                "(i confía en j), amortiguación d=0.85 — los nodos en quienes confían los confiables "
                "puntúan más alto. Confianza escalar: plugin reputation + trust_score de los peers de "
                "federación (/ai-market/v2/federation/peers). El botón REP del monitor abre este grafo "
                "según el modo actual."
                + live_hint
            )
        if "oracle" in q or "orácul" in q or "oracul" in q:
            return (
                "7 oráculos math-as-a-service (AIMarket v2, unificados en oracle-family puerto 9400): "
                "Platon (caos 32D: aleatoriedad/beacon/steering, 9200), Chronos (VDF Wesolowski, 9300), "
                "Lattice (secuencias de Halton, 9301), Murmuration (consenso robusto, 9302), "
                "Lumen (reputación EigenTrust/PageRank, 9303), Colony (TSP con brecha de optimalidad, 9304), "
                "Turing (muestreo blue-noise, 9305). Portal: oracles.modelmarket.dev."
                + live_hint
            )
        if "hub" in q:
            return "AIMarket Hub: catálogo federado + micropagos. Puerto 9083. 15 plugins."
        if "channel" in q or "payment" in q or "canal" in q or "pago" in q or "micropago" in q:
            return (
                "Canales de pago: carriles off-chain USDT/USDC — open (prefondo) → invoke → close (liquidación + reembolso). "
                "EVM: AIMarketEscrow + EIP-712; Solana: aimarket-escrow (Anchor, USDC). "
                "Hub: POST /ai-market/v2/channel/open y /channel/close."
                + live_hint
            )
        if "contract" in q or "escrow" in q:
            return "Escrow EVM y Solana con canales USDT/USDC. NFT ERC-721."
        if "plugin" in q:
            return "15 plugins vía entry_points 'aimarket.plugins'."
        if "desktop" in q or "app" in q:
            return "9 apps de escritorio: 8 Flutter + 1 Rust/Tauri."
        if "mesh" in q:
            return "AI Service Mesh (8090): discovery, verificación, escrow."
        if "acex" in q:
            return "ACEX: mercado de capital para agentes AI."
        if "sdk" in q:
            return "SDK Dart, TypeScript y Rust con el mismo flujo de protocolo."
        if "mode" in q or "test" in q or "tick" in q:
            return f"Modo actual: {(mode or MODE).upper()}. TEST simula; UNI cadena local + capas vivas; LIVE producción." + live_hint
        return "Pregunta sobre hub, contratos, plugins, escritorio, mesh, ACEX o SDK." + live_hint
    # English
    if "lumen" in q or "reputation" in q or "trust" in q:
        return (
            "LUMEN is a reputation oracle: EigenTrust / PageRank over a directed trust graph "
            "(i trusts j) with damping d=0.85, so nodes trusted by trusted nodes rank highest. "
            "Scalar trust comes from the reputation plugin (bond, success-rate, quality, disputes, "
            "slashes) and each federation peer's trust_score (GET /ai-market/v2/federation/peers). "
            "The monitor's REP button opens this graph for the current mode — real federation trust "
            "in LIVE/UNI, simulated in TEST."
            + live_hint
        )
    if "oracle" in q:
        return (
            "Seventeen math-as-a-service oracles (AIMarket v2, portal oracles.modelmarket.dev): "
            "Platon (chaos randomness/beacon, 9200), Chronos (Wesolowski VDF, 9300), "
            "Lattice (Halton sequences, 9301), Murmuration (consensus, 9302), "
            "Lumen (EigenTrust/PageRank, 9303), Colony (TSP + gap certificate, 9304), "
            "Turing (blue-noise, 9305), Percola (percolation, 9306), Fermat (routing, 9307), "
            "Ablation (cascade-risk, 9308), Landauer (thermodynamic audit, 9309), "
            "Sortes (ECVRF randomness, 9310), Gauss (Gaussian-Process regression, 9311), "
            "Aestus (RSW time-lock puzzles, 9312), Betti (persistent homology, 9313), "
            "Kantor (optimal transport, 9314), Fourier (graph-spectral analysis, 9315)."
            + live_hint
        )
    if "hub" in q:
        return "AIMarket Hub is a federated AI capability catalog with micropayment routing on port 9083 (discover → channel → invoke → settle). 15 plugins loaded."
    if "channel" in q or "payment" in q or "micropayment" in q or "settle" in q:
        return (
            "Payment channels are off-chain USDT/USDC lanes: open (pre-fund) → invoke → close (settle + refund remainder). "
            "EVM uses AIMarketEscrow with EIP-712 signatures; Solana uses aimarket-escrow (Anchor, USDC). "
            "Hub endpoints: POST /ai-market/v2/channel/open and POST /ai-market/v2/channel/close."
            + live_hint
        )
    if "contract" in q or "escrow" in q:
        return "Two escrows: AIMarketEscrow (EVM) and aimarket-escrow (Solana), plus an ERC-721 NFT contract for transferable entitlements."
    if "plugin" in q:
        return "15 plugins via entry_points 'aimarket.plugins': safety, TEE, channels, streaming, reputation, auction, orchestrator, NFT, ZK, provenance, MCP, personas, promo, dataset, data-cap."
    if "desktop" in q or "app" in q or "flutter" in q:
        return "Nine desktop apps: eight Flutter integrations plus one Rust/Tauri security audit tool, all using the Dart SDK to reach the hub."
    if "mesh" in q:
        return "AI Service Mesh (8090) handles agent discovery, zero-trust verification, escrow, and orchestration."
    if "acex" in q:
        return "ACEX (Agent Capital Exchange) lists ALPs, CapShares, AgentNotes, and runs a Pulse AMM for AI agent capital."
    if "sdk" in q:
        return "Three SDKs — Dart, TypeScript, Rust — share discover → open_channel → invoke → close_channel → verify."
    if "mode" in q or "test" in q or "tick" in q or "metric" in q:
        return (
            f"Monitor mode: {(mode or MODE).upper()}. TEST simulates; UNI uses local chain + live Hub/Mesh/Factory/Prometheus; "
            "LIVE reads production RPC and services from .env."
            + live_hint
        )
    return "Ask about the hub, contracts, plugins, desktop apps, service mesh, ACEX, SDKs, or current ecosystem state." + live_hint


# ---------------------------------------------------------------------------
# WebSocket — real-time streaming
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    CONNECTED_CLIENTS.add(ws)
    _ws_client_modes[id(ws)] = get_server_mode()
    initial = _cached_monitor_state()
    if not initial and get_server_mode() == "universe" and get_universe().entities:
        initial = await asyncio.to_thread(_universe_fast_snapshot)
    if not initial:
        initial = await _fetch_monitor_state()
    if initial:
        await ws.send_text(json.dumps({
            "type": "state_update",
            "data": _slim_state_for_ws(initial),
        }, default=str))
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            cmd = msg.get("cmd", "")
            if cmd == "set_mode":
                if not monitor_control_token_valid(msg.get("token")):
                    await ws.send_text(json.dumps({
                        "type": "error",
                        "detail": "unauthorized",
                        "cmd": cmd,
                    }))
                    continue
                requested = _normalize_mode(str(msg.get("mode", "")).strip().lower())
                if requested:
                    _ws_client_modes[id(ws)] = requested
                client_mode = _ws_client_modes[id(ws)]
                if client_mode == "universe":
                    u = get_universe()
                    if not u.running or not u.blockchain_ready:
                        await asyncio.to_thread(u.bootstrap)
                    elif not u.entities:
                        await asyncio.to_thread(u.seed_entities)
                snap = _cached_monitor_state(client_mode)
                if not snap and client_mode == "universe" and get_universe().entities:
                    snap = await asyncio.to_thread(_universe_fast_snapshot)
                if snap:
                    await ws.send_text(json.dumps({
                        "type": "state_update",
                        "data": _slim_state_for_ws(snap),
                    }, default=str))
                await ws.send_text(json.dumps({"type": "mode_changed", "mode": client_mode}))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        CONNECTED_CLIENTS.discard(ws)
        _ws_client_modes.pop(id(ws), None)


# ---------------------------------------------------------------------------
# Serve static frontend in production
# ---------------------------------------------------------------------------

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIR.exists():
    # Vite base=/monitor/ — serve the same build under /monitor/ for direct :9100 access
    # (without nginx path rewrite, /monitor/assets/* would 404 and the UI stays black).
    app.mount("/monitor", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend_monitor")
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=(SERVER_MODE == "test"))


if __name__ == "__main__":
    main()
