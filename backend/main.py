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
import math
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
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

_MONITOR_ROOT = Path(__file__).resolve().parent.parent
_AICOM_ROOT = _MONITOR_ROOT.parent
load_dotenv(_AICOM_ROOT / ".env")
load_dotenv(_MONITOR_ROOT / ".env")
load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODE = os.getenv("ALIEN_MODE", "test")  # "test" | "real" | "universe"
PORT = int(os.getenv("ALIEN_PORT", "9100"))
HOST = os.getenv("ALIEN_HOST", "0.0.0.0")
HUB_URL = os.getenv("HUB_URL", "http://localhost:9083").rstrip("/")
MESH_URL = os.getenv("MESH_URL", "http://localhost:8090").rstrip("/")
PROM_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090").rstrip("/")
APP_URL = os.getenv("AICOM_API_URL", "http://localhost:9081").rstrip("/")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# ---------------------------------------------------------------------------
# Data models (hand-rolled, no pydantic to keep it light)
# ---------------------------------------------------------------------------

ECO_NODES: list[dict] = []
ECO_LINKS: list[dict] = []
ACTIVITY_LOG: list[dict] = []
METRICS_SNAPSHOT: dict = {}
CONNECTED_CLIENTS: set = set()

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
            "label": "Ethereum",
            "group": "chain",
            "icon": "chain",
            "description": "EVM L1 — Base, Arbitrum, Optimism, Polygon",
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

    return nodes, links


# ---------------------------------------------------------------------------
# Simulator — generates fake but realistic ecosystem activity
# ---------------------------------------------------------------------------


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

        # Build nodes with updated metrics
        nodes, _links = build_topology()
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
            "links": _links,
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

    apply_chain_metrics_to_nodes(nodes, chain_snapshot)

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
You are the Alien Monitor AI — a helpful assistant embedded in a real-time
ecosystem monitoring dashboard for AIMarket (AI-Factory). You answer questions
about the ecosystem components, architecture, and current state.

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

## Current monitor modes
- TEST mode: Simulated vibrant ecosystem with fake agents, transactions, channels.
- REAL mode: Live data from actual running infrastructure.

Answer concisely but thoroughly. If asked about metrics, mention current values
shown in the monitor. If the monitor is in TEST mode, remind the user that
data is simulated.
"""


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Alien Monitor", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    return {"status": "ok", "mode": MODE}


@app.get("/api/chain/status")
async def chain_status():
    """On-chain RPC + contract deployment snapshot (LIVE mode helper)."""
    return await fetch_onchain_snapshot()


@app.get("/api/state")
async def get_state():
    """Return current full state snapshot."""
    if MODE == "universe":
        u = get_universe()
        return u.tick_universe()
    if MODE == "real":
        return await fetch_real_metrics()
    return simulator.step()


@app.get("/api/summary")
async def get_summary():
    """Return lightweight summary for headers/badges."""
    if MODE == "universe":
        u = get_universe()
        state = u.tick_universe()
        return state["summary"]
    if MODE == "real":
        data = await fetch_real_metrics()
        return data.get("summary", {"mode": "real"})
    state = simulator.step()
    return state["summary"]


@app.get("/api/topology")
async def get_topology():
    """Return graph topology (nodes + links) with current metrics."""
    if MODE == "universe":
        u = get_universe()
        nodes = [e.to_node() for e in u.entities.values()]
        links = u.get_topology_links()
        return {"nodes": nodes, "links": links}

    nodes, links = build_topology()
    if MODE == "test":
        state = simulator.step()
        smap = {n["id"]: n for n in state["nodes"]}
        for node in nodes:
            if node["id"] in smap:
                node["metrics"] = smap[node["id"]]["metrics"]
                node["status"] = smap[node["id"]]["status"]
    elif MODE == "real":
        data = await fetch_real_metrics()
        smap = {n["id"]: n for n in data["nodes"]}
        for node in nodes:
            if node["id"] in smap:
                node["metrics"] = smap[node["id"]]["metrics"]
                node["status"] = smap[node["id"]]["status"]
    return {"nodes": nodes, "links": links}


@app.get("/api/universe/status")
async def universe_status():
    """Status of the UNI ecosystem runtime."""
    u = get_universe()
    return {
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
        "mode": MODE,
    }


@app.post("/api/universe/start")
async def universe_start():
    """Start UNI: local chain, contract deploy, live layer polling."""
    global MODE
    MODE = "universe"
    u = get_universe()
    u.running = True
    u.start_blockchain()
    u.deploy_contracts()
    u.seed_entities()
    return {
        "ok": True,
        "blockchain_ready": u.blockchain_ready,
        "entities": len(u.entities),
        "agents": len(u.agents),
    }


@app.post("/api/universe/stop")
async def universe_stop():
    """Stop UNI runtime and local chain processes."""
    global MODE
    MODE = "test"
    u = get_universe()
    u.stop_blockchain()
    u.running = False
    return {"ok": True}


@app.post("/api/universe/materialize")
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


@app.post("/api/universe/materialize/batch")
async def universe_materialize_batch(body: dict):
    """Materialize multiple products at once."""
    u = get_universe()
    products = body.get("products", [])
    results = []
    for p in products:
        entity = u.materialize_product(p)
        results.append(entity.to_node())
    return {"ok": True, "entities": results, "total_products": len(u.products)}


@app.get("/api/universe/state")
async def universe_state():
    """Get full UNI ecosystem state snapshot."""
    u = get_universe()
    return u.tick_universe()


@app.post("/api/ai/ask")
async def ai_ask(body: dict):
    """AI assistant — answer questions about the ecosystem."""
    question = body.get("question", "")
    if not question:
        return {"answer": "Please ask a question about the AIMarket ecosystem."}

    if not ANTHROPIC_API_KEY:
        # Fallback: rule-based answers
        return {"answer": _fallback_answer(question)}

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=ECOSYSTEM_CONTEXT,
            messages=[{"role": "user", "content": question}],
        )
        return {"answer": msg.content[0].text}
    except Exception as e:
        return {"answer": _fallback_answer(question) + f"\n\n(AI unavailable: {e})"}


def _fallback_answer(question: str) -> str:
    q = question.lower()
    if "hub" in q or "хаб" in q:
        return "AIMarket Hub — это федеративный каталог AI-возможностей с маршрутизацией микроплатежей. Порт 9083. Поддерживает discover → channel → invoke → settle. Содержит 15 плагинов."
    if "contract" in q or "контракт" in q or "escrow" in q:
        return "У нас два эскроу-контракта: AIMarketEscrow (EVM — Ethereum/Base/Arbitrum) и aimarket-escrow (Solana). Оба поддерживают платёжные каналы с USDT/USDC. Плюс NFT-контракт (ERC-721) для передаваемых entitlements."
    if "plugin" in q or "плагин" in q:
        return "15 плагинов: safety, TEE, channels, streaming, reputation, auction, orchestrator, NFT, ZK proofs, provenance, MCP packager, personas, promo, dataset, data-cap. Каждый подключается через entry_points 'aimarket.plugins'."
    if "desktop" in q or "app" in q or "flutter" in q:
        return "9 десктопных приложений: 8 на Flutter (Capability Composer, Coaches, Prospector, Dashboard) + 1 на Rust/Tauri (Local Security Audit). Все используют Dart SDK для связи с хабом."
    if "mesh" in q or "меш" in q:
        return "AI Service Mesh (порт 8090) — автономный discovery, zero-trust verification, escrow и оркестрация между AI-агентами. Как Airbnb для AI."
    if "acex" in q:
        return "ACEX (Agent Capital Exchange) — рынок капитала для AI-агентов: ALP листинги, CapShares, AgentNotes, Pulse AMM. Позволяет торговать долями в AI-возможностях."
    if "sdk" in q:
        return "Три SDK: Dart (Flutter), TypeScript (Node.js/браузер), Rust (Tauri/CLI). Все следуют протоколу: discover → open_channel → invoke → close_channel → verify."
    if "mode" in q or "режим" in q or "test" in q:
        return (
            f"Монитор сейчас в режиме: {MODE.upper()}. "
            "TEST — симуляция. UNI — локальная сеть + живые Hub/Mesh/Factory/Prometheus. "
            "LIVE — production RPC и сервисы из .env."
        )
    return "Я AI-помощник Инопланетного Монитора. Спросите о хабе, контрактах, плагинах, десктопных приложениях, AI Service Mesh, ACEX, SDK или о текущем состоянии экосистемы."


# ---------------------------------------------------------------------------
# WebSocket — real-time streaming
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    CONNECTED_CLIENTS.add(ws)
    try:
        while True:
            # Wait for client message (ping or mode switch request)
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=2.0)
                msg = json.loads(data)
                cmd = msg.get("cmd", "")
                if cmd == "set_mode":
                    global MODE
                    MODE = msg.get("mode", MODE)
                    await ws.send_text(json.dumps({"type": "mode_changed", "mode": MODE}))
            except asyncio.TimeoutError:
                pass  # No message, just push state

            # Push current state
            if MODE == "universe":
                u = get_universe()
                state = u.tick_universe()
            elif MODE == "real":
                state = await fetch_real_metrics()
            else:
                state = simulator.step()

            await ws.send_text(json.dumps({
                "type": "state_update",
                "data": state,
            }))

            await asyncio.sleep(1.5)  # ~0.67 Hz refresh — smooth but not overwhelming
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        CONNECTED_CLIENTS.discard(ws)


# ---------------------------------------------------------------------------
# Serve static frontend in production
# ---------------------------------------------------------------------------

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=(MODE == "test"))


if __name__ == "__main__":
    main()
