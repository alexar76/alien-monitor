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
from factory_products import fetch_factory_products_sync, merge_factory_products
from monitor_auth import cors_allow_origins, require_monitor_auth
from ai_assistant import (
    EMPTY_QUESTION,
    any_provider_configured,
    build_live_context,
    build_system_prompt,
    generate_answer,
    list_providers,
    normalize_locale,
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

MODE = os.getenv("ALIEN_MODE", "test")  # "test" | "real" | "universe"
PORT = int(os.getenv("ALIEN_PORT", "9100"))
HOST = os.getenv("ALIEN_HOST", "127.0.0.1")
HUB_URL = os.getenv("HUB_URL", "http://localhost:9083").rstrip("/")
MESH_URL = os.getenv("MESH_URL", "http://localhost:8090").rstrip("/")
PROM_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090").rstrip("/")
APP_URL = os.getenv("AICOM_API_URL", "http://localhost:9081").rstrip("/")

# ---------------------------------------------------------------------------
# Data models (hand-rolled, no pydantic to keep it light)
# ---------------------------------------------------------------------------

ECO_NODES: list[dict] = []
ECO_LINKS: list[dict] = []
ACTIVITY_LOG: list[dict] = []
METRICS_SNAPSHOT: dict = {}
CONNECTED_CLIENTS: set = set()
LAST_MONITOR_STATE: dict | None = None
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


def _merge_discovered(nodes: list[dict], links: list[dict], disc: dict) -> None:
    """Fold hub-discovered federation nodes/links into the graph (dedupe by id)."""
    existing = {n.get("id") for n in nodes}
    for n in disc.get("nodes", []):
        if n.get("id") and n["id"] not in existing:
            nodes.append(n)
            existing.add(n["id"])
    link_keys = {(l.get("source"), l.get("target")) for l in links}
    for l in disc.get("links", []):
        key = (l.get("source"), l.get("target"))
        if key not in link_keys:
            links.append(l)
            link_keys.add(key)
    fed = next((n for n in nodes if n.get("id") == "federation"), None)
    if fed is not None and disc.get("peer_count"):
        fed.setdefault("metrics", {})["peers"] = disc["peer_count"]
        fed["status"] = "active"


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

    # Real factory catalog → product planets orbiting AI-Factory
    catalog = fetch_factory_products_sync(APP_URL)
    if catalog is not None:
        merge_factory_products(nodes, links, catalog, app_url=APP_URL)

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
    body: dict = {"status": "ok", "mode": MODE}
    if MODE == "universe":
        u = get_universe()
        body["blockchain_ready"] = u.blockchain_ready
        body["contracts"] = {
            "evm_usdt": u.evm_usdt_address,
            "evm_escrow": u.evm_escrow_address,
            "evm_nft": u.evm_nft_address,
        }
        if _universe_bootstrap is not None:
            body["bootstrap"] = _universe_bootstrap
    return body


@app.get("/api/chain/status")
async def chain_status():
    """On-chain RPC + contract deployment snapshot (LIVE mode helper)."""
    return await fetch_onchain_snapshot()


async def _fetch_monitor_state() -> dict:
    """Current ecosystem snapshot for REST, WebSocket, and AI context."""
    global LAST_MONITOR_STATE
    async with _state_fetch_lock:
        if MODE == "universe":
            state = await asyncio.to_thread(get_universe().tick_universe)
        elif MODE == "real":
            state = await fetch_real_metrics()
        else:
            state = await asyncio.to_thread(simulator.step)
        LAST_MONITOR_STATE = state
        return state


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
            state = await _fetch_monitor_state()
            payload = json.dumps(
                {"type": "state_update", "data": _slim_state_for_ws(state)},
                default=str,
            )
            dead: list = []
            for ws in list(CONNECTED_CLIENTS):
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                CONNECTED_CLIENTS.discard(ws)
        except Exception:
            pass
        await asyncio.sleep(STATE_TICK_INTERVAL)


@app.on_event("startup")
async def _on_startup() -> None:
    global _universe_bootstrap
    if MODE == "test":
        logger.warning(
            "Alien Monitor running in TEST mode (ALIEN_MODE=test): all nodes, "
            "agents, transactions, channels and summary metrics are SIMULATED "
            "(random data) — do NOT treat these numbers as real ecosystem "
            "activity. Set ALIEN_MODE=real or ALIEN_MODE=universe for live data."
        )
    if MODE == "universe" and os.getenv("ALIEN_UNIVERSE_AUTO_START", "1").strip().lower() not in (
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
    asyncio.create_task(_monitor_broadcaster())


@app.get("/api/state")
async def get_state():
    """Return current full state snapshot."""
    return await _fetch_monitor_state()


@app.get("/api/summary")
async def get_summary():
    """Return lightweight summary for headers/badges."""
    if LAST_MONITOR_STATE and isinstance(LAST_MONITOR_STATE.get("summary"), dict):
        return LAST_MONITOR_STATE["summary"]
    if MODE == "universe":
        state = await asyncio.to_thread(get_universe().tick_universe)
        return state["summary"]
    if MODE == "real":
        data = await fetch_real_metrics()
        return data.get("summary", {"mode": "real"})
    state = await asyncio.to_thread(simulator.step)
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
        "mode": MODE,
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
    global MODE, _universe_bootstrap
    MODE = "universe"
    _universe_bootstrap = await asyncio.to_thread(get_universe().bootstrap)
    return _universe_bootstrap


@app.post("/api/universe/stop", dependencies=_MONITOR_AUTH)
async def universe_stop():
    """Stop UNI runtime and local chain processes."""
    global MODE
    MODE = "test"
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


@app.get("/api/ai/providers")
async def ai_providers():
    """LLM providers (same registry as aicom model_providers.yaml)."""
    return list_providers()


@app.post("/api/ai/ask", dependencies=_MONITOR_AUTH)
async def ai_ask(body: dict):
    """AI assistant — live state + multi-provider LLM (default: deepseek-v4-pro)."""
    question = (body.get("question") or "").strip()
    locale = normalize_locale(body.get("locale", "en"))
    if not question:
        return {"answer": EMPTY_QUESTION[locale]}

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
    system = build_system_prompt(ECOSYSTEM_CONTEXT, locale, live_ctx)
    provider_id = body.get("provider") or body.get("provider_id")
    model_role = body.get("model_role") or "heavy"

    if not any_provider_configured():
        return {
            "answer": _fallback_answer(question, locale, state, MODE),
            "meta": {"provider": "fallback", "live_state": state is not None},
        }

    try:
        answer, meta = await generate_answer(
            question=question,
            locale=locale,
            system_prompt=system,
            provider_id=provider_id,
            model_role=model_role,
        )
        meta["live_state"] = state is not None
        return {"answer": answer, "meta": meta}
    except Exception as e:
        fb = _fallback_answer(question, locale, state, MODE)
        return {
            "answer": fb + f"\n\n(LLM error: {e})",
            "meta": {"provider": "fallback", "error": str(e)},
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
        if "hub" in q or "хаб" in q:
            return "AIMarket Hub — федеративный каталог AI-возможностей с маршрутизацией микроплатежей. Порт 9083. discover → channel → invoke → settle. 15 плагинов."
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
        if "hub" in q:
            return "AIMarket Hub: catálogo federado + micropagos. Puerto 9083. 15 plugins."
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
    if "hub" in q:
        return "AIMarket Hub is a federated AI capability catalog with micropayment routing on port 9083 (discover → channel → invoke → settle). 15 plugins loaded."
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
    if LAST_MONITOR_STATE:
        await ws.send_text(json.dumps({
            "type": "state_update",
            "data": LAST_MONITOR_STATE,
        }, default=str))
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            cmd = msg.get("cmd", "")
            if cmd == "set_mode":
                global MODE
                pinned = (os.environ.get("ALIEN_MODE") or "").strip().lower()
                if os.environ.get("ALIEN_UNIVERSE_LOCK_MODE", "1").strip().lower() not in (
                    "0", "false", "no", "off",
                ) and pinned == "universe":
                    MODE = "universe"
                else:
                    MODE = msg.get("mode", MODE)
                if MODE == "universe":
                    u = get_universe()
                    if not u.running or not u.blockchain_ready:
                        await asyncio.to_thread(u.bootstrap)
                    elif not u.entities:
                        await asyncio.to_thread(u.seed_entities)
                    await asyncio.to_thread(u.sync_factory_catalog, APP_URL)
                await ws.send_text(json.dumps({"type": "mode_changed", "mode": MODE}))
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
    # Vite base=/monitor/ — serve the same build under /monitor/ for direct :9100 access
    # (without nginx path rewrite, /monitor/assets/* would 404 and the UI stays black).
    app.mount("/monitor", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend_monitor")
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=(MODE == "test"))


if __name__ == "__main__":
    main()
