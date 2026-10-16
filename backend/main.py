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
import contextlib
import ipaddress
import json
import logging
import mimetypes
import os
import random
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from universe import VirtualUniverse
from chain_metrics import (
    mesh_agent_count,
    apply_chain_metrics_to_nodes,
    build_real_summary,
    fetch_onchain_snapshot,
    hub_events_to_activity,
)
from factory_products import ensure_factory_clusters
from hub_affiliation import apply_hub_affiliation, hub_public_url
from realm_links import realm_links, session_tick_mode
from lottery_layers import apply_lottery_metrics
from themis_layers import apply_themis_to_nodes, fill_themis_sim_node
from competing_lab_layers import apply_competing_lab_sim_metrics, enrich_competing_lab_nodes
from logos_status import apply_logos_to_nodes, fetch_logos_status_sync
from monitor_auth import (
    MONITOR_SESSION_COOKIE,
    client_address,
    cors_allow_origins,
    create_monitor_session,
    monitor_api_token,
    monitor_cookie_secure,
    monitor_control_token_valid,
    monitor_public_read_allowed,
    monitor_websocket_origin_allowed,
    monitor_ws_token_valid,
    require_monitor_auth,
    require_monitor_read_auth,
    require_monitor_state_auth,
    trusted_proxies,
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
from ai_nav_actions import append_nav_hint, match_live_node_id, resolve_nav_actions
from ecosystem_registry import live_component_answer
from prompt_firewall import (
    rejected_answer,
    rejection_reason_if_blocked,
    wrap_snapshot_for_llm,
    wrap_user_question_for_llm,
)
from live_lottery_feed import LIVE_LOTTERY_TTL, set_live_lottery

from ecosystem_topology import (  # noqa: F401 - re-exported
    apply_live_lottery,
    build_aicom_topology,
    build_generic_topology,
    build_topology,
)
from ecosystem_context import (  # noqa: F401 - re-exported
    ECOSYSTEM_CONTEXT,
    full_ecosystem_context,
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
_ws_client_authed: dict[int, bool] = {}


def get_server_mode() -> str:
    """Canonical monitor mode for REST/health (env + optional admin override)."""
    return _normalize_mode(_runtime_server_mode) or SERVER_MODE


# --- Ecosystem crypto master switch -----------------------------------------
# Mirror of core/crypto_config.crypto_enabled — SAME env var + SAME truthy rule.
# The monitor is a standalone package with no import boundary to `core`; every
# standalone package reads the same env var with the same default-OFF contract.
_CRYPTO_TRUTHY = {"1", "true", "yes", "on"}


def crypto_enabled() -> bool:
    """True only if the ecosystem crypto switch is explicitly on. Default OFF.

    Delegates to chain_metrics, which the chain-source policy reads: two copies of this
    predicate is two answers to "is crypto on", and the scanner would eventually disagree
    with the map about which chain it is showing.
    """
    from chain_metrics import crypto_enabled as _shared

    return _shared()


def should_build_chain_context(mode: str, crypto_on: bool) -> bool:
    """Python mirror of argus/src/ecosystem/networks.ts `shouldBuildChainContext`:
    universe → always (a PRIVATE/local Anvil chain — never Base); real/LIVE →
    ONLY with crypto on (so the default never touches Base mainnet); test → never.
    Safety invariant: should_build_chain_context("real", False) is False."""
    return mode == "universe" or (mode == "real" and crypto_on)


# Nodes whose live state IS the real blockchain. In LIVE with crypto OFF these
# are explicitly greyed/disabled (honest "off in settings", not "service down").
# Universe always has its private Anvil, so this never applies there.
_CRYPTO_NODE_GROUPS = {"chain", "contract"}
_CRYPTO_NODE_IDS = {"acex", "lottery", "evm_escrow", "solana_escrow", "nft_contract",
                    "ethereum", "solana",
                    # Every number on the settlement node is an on-chain read, so with
                    # crypto off it must grey out like the rest rather than show zeros.
                    "settlement"}


def _is_crypto_node(node: dict) -> bool:
    return node.get("group") in _CRYPTO_NODE_GROUPS or node.get("id") in _CRYPTO_NODE_IDS


PORT = int(os.getenv("ALIEN_PORT", "9100"))
HOST = os.getenv("ALIEN_HOST", "127.0.0.1")
HUB_URL = os.getenv("HUB_URL", "http://localhost:9083").rstrip("/")
MESH_URL = os.getenv("MESH_URL", "http://localhost:8090").rstrip("/")
PROM_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090/prometheus").rstrip("/")
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
# With nobody watching, the ticker still keeps the REST cache warm, just slowly. It used to
# poll every satellite every 1.5 s around the clock: on the attested host that was two hub
# documents per tick, ~25% of a core with zero viewers, and on 2026-10-16 much of what
# /health queued behind while the CPU was crowded (hub.attestedmemory.net down twice).
STATE_IDLE_TICK_INTERVAL = float(os.getenv("ALIEN_STATE_IDLE_TICK_SEC", "20"))
# The hub's self-description changes about hourly; asking for it every tick cost the hub a
# catalogue scan and a full-document signature each time.
HUB_IDENTITY_TTL = float(os.getenv("ALIEN_HUB_IDENTITY_TTL_SEC", "300"))
_hub_identity_cache: dict[str, Any] = {"at": 0.0, "doc": None}
logger = logging.getLogger(__name__)
_universe_bootstrap: dict | None = None


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
        ensure_factory_clusters(nodes, links, APP_URL, catalog_timeout=8.0)
        for node in nodes:
            nid = node["id"]
            if nid == "hub":
                node["metrics"] = {
                    "peers": peers, "capabilities": capabilities,
                    "channels_open": channels_open, "invocations_24h": invocations,
                    "trust_score": 1.0,
                }
                node["status"] = "active"
                node["role"] = "hub"
            elif nid == "factory":
                node["metrics"] = {
                    "products": products, "tasks_pending": tasks_pending, "tasks_done": tasks_done,
                }
                node["status"] = "active"
                node["role"] = "hub"
                node["color"] = "#00f0ff"
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
            elif nid == "argus":
                from argus_feed import DEFAULT_ARGUS_RUN

                node["status"] = "active"
                node["argus_live"] = {
                    "economy": "on",
                    "mode": "test",
                    "model": "simulated/deepseek-chat",
                    "uptime_sec": t * 3,
                }
                node["argus_run"] = dict(DEFAULT_ARGUS_RUN)
            elif nid == "skopos":
                node["metrics"] = {
                    "servers": 3,
                    "requests_total": 120_000 + t * 120,
                    "security_score": 88 + (t % 5),
                }
                node["status"] = "active"
            elif nid == "metis":
                node["metrics"] = {
                    "knowledge_entries": 240 + t,
                    "cluster_nodes": 1,
                    "open_breakers": 0,
                }
                node["status"] = "active"
                node["chat"] = True
            elif nid == "dioscuri":
                node["metrics"] = {
                    "kb_chunks": 1800 + t * 2,
                    "kb_repos": 12,
                    "uptime_sec": t * 5,
                    "telegram": 1,
                    "discord": 1,
                }
                node["status"] = "active"
                node["dioscuri_live"] = {"theoros_active": True, "kb_chunks": node["metrics"]["kb_chunks"]}
            elif nid == "helios":
                node["metrics"] = {"subscribers": 1200 + t, "videos": 42, "views": 85000 + t * 10}
                node["status"] = "active"
            elif nid == "gaia":
                from gaia_status import fill_gaia_sim_node

                fill_gaia_sim_node(node)
            elif nid == "atlas":
                from atlas_status import fill_atlas_sim_node

                fill_atlas_sim_node(node)
            elif nid == "momus":
                node["metrics"] = {
                    "findings": 3 + (t % 4),
                    "targets": 4,
                    "learned": 12 + t % 5,
                }
                node["status"] = "active"
                node["momus_live"] = {
                    "provider": "simulated",
                    "model": "test/deepseek",
                    "crypto_enabled": False,
                    "holds_treasury_key": False,
                    "corpus": {"backend": "sim", "total_findings": 3, "recurring": 2},
                    "settlement": {"mode": "uni", "simulated": True, "moves_real_value": False},
                }
            elif nid == "bridges":
                # The one node in this loop that fabricates nothing. Every branch above invents
                # plausible activity because TEST simulates a running ecosystem; a billed channel
                # with no counter anywhere has no activity to simulate, and a made-up turnover
                # here would be screenshotted and believed.
                from bridges_status import fill_bridges_sim_node

                fill_bridges_sim_node(node)
            elif nid == "themis":
                fill_themis_sim_node(node, t)
            elif nid == "treasury":
                from treasury_status import fill_treasury_sim_node

                fill_treasury_sim_node(node, tick=t)

        apply_competing_lab_sim_metrics(nodes, t)
        apply_hub_affiliation(nodes, primary_hub_url=hub_public_url())

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


# The last merge outcome, kept so /api/federation/audit can explain what happened to every
# discovered hub without re-running discovery against somebody else's infrastructure.
_LAST_MERGE: dict[str, Any] = {"outcome": {}, "static_ids": set(), "disc": {}}


def _merge_discovered(nodes: list[dict], links: list[dict], disc: dict) -> None:
    """Fold hub-discovered federation nodes/links into the graph (dedupe by id)."""
    from oracle_family import merge_discovered_peers

    static_ids = {str(n.get("id")) for n in nodes if n.get("id")}
    outcome = merge_discovered_peers(nodes, links, disc) or {}
    _LAST_MERGE["outcome"] = outcome
    _LAST_MERGE["static_ids"] = static_ids
    _LAST_MERGE["disc"] = disc
    _LAST_MERGE["nodes"] = nodes


async def _hub_identity(client: httpx.AsyncClient, errors: list[str]) -> dict | None:
    """The hub's /.well-known document, fetched at most once per HUB_IDENTITY_TTL.

    A failed refresh keeps the last good document (the hub's name does not vanish because
    one request timed out) and is retried on the next tick.
    """
    cache = _hub_identity_cache
    if cache["doc"] is not None and time.monotonic() - cache["at"] < HUB_IDENTITY_TTL:
        return cache["doc"]
    try:
        r = await client.get(f"{HUB_URL}/.well-known/ai-market.json")
        doc = r.json() if r.status_code == 200 else None
        if isinstance(doc, dict):
            cache["doc"], cache["at"] = doc, time.monotonic()
    except Exception as e:
        errors.append(f"hub identity unavailable: {e}")
    return cache["doc"]


async def fetch_real_metrics() -> dict:
    """Gather live metrics from ecosystem HTTP APIs + on-chain RPC."""
    global _real_tick
    _real_tick += 1
    t = _real_tick

    result: dict = {"mode": "real", "errors": [], "components": {}}

    # Ecosystem crypto switch. In LIVE we only build a chain context (contact an
    # RPC) when crypto is explicitly enabled — otherwise the demo runs LIVE
    # off-chain and every crypto node is greyed as "off in settings".
    crypto_on = crypto_enabled()
    build_chain = should_build_chain_context("real", crypto_on)
    result["crypto_enabled"] = crypto_on

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

        # The centre of a self-hosted Monitor is the hub it is actually pointed at.  Keeping
        # the build-time label "AIMarket Hub" made Independent AI Hub look like a second,
        # unrelated cyan hub beside its own yellow discovery record.
        identity = await _hub_identity(client, result["errors"])
        if identity is not None:
            result["components"]["hub_identity"] = identity

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

    # On-chain RPC (EVM + Solana) — same env as AI-Factory. Only when a chain
    # context should exist: in LIVE with crypto OFF we never touch a chain
    # (honest state + safety invariant should_build_chain_context("real", False)).
    if build_chain:
        try:
            chain_snapshot = await fetch_onchain_snapshot()
            result["components"]["blockchain"] = chain_snapshot
            result["errors"].extend(chain_snapshot.get("errors") or [])
        except Exception as e:
            chain_snapshot = {"errors": [f"blockchain poll failed: {e}"]}
            result["components"]["blockchain"] = chain_snapshot
            result["errors"].append(str(e))
    else:
        chain_snapshot = {"errors": [], "skipped": "crypto-disabled"}

    nodes, links = build_topology()
    from oracle_family import poll_oracle_family_nodes

    for node in nodes:
        node["status"] = "unknown"
        cid = node["id"]
        if cid in result.get("components", {}):
            node["status"] = "active"

    hub_payload = result["components"].get("hub") or {}
    hub_identity = result["components"].get("hub_identity") or {}
    events, hub_hints = hub_events_to_activity(hub_payload if isinstance(hub_payload, dict) else {})
    # Who has actually transacted with us. A second-hop node earns its sphere by being part
    # of this economy on EITHER side — selling, or buying — and the catalogue only answers
    # the selling half. See hub_discovery._peer_hub_children.
    from hub_discovery import note_economy_participants

    note_economy_participants(
        str((event or {}).get("consumer_hub") or "")
        for event in ((hub_payload or {}).get("events") or [])
        if isinstance(event, dict)
    )
    apply_themis_to_nodes(
        nodes, hub_payload if isinstance(hub_payload, dict) else None
    )
    mesh_stats = result["components"].get("mesh")
    if "hub" in {n["id"] for n in nodes}:
        hub_node = next(n for n in nodes if n["id"] == "hub")
        if isinstance(hub_identity, dict):
            declared_name = str(hub_identity.get("name") or "").strip()
            declared_description = str(hub_identity.get("description") or "").strip()
            declared_url = str(
                hub_identity.get("hub_url") or hub_identity.get("base_url") or ""
            ).strip()
            if declared_name:
                hub_node["label"] = declared_name[:80]
            if declared_description:
                # One shared clip, not a second copy of the rule: this path had the polite
                # version while hub_discovery - the path that actually feeds the card - kept a
                # hard slice, so the fix was live and invisible.
                from hub_discovery import clip_description
                hub_node["description"] = clip_description(declared_description)
            if declared_url:
                hub_node["url"] = declared_url.rstrip("/")
        if hub_hints.get("invocations_24h"):
            hub_node["metrics"]["invocations_24h"] = hub_hints["invocations_24h"]
        if hub_hints.get("channels_open"):
            hub_node["metrics"]["channels_open"] = hub_hints["channels_open"]
        if hub_hints.get("capabilities") is not None:
            hub_node["metrics"]["capabilities"] = hub_hints["capabilities"]
        if hub_hints.get("peers") is not None:
            hub_node["metrics"]["peers"] = hub_hints["peers"]
        if result["components"].get("hub"):
            hub_node["status"] = "active"

    if isinstance(mesh_stats, dict):
        mesh_node = next((n for n in nodes if n["id"] == "mesh"), None)
        if mesh_node:
            mesh_node["status"] = "active"
            mesh_node["metrics"]["agents"] = int(
                mesh_agent_count(mesh_stats)
            )
            mesh_node["metrics"]["tasks"] = int(mesh_stats.get("tasks") or mesh_stats.get("tasks_total") or 0)
            mesh_node["metrics"]["activity"] = int(mesh_stats.get("activity") or 0)

    if result["components"].get("factory"):
        factory_node = next((n for n in nodes if n["id"] == "factory"), None)
        if factory_node:
            factory_node["status"] = "active"

    from deployment_profile import owns_builtin_shelf

    shelf_is_ours = owns_builtin_shelf()

    if shelf_is_ours:
        # Fail fast on slow /api/products — /categories fallback is ~300ms.
        ensure_factory_clusters(nodes, links, APP_URL, catalog_timeout=15.0)

    if build_chain:
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

    # Every poller below reaches out to a *.modelmarket.dev satellite. On a deployment
    # that is not ours those hosts are somebody else's infrastructure: the nodes are not on
    # this map, and asking them for status from a hundred foreign Monitors is how we
    # exhausted LOGOS's own rate limit from a single deployment (see poll_cache).
    # Foreign ecosystems arrive through federation, in one request to the hub.
    if not shelf_is_ours:
        apply_hub_affiliation(nodes, primary_hub_url=hub_public_url())
        return _finish_real_snapshot(
            t=t, result=result, nodes=nodes, links=links, events=events,
            crypto_on=crypto_on, build_chain=build_chain, hub_hints=hub_hints,
            chain_snapshot=chain_snapshot,
            mesh_stats=mesh_stats if isinstance(mesh_stats, dict) else None,
        )

    if t == 1 or t % 4 == 0:
        poll_oracle_family_nodes(nodes)

    apply_lottery_metrics(
        nodes,
        hub_hints=hub_hints,
        mesh_stats=mesh_stats if isinstance(mesh_stats, dict) else None,
        chain=chain_snapshot,
    )

    from argus_status import apply_argus_graph

    apply_argus_graph(nodes, mode="real")

    from hephaestus_status import apply_hephaestus_graph

    apply_hephaestus_graph(nodes, mode="real")

    from basanos_status import apply_basanos_graph

    apply_basanos_graph(nodes, mode="real")
    from hestia_status import apply_hestia_graph

    apply_hestia_graph(nodes, mode="real")
    from dolos_status import apply_dolos_graph

    apply_dolos_graph(nodes, mode="real")
    from settlement_status import apply_settlement_graph
    apply_settlement_graph(nodes, mode="real")

    from dioscuri_status import apply_dioscuri_graph
    from helios_status import apply_helios_graph
    from metis_status import apply_metis_graph
    from skopos_status import apply_skopos_graph

    apply_dioscuri_graph(nodes, mode="real")
    apply_helios_graph(nodes, mode="real")
    apply_metis_graph(nodes, mode="real")
    apply_skopos_graph(nodes, mode="real")

    from gaia_status import apply_gaia_graph

    apply_gaia_graph(nodes, mode="real")

    from atlas_status import apply_atlas_graph

    apply_atlas_graph(nodes, mode="real")
    from factory_agents import apply_factory_agents_graph

    apply_factory_agents_graph(nodes, mode="real")

    from momus_status import apply_momus_graph
    from warden_status import apply_warden_graph
    from treasury_status import apply_treasury_graph

    apply_momus_graph(nodes, mode="real")
    apply_warden_graph(nodes, mode="real")
    from histor_status import apply_histor_graph

    try:
        # Two HTTP reads to a public host: in a thread, so a slow HISTOR never stalls the loop.
        await asyncio.to_thread(apply_histor_graph, nodes, mode="real")
    except Exception:  # noqa: BLE001 - one satellite's poller must not take the metrics loop down
        logger.exception("HISTOR overlay failed")
    apply_logos_to_nodes(nodes, fetch_logos_status_sync())
    apply_treasury_graph(nodes, mode="real")

    from bridges_status import apply_bridges_graph

    apply_bridges_graph(nodes, mode="real")

    try:
        await enrich_competing_lab_nodes(nodes, primary_hub_url=HUB_URL)
    except Exception as e:  # pragma: no cover - viz must not hard-fail
        result["errors"].append(f"competing lab enrich failed: {e}")

    apply_hub_affiliation(nodes, primary_hub_url=hub_public_url())

    return _finish_real_snapshot(
        t=t, result=result, nodes=nodes, links=links, events=events,
        crypto_on=crypto_on, build_chain=build_chain, hub_hints=hub_hints,
        chain_snapshot=chain_snapshot,
        mesh_stats=mesh_stats if isinstance(mesh_stats, dict) else None,
    )


def _finish_real_snapshot(
    *,
    t: int,
    result: dict,
    nodes: list[dict],
    links: list[dict],
    events: list,
    crypto_on: bool,
    build_chain: bool,
    hub_hints: dict,
    chain_snapshot: dict,
    mesh_stats: dict | None = None,
) -> dict:
    """Everything a LIVE snapshot needs regardless of whose ecosystem it describes.

    Split out when the profile split arrived: a deployment pointed at somebody else's hub
    skips the satellite pollers entirely, and still has to be spaced, summarised and shipped
    the same way.
    """
    # Honest state: in LIVE with crypto OFF the real chain is intentionally never
    # contacted, so every crypto-dependent node is explicitly DISABLED (greyed +
    # "blockchain off in settings" badge on the client) — not silently idle. Runs
    # LAST so it overrides any liveness/lottery/discovery status set above.
    if not crypto_on:
        for node in nodes:
            if _is_crypto_node(node):
                node["status"] = "disabled"
                node["crypto_disabled"] = True

    from factory_products import published_app_count

    summary = build_real_summary(
        tick=t,
        hub_hints=hub_hints,
        mesh_stats=mesh_stats,
        chain=chain_snapshot,
        apps_online=published_app_count(nodes),
    )

    # Same owner as the UNI map: whoever authored a position, two planets must not
    # end up inside each other. Runs on the assembled graph, right before it ships.
    from space_map import enforce_spacing

    enforce_spacing(nodes)

    return {
        "tick": t,
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": "real",
        "crypto_enabled": crypto_on,
        "chain_context": build_chain,
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
_MONITOR_READ_AUTH = [Depends(require_monitor_read_auth)]

# Public demo AI rate limit (per client address — see monitor_auth.client_address, which
# needs ALIEN_TRUSTED_PROXIES to see past nginx). Bearer-authed clients share the bucket.
_AI_ASK_HITS: dict[str, list[float]] = {}
_AI_ASK_LIMIT = int(os.environ.get("ALIEN_AI_ASK_RATE_LIMIT", "20"))  # requests
_AI_ASK_WINDOW_S = float(os.environ.get("ALIEN_AI_ASK_RATE_WINDOW_S", "60"))
_AUTH_SESSION_HITS: dict[str, list[float]] = {}
_AUTH_SESSION_LIMIT = int(os.environ.get("ALIEN_AUTH_SESSION_RATE_LIMIT", "10"))
_AUTH_SESSION_WINDOW_S = 5 * 60.0


# The per-address limit is not a budget: an IPv6 /64 or a proxy pool has as many
# addresses as the caller wants, and every answer is paid on the operator's provider key
# (the same key the factory's pipelines run on). So there is a GLOBAL hourly ceiling too.
_AI_ASK_MAX_PER_HOUR = int(os.environ.get("ALIEN_AI_ASK_MAX_PER_HOUR", "240"))
_AI_ASK_GLOBAL: list[float] = []
#: Client-sent monitor state is only a fallback, and a bounded one.
_AI_CLIENT_STATE_MAX_BYTES = 64 * 1024


def _rate_key(address: str) -> str:
    """One bucket per IPv4 address, one per IPv6 /64 (a host is handed a whole /64)."""
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return address
    if parsed.version == 6 and parsed.ipv4_mapped is None:
        return str(ipaddress.ip_network(f"{parsed}/64", strict=False))
    return address


def _ai_ask_rate_limit(request: Request) -> None:
    ip = _rate_key(client_address(request))
    now = time.time()
    hits = [t for t in _AI_ASK_HITS.get(ip, []) if now - t < _AI_ASK_WINDOW_S]
    if len(hits) >= _AI_ASK_LIMIT:
        raise HTTPException(status_code=429, detail="Too many AI requests — slow down")
    _AI_ASK_GLOBAL[:] = [t for t in _AI_ASK_GLOBAL if now - t < 3600.0]
    if len(_AI_ASK_GLOBAL) >= _AI_ASK_MAX_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail="The monitor AI has answered its hourly budget of questions — try again later",
        )
    _AI_ASK_GLOBAL.append(now)
    hits.append(now)
    _AI_ASK_HITS[ip] = hits
    # Bound memory
    if len(_AI_ASK_HITS) > 4096:
        stale = [k for k, v in _AI_ASK_HITS.items() if not v or now - v[-1] > _AI_ASK_WINDOW_S]
        for k in stale[:512]:
            _AI_ASK_HITS.pop(k, None)


def _auth_session_rate_limit(request: Request) -> None:
    ip = client_address(request)
    now = time.time()
    hits = [t for t in _AUTH_SESSION_HITS.get(ip, []) if now - t < _AUTH_SESSION_WINDOW_S]
    if len(hits) >= _AUTH_SESSION_LIMIT:
        raise HTTPException(status_code=429, detail="Too many authentication attempts")
    hits.append(now)
    _AUTH_SESSION_HITS[ip] = hits
    if len(_AUTH_SESSION_HITS) > 4096:
        stale = [k for k, v in _AUTH_SESSION_HITS.items() if not v or now - v[-1] > _AUTH_SESSION_WINDOW_S]
        for key in stale[:512]:
            _AUTH_SESSION_HITS.pop(key, None)

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
    # Ecosystem crypto switch — lets the client honestly badge LIVE-without-crypto
    # and grey the chain nodes ("off in settings", not "service down").
    body["crypto_enabled"] = crypto_enabled()
    body["chain_context"] = should_build_chain_context(sm, body["crypto_enabled"])
    # The two maps are separate processes and neither used to admit the other existed.
    links = realm_links(sm)
    if links:
        body["realm_links"] = links
    if sm == "universe":
        u = get_universe()
        body["blockchain_ready"] = u.blockchain_ready
        body["contracts"] = {
            "evm_usdt": u.evm_usdt_address,
            "evm_escrow": u.evm_escrow_address,
            "evm_nft": u.evm_nft_address,
            "evm_lottery": u.evm_lottery_address,
            "evm_acex_amm": u.evm_acex_amm_address,
            "evm_acex_registry": u.evm_acex_registry_address,
            "solana_lottery": u.solana_lottery_program_id,
        }
        if _universe_bootstrap is not None:
            body["bootstrap"] = _universe_bootstrap
    return body


@app.post("/api/auth/session")
async def login_monitor_session(request: Request, body: dict):
    """Exchange the operator token for an HttpOnly, short-lived browser session."""
    _auth_session_rate_limit(request)
    expected = monitor_api_token()
    supplied = str(body.get("token") or "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Monitor authentication is not configured")
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
    response = JSONResponse({"ok": True})
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(
        MONITOR_SESSION_COOKIE,
        create_monitor_session(),
        max_age=8 * 60 * 60,
        httponly=True,
        secure=monitor_cookie_secure(),
        samesite="strict",
        path="/",
    )
    return response


@app.delete("/api/auth/session")
async def logout_monitor_session():
    response = JSONResponse({"ok": True})
    response.delete_cookie(MONITOR_SESSION_COOKIE, path="/", secure=monitor_cookie_secure(), samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/chain/status", dependencies=[Depends(require_monitor_read_auth)])
async def chain_status():
    """On-chain RPC + contract deployment snapshot (LIVE mode helper)."""
    return await fetch_onchain_snapshot()


def _scan_target() -> tuple[str, str, dict]:
    """(rpc_url, deployment realm, network label) for a scan — one policy, three routes.

    `chain_metrics.chain_source` decides WHICH chain: the bubble reads its own Anvil; a LIVE
    monitor reads the EVM network in settings only while the crypto switch is on, and the
    bubble's chain otherwise. The routes used to hardcode "base" and take whatever
    `ALIEN_EVM_RPC` named — which is how a panel headed "Base" scanned a local Anvil.
    """
    from chain_metrics import chain_source
    source = chain_source()
    urls = source.get("urls") or []
    # Contract NAMES are per-deployment: the bubble's address book must never label a mainnet
    # address and vice versa. Reading the bubble means reading the bubble's names too.
    realm = "uni" if source.get("source") == "uni-bubble" else "live"
    return (urls[0] if urls else "", realm, {k: v for k, v in source.items() if k != "urls"})


@app.get("/api/chain/scan", dependencies=[Depends(require_monitor_read_auth)])
async def chain_scan(limit: int = 25):
    """Recent transactions on the chain this monitor is actually reading (see _scan_target)."""
    from chain_scan import scan_chain
    rpc, realm, network = _scan_target()
    return await scan_chain(rpc, realm=realm, network=network,
                            limit=max(1, min(100, int(limit or 25))))


@app.get("/api/chain/tx/{tx_hash}", dependencies=[Depends(require_monitor_read_auth)])
async def chain_tx(tx_hash: str):
    """One transaction with its receipt (status / gas / logs) on that same chain."""
    from chain_scan import scan_tx
    rpc, realm, network = _scan_target()
    return await scan_tx(rpc, tx_hash, realm=realm, network=network)


@app.get("/api/chain/address/{address}", dependencies=[Depends(require_monitor_read_auth)])
async def chain_address(address: str, limit: int = 25):
    """An address page: balance, nonce, code, and its recent transactions on that chain."""
    from chain_scan import scan_address
    rpc, realm, network = _scan_target()
    return await scan_address(rpc, address, realm=realm, network=network,
                              limit=max(1, min(100, int(limit or 25))))


@app.get("/api/public/dioscuri-collab")
async def public_dioscuri_collab():
    """Public THEOROS collaboration badge for ecosystem landing (no auth)."""
    from dioscuri_status import dioscuri_theoros_collaboration, fetch_dioscuri_health_sync

    health = fetch_dioscuri_health_sync()
    if not health or not health.get("ok"):
        return dioscuri_theoros_collaboration(active=False)
    theoros = health.get("theoros") if isinstance(health.get("theoros"), dict) else {}
    return dioscuri_theoros_collaboration(active=bool(theoros.get("active")))


def _universe_fast_snapshot() -> dict:
    """Seed graph the WebSocket sends on connect, before the broadcaster's first tick.

    "Without network polls" it never was — it polled twelve satellites — and the ones it did
    NOT poll arrived offline. It now goes through the one owner like everything else, which
    also means the first payload a browser sees matches every payload after it.
    """
    u = get_universe()
    from factory_products import collapse_graph_products

    raw_nodes = [ent.to_node() for ent in u.entities.values()]
    raw_links = u.get_topology_links()
    graph_nodes, graph_links = collapse_graph_products(raw_nodes, raw_links)
    from satellite_overlays import apply_live_layers

    apply_live_layers(graph_nodes, tick=u.tick,
                      escrow=getattr(u, "evm_escrow_address", "") or "",
                      rpc=getattr(u, "evm_rpc", "") or "")
    ensure_factory_clusters(graph_nodes, graph_links, APP_URL, catalog_timeout=5.0)
    apply_hub_affiliation(graph_nodes, primary_hub_url=hub_public_url())
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
    mode = session_tick_mode(effective_mode, get_server_mode())
    async with _state_fetch_lock:
        if mode == "universe":
            state = await asyncio.to_thread(get_universe().tick_universe)
            try:
                await enrich_competing_lab_nodes(state.get("nodes") or [], primary_hub_url=HUB_URL)
            except Exception:
                pass
            apply_hub_affiliation(state.get("nodes") or [], primary_hub_url=hub_public_url())
        elif mode == "real":
            state = await fetch_real_metrics()
        else:
            state = await asyncio.to_thread(simulator.step)
        return state


def _cached_monitor_state(mode: str | None = None) -> dict | None:
    effective = session_tick_mode(mode, get_server_mode())
    cached = LAST_MONITOR_STATES.get(effective)
    if cached and cached.get("nodes"):
        return cached
    return None


def _slim_state_for_ws(state: dict) -> dict:
    """Drop bulky debug fields from WebSocket payloads (REST /api/state unchanged).

    Also the single choke point where a map too big to send stops being sent whole: past
    `ALIEN_MAP_WINDOW_THRESHOLD` the tick carries this deployment's own ecosystem and a
    pointer to the rest, and the client pulls the star chart and its window over HTTP.
    Below the threshold this is a no-op — see map_window.tick_payload.
    """
    if not isinstance(state, dict):
        return state
    from map_window import tick_payload
    from node_identity import resolved_nodes

    slim = dict(state)
    slim.pop("components", None)
    # A foreign hub describes itself the way it sees itself, and what it sees is its own
    # compose network: the Attested Memory Hub advertised `http://provenance-ledger:8812`,
    # and the card offered that to the reader as a link. An address is a link only when a
    # browser elsewhere could open it — see node_identity.
    slim["nodes"] = resolved_nodes(slim.get("nodes"))
    return tick_payload(slim)


def _public_demo_state_for_ws(state: dict) -> dict:
    """Graph-friendly WS payload without contract addresses or internal diagnostics."""
    slim = _slim_state_for_ws(state)
    summary = slim.get("summary")
    if isinstance(summary, dict):
        redacted = dict(summary)
        for key in ("contracts", "bootstrap", "hub_env_snippet", "payment_recipient"):
            redacted.pop(key, None)
        slim["summary"] = redacted
    nodes: list = []
    for node in slim.get("nodes") or []:
        if not isinstance(node, dict):
            nodes.append(node)
            continue
        nc = dict(node)
        nc.pop("hub_env_snippet", None)
        nodes.append(nc)
    slim["nodes"] = nodes
    slim.pop("errors", None)
    return slim


def _monitor_request_authed(request: Request) -> bool:
    """Did THIS request prove who it is, independently of whether the guard let it through?

    The read guard admits anonymous callers whenever ``ALIEN_PUBLIC_READ=1``, so "the guard
    passed" says nothing about identity. Routes that serve a reduced payload to the public
    tier need the identity answer, and it is the same one the WebSocket asks
    (``monitor_ws_token_valid``) — a bearer token or the HttpOnly browser session.
    """
    from monitor_auth import MONITOR_SESSION_COOKIE, monitor_ws_token_valid

    header = (request.headers.get("authorization") or "").strip()
    token = header[7:].strip() if header.lower().startswith("bearer ") else None
    return monitor_ws_token_valid(token, request.cookies.get(MONITOR_SESSION_COOKIE))


def _state_for_ws(state: dict, *, ws_authed: bool) -> dict:
    """Full slim payload for an AUTHENTICATED client; the redacted one for everybody else.

    This used to read `if ws_authed or monitor_public_read_allowed()`, which made the
    redaction branch unreachable: the only way to be unauthenticated AND outside the public
    read tier is the case where `websocket_endpoint` has already closed the socket with
    1008. So every anonymous public-demo viewer received the UNREDACTED stream — contract
    addresses, bootstrap, hub_env_snippet and internal `errors` — and the function written
    to prevent exactly that never ran. The tier has to key on the same thing the gate does:
    whether this client proved who it is.
    """
    if ws_authed:
        return _slim_state_for_ws(state)
    return _public_demo_state_for_ws(state)


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
                    {
                        "type": "state_update",
                        "data": _state_for_ws(
                            state,
                            ws_authed=_ws_client_authed.get(id(ws), False),
                        ),
                    },
                    default=str,
                )
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                CONNECTED_CLIENTS.discard(ws)
                _ws_client_modes.pop(id(ws), None)
                _ws_client_authed.pop(id(ws), None)
        except Exception:
            pass
        await _wait_for_next_tick()


# Set when a viewer connects, so an idle ticker wakes for them instead of finishing its
# long sleep: the first frame comes from the cache, the next one is fresh.
_viewer_arrived = asyncio.Event()


def _tick_interval() -> float:
    if CONNECTED_CLIENTS:
        return STATE_TICK_INTERVAL
    return max(STATE_TICK_INTERVAL, STATE_IDLE_TICK_INTERVAL)


async def _wait_for_next_tick() -> None:
    _viewer_arrived.clear()
    try:
        await asyncio.wait_for(_viewer_arrived.wait(), timeout=_tick_interval())
    except asyncio.TimeoutError:
        pass


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
    if monitor_public_read_allowed() and not trusted_proxies():
        logger.warning(
            "ALIEN_TRUSTED_PROXIES is not set while the read APIs are public — the AI and "
            "session rate limits key on the immediate peer, which behind nginx is the PROXY: "
            "one bucket for every visitor. Set it to the proxy address(es), e.g. 127.0.0.1."
        )
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


async def _monitor_state_snapshot(mode: str | None = None):
    """Full ecosystem snapshot (shared by /api/state and Pulse Terminal)."""
    effective = session_tick_mode(mode, get_server_mode())
    cached = _cached_monitor_state(effective)
    if cached:
        return cached
    if effective == "universe" and get_universe().entities:
        return await asyncio.to_thread(_universe_fast_snapshot)
    return await _fetch_monitor_state(effective)


_FEDERATION_LAZY_ALLOWED: set[str] = set()


@app.get("/api/state", dependencies=[Depends(require_monitor_state_auth)])
async def get_state(mode: str | None = None):
    """Return current full state snapshot (optional ?mode= for UI session override)."""
    return await _monitor_state_snapshot(mode)


@app.get("/api/map/digest", dependencies=[Depends(require_monitor_read_auth)])
async def get_map_digest(cursor: int = 0, limit: int = 0, mode: str | None = None):
    """The star chart: every node as `[id, x, y, z, kind]`, paged.

    What the far field is drawn from. Deliberately not objects — at a hundred thousand
    nodes the client must never build a hundred thousand of anything.
    """
    from map_window import DIGEST_PAGE, build_digest

    state = await _monitor_state_snapshot(mode)
    nodes = (state or {}).get("nodes") or []
    return build_digest(nodes, cursor=cursor, limit=limit or DIGEST_PAGE)


@app.get("/api/map/window", dependencies=[Depends(require_monitor_read_auth)])
async def get_map_window(
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
    radius: float = 40.0,
    limit: int = 0,
    focus: str = "",
    mode: str | None = None,
):
    """Full nodes near a point — what the camera can actually resolve.

    `focus` names ids to include whatever the distance: the hub the reader just clicked is
    the one thing that must never come back empty.
    """
    from map_window import select_window

    state = await _monitor_state_snapshot(mode)
    nodes = (state or {}).get("nodes") or []
    links = (state or {}).get("links") or []
    wanted = [part for part in focus.split(",") if part.strip()]
    return select_window(
        nodes, links,
        center=(x, y, z), radius=radius, limit=limit or None, include_ids=wanted,
    )


@app.get("/api/federation/audit")
async def federation_audit():
    """Did every hub the federation reports actually reach the map?

    Public and unauthenticated on purpose: it carries no secret, only whether this deployment
    can draw what it claims to index. A federation that grows by strangers knocking cannot be
    audited by looking at pictures — three hubs in a row went missing here with nothing in a
    log, because "discovered", "merged" and "visible" are three different things and only the
    last one is what anybody sees.
    """
    from federation_audit import audit as _audit

    last = _LAST_MERGE
    if not last.get("disc"):
        return {"ok": None, "note": "no snapshot built yet — ask again after the next tick"}
    folded = {
        nid: out.split(":", 1)[1]
        for nid, out in (last.get("outcome") or {}).items()
        if str(out).startswith("fold")
    }
    return _audit(
        list(last.get("nodes") or []),
        last.get("disc") or {},
        set(last.get("static_ids") or set()),
        folded,
    )


@app.get("/api/federation/neighborhood", dependencies=[Depends(require_monitor_state_auth)])
async def federation_neighborhood(hub_url: str, cursor: int = 0, limit: int = 2000):
    """Lazy graph window around a Hub already visible in the live map."""
    state = await _monitor_state_snapshot("real")
    nodes = state.get("nodes") if isinstance(state, dict) else []
    normalized = hub_url.strip().rstrip("/").lower()
    known = next((
        node for node in (nodes or [])
        if str(node.get("url") or "").strip().rstrip("/").lower() == normalized
    ), None)
    if known is None and normalized not in _FEDERATION_LAZY_ALLOWED:
        raise HTTPException(status_code=403, detail="Hub is not an approved graph node")
    from hub_discovery import fetch_neighborhood_async

    result = await fetch_neighborhood_async(hub_url, cursor=cursor, limit=limit)
    for neighbor in result.get("neighbors") or []:
        if isinstance(neighbor, dict):
            _FEDERATION_LAZY_ALLOWED.add(str(neighbor.get("url") or "").rstrip("/").lower())
    return result


@app.get("/api/pulse/state", dependencies=[Depends(require_monitor_read_auth)])
async def get_pulse_state(request: Request, mode: str | None = None):
    """Pulse Terminal read path — respects ALIEN_PUBLIC_READ in production.

    Projected for an unauthenticated caller. This returned the identical object as
    `/api/state`, whose guard is documented as "always token-gated in production (even
    public demo)" — but under the READ guard, which `ALIEN_PUBLIC_READ=1` (set in
    docker-compose.prod.yml) turns into a no-op. The dump the state guard exists to withhold
    was therefore served anonymously one URL over: `components` is the raw upstream JSON
    from the internal Hub, mesh, factory and Prometheus, and `errors` is internal
    diagnostics. Reuses the WS redaction so there is ONE definition of what the public tier
    may see.
    """
    snapshot = await _monitor_state_snapshot(mode)
    if _monitor_request_authed(request):
        return snapshot
    return _public_demo_state_for_ws(snapshot)


@app.get("/api/summary", dependencies=[Depends(require_monitor_read_auth)])
async def get_summary(mode: str | None = None):
    """Lightweight summary for headers/badges, for the requested session mode.

    It took no ``mode`` at all while ``/api/topology`` painted one, and the two are
    fetched together by the client's HTTP fallback — the path every anonymous viewer
    takes on a deploy where ``/api/state`` is authed. Clicking TEST there produced a
    simulated graph under a header of LIVE settlement numbers. ``session_tick_mode``
    still refuses cross-realm requests, so this only ever honours TEST.
    """
    snapshot = await _monitor_state_snapshot(mode)
    summary = (snapshot or {}).get("summary")
    if isinstance(summary, dict):
        return summary
    return {"mode": session_tick_mode(mode, get_server_mode())}


@app.get("/api/topology", dependencies=[Depends(require_monitor_read_auth)])
async def get_topology(mode: str | None = None):
    """Return graph topology (nodes + links) with current metrics for the session mode.

    ``?mode=`` used to be accepted by the client and ignored by the route.
    ``session_tick_mode`` keeps the realm seal: LIVE never renders UNI and vice versa.
    """
    sm = session_tick_mode(mode, get_server_mode())
    if sm == "universe":
        u = get_universe()
        nodes = [e.to_node() for e in u.entities.values()]
        links = u.get_topology_links()
        from factory_products import collapse_graph_products

        nodes, links = collapse_graph_products(nodes, links)
        # Every satellite status layer, from the one place that owns the list. This route
        # used to apply four of them, so MOMUS, ATLAS, GAIA, SKOPOS and the rest came back
        # at their node-spec defaults — `status: "offline"`, zero metrics — while the
        # services themselves were answering in milliseconds.
        from satellite_overlays import apply_live_layers

        apply_live_layers(nodes, tick=u.tick,
                          escrow=getattr(u, "evm_escrow_address", "") or "",
                          rpc=getattr(u, "evm_rpc", "") or "")
        ensure_factory_clusters(nodes, links, APP_URL, catalog_timeout=5.0)
        apply_hub_affiliation(nodes, primary_hub_url=hub_public_url())
        from node_identity import resolved_nodes

        return {"nodes": resolved_nodes(nodes), "links": links}

    nodes, links = build_topology()
    if sm == "test":
        state = simulator.step()
        smap = {n["id"]: n for n in state["nodes"]}
        for node in nodes:
            if node["id"] in smap:
                node["metrics"] = smap[node["id"]]["metrics"]
                node["status"] = smap[node["id"]]["status"]
    elif sm == "real":
        # Anonymous browsers hit this every few seconds (/api/state is token-gated).
        # Calling fetch_real_metrics() here re-polls every satellite on the request
        # path. A handful of open tabs pile those polls up until new connections
        # fail and the page stays on "Connecting" with a network error, while
        # /api/health still answers. The broadcaster already holds this graph.
        cached = _cached_monitor_state("real")
        if cached and cached.get("nodes"):
            nodes = []
            for extra in cached["nodes"]:
                if not isinstance(extra, dict):
                    continue
                carried = dict(extra)
                carried.pop("hub_env_snippet", None)
                nodes.append(carried)
            known_ids = {str(n.get("id") or "") for n in nodes}
            links = [
                lnk for lnk in (cached.get("links") or [])
                if str(lnk.get("source") or "") in known_ids
                and str(lnk.get("target") or "") in known_ids
            ]
            apply_hub_affiliation(nodes, primary_hub_url=hub_public_url())
            return {"nodes": nodes, "links": links}
        data = await _fetch_monitor_state("real")
        smap = {n["id"]: n for n in data["nodes"]}
        for node in nodes:
            if node["id"] in smap:
                snap = smap[node["id"]]
                node["metrics"] = snap["metrics"]
                node["status"] = snap["status"]
                # The live card payload too — momus_live, histor_live, argus_live, … Copying only
                # metrics and status left every satellite card on the public map reading "no live
                # data" beside a green node (MOMUS "Frozen — unreachable" while answering in
                # 0.5 s). Same rule as the public WS tier: everything but hub_env_snippet.
                for key, value in snap.items():
                    if key == "hub_env_snippet":
                        continue
                    if key.endswith("_live") or key not in node:
                        node[key] = value
        # Carry over EVERYTHING the real snapshot has that build_topology() does not seed.
        #
        # This used to be a hand-written pair of groups — {"cluster", "factory_product"},
        # the catalog nebula and the pinned factory ships — and it was written before
        # federation discovery existed. So every node discovery produces (`peer_hub`, its
        # providers, a peer's own peers) was dropped from THIS route, which is the one an
        # anonymous browser actually renders: `/api/state` is authenticated, the public map
        # falls back here, and the two are supposed to be the same graph.
        #
        # Measured 2026-09-16 on monitor.modelmarket.dev: 73 nodes in /api/state against 61
        # here, the twelve missing ones being both federated hubs — Attested Memory and
        # Independent AI — every provider hanging off them, and CHARON. They were on the
        # authenticated map and on nobody's screen.
        #
        # A list of groups has to be edited whenever the graph grows a kind, and will be
        # forgotten again. "Not seeded" needs no maintenance.
        replaced_groups = {"cluster", "factory_product"}
        nodes = [n for n in nodes if n.get("group") not in replaced_groups]
        seeded_ids = {str(n.get("id") or "") for n in nodes}
        for extra in data.get("nodes") or []:
            node_id = str(extra.get("id") or "")
            if not node_id or node_id in seeded_ids:
                continue
            carried = dict(extra)
            # The same key the public WebSocket tier strips. This route is read-public.
            carried.pop("hub_env_snippet", None)
            nodes.append(carried)
            seeded_ids.add(node_id)
        known_ids = seeded_ids
        seen_links = {
            (str(lnk.get("source") or ""), str(lnk.get("target") or ""), str(lnk.get("label") or ""))
            for lnk in links
        }
        links = [
            lnk for lnk in links
            if str(lnk.get("source") or "") in known_ids
            and str(lnk.get("target") or "") in known_ids
        ]
        for lnk in data.get("links") or []:
            key = (str(lnk.get("source") or ""), str(lnk.get("target") or ""), str(lnk.get("label") or ""))
            if key in seen_links:
                continue
            if key[0] in known_ids and key[1] in known_ids:
                links.append(lnk)
                seen_links.add(key)
    apply_hub_affiliation(nodes, primary_hub_url=hub_public_url())
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


def _patch_argus_run_in_cached_states(run: dict) -> None:
    """Reflect a fresh pushed run in REST/WS cache without waiting for the next tick."""
    global LAST_MONITOR_STATE

    def _apply(state: dict | None) -> None:
        if not state or not isinstance(state.get("nodes"), list):
            return
        for node in state["nodes"]:
            if node.get("id") == "argus":
                node["argus_run"] = dict(run)
                return

    for mode, state in LAST_MONITOR_STATES.items():
        if mode == "test":
            continue
        _apply(state)
    if get_server_mode() != "test":
        _apply(LAST_MONITOR_STATE)


def _patch_argus_roster_in_cached_states() -> None:
    """Refresh ARGUS · N label/metrics on cached graph nodes after heartbeat/run."""
    global LAST_MONITOR_STATE
    try:
        from argus_roster import apply_roster_to_node
    except Exception:
        return

    def _apply(state: dict | None) -> None:
        if not state or not isinstance(state.get("nodes"), list):
            return
        for node in state["nodes"]:
            if node.get("id") == "argus":
                apply_roster_to_node(node)
                return

    for mode, state in LAST_MONITOR_STATES.items():
        if mode == "test":
            continue
        _apply(state)
    if get_server_mode() != "test":
        _apply(LAST_MONITOR_STATE)


@app.post("/api/argus/run", dependencies=_MONITOR_AUTH)
async def argus_run_update(body: dict):
    """Ingest a live verifiable run from ARGUS for the graph node detail panel.

    Also upserts the multi-instance roster (``instance_id`` optional — derived
    from wallet/signer when omitted).
    """
    from argus_feed import ARGUS_RUN_TTL, argus_run_if_fresh, set_argus_run
    from argus_roster import counts

    set_argus_run(body)
    fresh = argus_run_if_fresh()
    if fresh:
        _patch_argus_run_in_cached_states(fresh)
    _patch_argus_roster_in_cached_states()
    c = counts()
    return {
        "ok": True,
        "fresh_ttl_s": ARGUS_RUN_TTL,
        "run_id": str(body.get("id", ""))[:64],
        "roster": c,
    }


@app.post("/api/argus/heartbeat", dependencies=_MONITOR_AUTH)
async def argus_heartbeat(body: dict):
    """Lightweight presence ping — keeps an instance on the ARGUS · N roster."""
    from argus_roster import ACTIVE_TTL_S, counts, heartbeat

    rec = heartbeat(body if isinstance(body, dict) else {})
    if not rec:
        raise HTTPException(
            status_code=400,
            detail="instance_id or wallet required (4–128 chars [A-Za-z0-9_.:-])",
        )
    _patch_argus_roster_in_cached_states()
    return {"ok": True, "instance": rec, "active_ttl_s": ACTIVE_TTL_S, "roster": counts()}


@app.get("/api/argus/instances", dependencies=[Depends(require_monitor_read_auth)])
async def argus_instances_list(
    q: str = "",
    sort: str = "last_seen",
    cursor: str = "",
    limit: int = 40,
    status: str = "",
):
    """Searchable / sortable / cursor-paginated ARGUS fleet roster.

    Same pattern as Factory ``Products · N``: one graph ball, list in the panel.
    """
    from argus_roster import list_instances

    return list_instances(q=q, sort=sort, cursor=cursor, limit=limit, status=status)


@app.get("/api/argus/instances/{instance_id}", dependencies=[Depends(require_monitor_read_auth)])
async def argus_instance_detail(instance_id: str):
    """Single ARGUS instance + latest verifiable run (if any)."""
    from argus_roster import get_instance

    rec = get_instance(instance_id)
    if not rec:
        raise HTTPException(status_code=404, detail="instance not found")
    return rec


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


@app.get("/api/ai/providers", dependencies=[Depends(require_monitor_read_auth)])
async def ai_providers():
    """LLM providers (same registry as aicom model_providers.yaml)."""
    return list_providers()


def _safe_reputation(raw: Any) -> dict | None:
    """The viewer's REP ranking, bounded and retyped before it reaches a prompt.

    The ranking is computed in the panel that draws it, so the client sends it — which means it
    is untrusted input on its way into a system prompt. Only the shape below survives: numbers
    are coerced, labels clipped, the list capped. Nothing here is executed or trusted as
    instruction; the firewall still wraps the snapshot.
    """
    if not isinstance(raw, dict):
        return None
    top: list[dict[str, Any]] = []
    for entry in (raw.get("top") or [])[:40]:
        if not isinstance(entry, dict) or not entry.get("id"):
            continue
        try:
            pos = int(entry.get("pos") or 0)
            rank = round(float(entry.get("rank") or 0.0), 4)
        except (TypeError, ValueError):
            continue
        top.append({
            "id": str(entry["id"])[:120],
            "label": str(entry.get("label") or "")[:80],
            "pos": pos,
            "rank": rank,
        })
    if not top:
        return None
    out: dict[str, Any] = {
        "source": str(raw.get("source") or "local")[:16],
        "count": max(0, int(raw.get("count") or 0)) if str(raw.get("count") or "0").isdigit() else len(top),
        "top": top,
        "note": "PageRank over the live graph; covers every node on the map, federated hubs included",
    }
    edges = raw.get("edges")
    if isinstance(edges, int) and edges >= 0:
        out["edges"] = edges
    return out


@app.post("/api/ai/ask", dependencies=_MONITOR_READ_AUTH)
async def ai_ask(request: Request, body: dict):
    """AI assistant — live state + multi-provider LLM (default: deepseek-v4-pro).

    Auth: same as public read APIs — open when ``ALIEN_PUBLIC_READ=1`` (demo),
    otherwise Bearer ``ALIEN_API_TOKEN``. Rate-limited per client IP.
    """
    _ai_ask_rate_limit(request)
    question = (body.get("question") or "").strip()
    ui_locale = normalize_locale(body.get("locale", "en"))
    if not question:
        return {"answer": EMPTY_QUESTION[ui_locale], "actions": []}

    response_locale = resolve_response_locale(question, ui_locale)
    blocked = rejection_reason_if_blocked(question)
    if blocked:
        return {
            "answer": rejected_answer(response_locale),
            "actions": [],
            "meta": {
                "blocked": True,
                "firewall": "prompt_injection",
                "reason": blocked,
                "response_locale": response_locale,
                "ui_locale": ui_locale,
            },
        }

    # The server's own snapshot first: a caller-sent state is caller-written prompt text.
    state = LAST_MONITOR_STATE
    if state is None and isinstance(body.get("state"), dict):
        with contextlib.suppress(TypeError, ValueError):
            if len(json.dumps(body["state"], default=str)) <= _AI_CLIENT_STATE_MAX_BYTES:
                state = body["state"]
    if state is None:
        try:
            state = await _fetch_monitor_state()
        except Exception:
            state = None

    selected_node = body.get("selected_node_id") or body.get("selected_node")
    live_ctx = wrap_snapshot_for_llm(
        build_live_context(state, MODE, str(selected_node) if selected_node else None,
                           reputation=_safe_reputation(body.get("reputation")))
    )
    system = build_system_prompt(full_ecosystem_context(), response_locale, live_ctx)
    provider_id = body.get("provider") or body.get("provider_id")
    model_role = body.get("model_role") or "heavy"
    actions = resolve_nav_actions(question, state)
    safe_question = wrap_user_question_for_llm(question)

    if not any_provider_configured():
        answer = append_nav_hint(
            _fallback_answer(question, response_locale, state, MODE),
            actions,
            response_locale,
            state,
        )
        return {
            "answer": answer,
            "actions": actions,
            "meta": {
                "provider": "fallback",
                "live_state": state is not None,
                "response_locale": response_locale,
                "firewall": "passed",
            },
        }

    try:
        answer, meta = await generate_answer(
            question=safe_question,
            locale=response_locale,
            system_prompt=system,
            provider_id=provider_id,
            model_role=model_role,
        )
        answer = append_nav_hint(answer, actions, response_locale, state)
        meta["live_state"] = state is not None
        meta["ui_locale"] = ui_locale
        meta["response_locale"] = response_locale
        meta["firewall"] = "passed"
        return {"answer": answer, "actions": actions, "meta": meta}
    except Exception as e:
        fb = append_nav_hint(
            _fallback_answer(question, response_locale, state, MODE), actions, response_locale, state
        )
        return {
            "answer": fb + f"\n\n(LLM error: {e})",
            "actions": actions,
            "meta": {"provider": "fallback", "error": str(e), "response_locale": response_locale},
        }


@app.post("/api/metis/chat", dependencies=_MONITOR_AUTH)
async def metis_chat_endpoint(body: dict):
    """Chat with the METIS cognitive layer (proxied; key stays server-side).

    Offline-safe: if Metis is not running this returns a readable message rather
    than an error, so the monitor is never affected by Metis being down.
    """
    from metis_status import metis_chat as _metis_chat

    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        q = str(body.get("question") or body.get("message") or "").strip()
        if not q:
            return {"answer": "Ask Metis something to begin.", "error": "empty"}
        messages = [{"role": "user", "content": q}]
    model = str(body.get("model") or "metis")
    return await _metis_chat(messages, model=model)


# The give-up line, in three languages, with one guard in front of all of them.
#
# `_fallback_answer` is a chain of hand-written `if "<name>" in q` branches, so a component is
# answerable only if somebody wrote a branch for it. That is precisely how this assistant denied
# LOGOS, and later CHARON: both existed and were callable, neither had a branch. Consulting the
# live federation first means the answer set maintains itself; the wording below is only reached
# when the federation has never heard of it either.
_GIVE_UP = {
    "ru": "Спросите о хабе, SKOPOS, Metis, THEMIS, DIOSCURI, MOMUS, контрактах, плагинах, mesh или ACEX.",
    "es": "Pregunta sobre hub, SKOPOS, Metis, THEMIS, DIOSCURI, MOMUS, contratos, plugins o mesh.",
    "en": ("Ask about the hub, SKOPOS, Metis, THEMIS, DIOSCURI, MOMUS, contracts, plugins, "
           "desktop apps, service mesh, ACEX, SDKs, or current ecosystem state."),
}


def _LIVE_OR(locale: str, q: str, live_hint: str, state: dict | None = None) -> str:
    """The registry, then the map, then the give-up line — in that order.

    `_GIVE_UP` names one deployment's products, so on any other map it recommends a
    stranger's components while the viewer's own hub sits on screen. The graph is the only
    source that is right on every deployment, so it goes in front.
    """
    try:
        live = live_component_answer(q)
    except Exception:
        live = ""
    if not live and state:
        from live_graph import graph_overview

        try:
            live = graph_overview(state, locale)
        except Exception:
            live = ""
    return (live or _GIVE_UP.get(locale, _GIVE_UP["en"])) + live_hint


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

    # No LLM key must not turn discovery off. The graph is already the authoritative
    # live registry, so answer an exact live id/label before the hand-written FAQ. This
    # makes a newly announced KOVA, AEGIS, Atlas or Momus visible to the assistant on the
    # same tick it becomes visible on the map. Identity remains namespaced by parent Hub;
    # two providers called "Atlas" therefore remain two distinct components.
    live_match: dict | None = None
    live_id = match_live_node_id(question, state)
    if state and live_id:
        live_match = next(
            (
                node for node in state.get("nodes") or []
                if isinstance(node, dict) and str(node.get("id") or "") == live_id
            ),
            None,
        )
    if live_match is not None:
        # The graph is a graph: what a node is wired to is most of the answer to "where is
        # it". This used to report only label, status and url — enough to prove the node
        # existed, not enough to place it — so `live_graph.describe_node` walks the links.
        from live_graph import describe_node

        described = describe_node(state, str(live_match.get("id") or ""), locale)
        if described:
            return described + live_hint
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
        if "skopos" in q or "скопос" in q:
            return (
                "SKOPOS (Σκοπός) — спутник наблюдаемости флота AICOM: аналитика nginx/Apache по SSH, "
                "Security Center с 3D-картой угроз, история сканов и AI-аналитик. "
                "Дашборд: skopos.modelmarket.dev · репо: alexar76/skopos. "
                "На карте — узел observability на западной полке рядом с Metis."
                + live_hint
            )
        if "warden" in q or "варден" in q or "варден" in q or "файрвол" in q or "firewall" in q:
            return (
                "WARDEN — сам MCP-файрвол, отдельный npm-пакет `@aimarket/warden` "
                "(репо: alexar76/warden), без рантайм-зависимостей. На карте он ЕСТЬ — бирюзовый "
                "узел группы security между MOMUS и ARGUS, — но нарисован как СЛОЙ, а не хост: это "
                "библиотека, работающая внутри процесса того MCP-хоста, который её подключил, у неё "
                "нет ни порта, ни демона, ни своего /health. Поэтому телеметрия берётся с двух "
                "концов, у которых адрес есть: MOMUS публикует подписанный threat feed (в метриках "
                "узла — число записей, отказы публикации, свежесть фида против окна 24 ч и "
                "закреплённый ключ Ed25519), а ARGUS — референсный хост, поэтому блокировки видны в "
                "его телеметрии. `builtin_floor: 11` — то, что WARDEN применяет вообще без фида. "
                "Цепочка гейтов: статический скан всех полей определения инструмента (ruleset v12) → "
                "подписанный threat feed → origin (объявлен оператором или предложен удалённым "
                "каталогом) → pin определений и launch-identity. Решает только по локальным фактам: "
                "без оракула, без сети во время проверки, и оценка 0..1 — своя композитная, а НЕ "
                "репутация LUMEN (тот гейт удалён). Ставится перед любым MCP-хостом без перехода на "
                "ARGUS. THEMIS — шлюз до публикации, WARDEN — на вызове."
                + live_hint
            )
        if "momus" in q or "момус" in q or "момос" in q or "red team" in q or "красн" in q:
            return (
                "MOMUS (Μῶμος) — автономный red team экосистемы: безопасные read-only пробы "
                "против собственных компонентов, findings с подписью Ed25519, самообучение. "
                "Находит и подписывает, но не может платить себе — платит Treasury (отдельный ключ). "
                "Live: momus.modelmarket.dev · репо: alexar76/momus. На карте — узел security рядом с ARGUS."
                + live_hint
            )
        if (
            "themis" in q
            or "темис" in q
            or "темид" in q
            or "допуск" in q
            or "supply chain" in q
            or ("цепочк" in q and "постав" in q)
        ):
            return (
                "THEMIS (Θέμις) — шлюз допуска публикации AIMarket для сторонних агентов, "
                "MCP и плагинов. Подписанное решение approve / review / reject по манифесту, "
                "полномочиям, evidence и политике. Это НЕ Metis (познание) и НЕ WARDEN "
                "(файрвол на invoke). Режим Hub по умолчанию off, пока оператор не включит "
                "advisory/enforce. Capability: agent.security.supply-chain.audit@v1. "
                "Репо: alexar76/themis. На карте — узел THEMIS у Hub/Factory; скажите "
                "«покажи THEMIS» / «где темис?»."
                + live_hint
            )
        if (
            "hestia" in q
            or "гести" in q
            or "очаг" in q
            or "hearth" in q
            or "хостед" in q
        ):
            return (
                "HESTIA (Ἑστία) — очаг: изолированный hosted-runtime провайдеров "
                "способностей AIMarket на машинах оператора. Это НЕ каталог Hub, НЕ Factory "
                "и НЕ доска работ. Агенты появляются только после явного подписанного "
                "деплоя на этот хост; пустой roster значит «здесь никто не хостится», "
                "а не «рынок пуст». Isolation first. THEMIS по-прежнему может отказать "
                "в старте. Hub остаётся рынком. Live: hestia.modelmarket.dev · лендинг: "
                "alexar76.github.io/hestia/ · репо: alexar76/hestia. На карте — янтарный "
                "шар над Hub/THEMIS/Factory; скажите «покажи HESTIA» / «где очаг?»."
                + live_hint
            )
        if "treasury" in q or "трезури" in q or "трежери" in q or "казна" in q or "казн" in q:
            return (
                "Treasury — отдельный плательщик bounty за находки MOMUS: свой ключ и контейнер, "
                "выплата только после независимой верификации. MOMUS находит; Treasury платит. "
                "Live: momus.modelmarket.dev/treasury · репо: alexar76/treasury."
                + live_hint
            )
        if "bridges" in q or "бридж" in q or "мост" in q or "langchain" in q or "crewai" in q or "autogen" in q:
            return (
                "Bridges (aimarket-bridges) — третий платный канал вызовов после хаба и меша: "
                "возможности AIMarket как нативные инструменты в LangChain/LangGraph, CrewAI и "
                "AutoGen. Подписанные чеки проверяются ключом ИСТОЧНИКА возможности (не хаба), "
                "жёсткий потолок budget_usd резервируется ДО вызова. Это клиентская библиотека "
                "(pip aimarket-bridges), а не сервис: она работает внутри процесса покупателя. "
                "Поэтому на карте у узла НЕТ цифр оборота — их никто не считает; пустые метрики "
                "означают «не измеряется», а не «ноль». Доки: modeldev.modelmarket.dev/bridges/."
                + live_hint
            )
        if "metis" in q or "метис" in q:
            return (
                "METIS (μῆτις) — распределённый когнитивный слой над любым LLM: "
                "Understanding Council → confidence gate (fail-closed) → MoA → verifier. "
                "OpenAI-compatible API; опциональный confidence gate для AI-Factory. "
                "В мониторе — узел cognition + чат-панель, когда Metis online."
                + live_hint
            )
        if "dioscuri" in q or "диоскур" in q or "castor" in q or "pollux" in q:
            return (
                "DIOSCURI — близнецы CASTOR (Telegram) и POLLUX (Discord) с общей базой MNEMOSYNE "
                "(GitHub-sync, AEGIS firewall). THEOROS пишет колонку #the-canon. "
                "Репо: alexar76/dioscuri."
                + live_hint
            )
        if "theoros" in q or "теорос" in q or "canon" in q:
            return (
                "THEOROS — Agent Sovereignty Canon (семь принципов суверенности агентов). "
                "Лендинг: alexar76.github.io/theoros · runtime через DIOSCURI #the-canon."
                + live_hint
            )
        if "helios" in q or "гелиос" in q:
            return (
                "HELIOS — медиа/YouTube-агент экосистемы (рост канала, контент). "
                "Репо: alexar76/helios · узел на 3D-карте рядом с DIOSCURI."
                + live_hint
            )
        if ("gaia" in q or "гайя" in q or "гайю" in q or "гея" in q or "гею" in q or "iot" in q or "айот" in q
                or "датчик" in q or "сенсор" in q or "устройств" in q):
            return (
                "GAIA — шлюз физических оракулов, третий класс оракулов экосистемы "
                "(маторакулы → когнитивный METIS → физическая GAIA). Виртуальные "
                "IoT-устройства (погода, качество воздуха, энергоучёт): каждое показание "
                "подписано Ed25519-ключом устройства и проходит верификатор правдоподобия "
                "(границы / z-оценка / скорость / согласованность соседей / физика полей) "
                "перед списанием — по модели Pay-on-Verified врущий датчик автоматически "
                "возвращает деньги. Бесплатный реестр: gaia.fleet.status@v1. Демо: "
                "iot.modelmarket.dev · репо: alexar76/gaia. На карте — зелёный узел physical; "
                "клик открывает список устройств и что они передают. Развёрнутый шлюз сейчас "
                "отдаёт 4 симулятора; живые релеи реальных API (NWS, openSenseMap, OGC "
                "SensorThings) написаны и покрыты тестами, но пока не подключены в прод."
                + live_hint
            )
        if "sdk" in q:
            return "SDK: Dart, TypeScript, Rust. Протокол: discover → open_channel → invoke → close_channel → verify."
        if "mode" in q or "режим" in q or "test" in q or "tick" in q or "метрик" in q:
            return (
                f"Режим монитора: {(mode or MODE).upper()}. TEST — симуляция. UNI — локальная сеть + живые слои. LIVE — production."
                + live_hint
            )
        return _LIVE_OR("ru", q, live_hint, state)
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
        if "skopos" in q:
            return (
                "SKOPOS (Σκοπός) — satélite de observabilidad del flota: analítica nginx/Apache vía SSH, "
                "Security Center con mapa 3D, historial de escaneos y analista IA. "
                "Dashboard: skopos.modelmarket.dev · repo: alexar76/skopos."
                + live_hint
            )
        if "warden" in q or "cortafuegos" in q or "firewall" in q:
            return (
                "WARDEN es el cortafuegos MCP en sí, distribuido como su PROPIO paquete npm "
                "`@aimarket/warden` (repo: alexar76/warden), sin dependencias de ejecución. SÍ está "
                "en el mapa — nodo del grupo security entre MOMUS y ARGUS — pero dibujado como CAPA, "
                "no como host: es una biblioteca que corre dentro del proceso del host que la carga, "
                "sin puerto, sin demonio y sin /health propio. Por eso su telemetría viene de los dos "
                "extremos que sí tienen dirección: MOMUS publica el threat feed firmado (registros, "
                "rechazos, frescura frente a la ventana de 24 h, clave Ed25519 fijada) y ARGUS es el "
                "host de referencia, así que los bloqueos aparecen en su telemetría. `builtin_floor: "
                "11` es lo que WARDEN aplica sin feed alguno. Cadena de puertas: escaneo estático de "
                "todos los campos de la herramienta (ruleset v12) → threat feed firmado → origin → "
                "pinning de definiciones e identidad de arranque. Decide solo con hechos locales: sin "
                "oráculo, sin red durante la revisión, y su puntuación 0..1 es propia, NO la "
                "reputación de LUMEN (esa puerta se eliminó)."
                + live_hint
            )
        if "momus" in q or "red team" in q or "equipo rojo" in q:
            return (
                "MOMUS — red team autónomo: sondas de solo lectura, findings firmados Ed25519; "
                "encuentra y firma pero no puede pagarse a sí mismo (lo paga Treasury). "
                "Live: momus.modelmarket.dev · repo: alexar76/momus."
                + live_hint
            )
        if "themis" in q or "admisión" in q or "admision" in q or "cadena de suministro" in q:
            return (
                "THEMIS — puerta de admisión al publicar en AIMarket para agentes, MCP y plugins "
                "de terceros. Decisión firmada approve / review / reject. No es Metis ni WARDEN. "
                "Capability: agent.security.supply-chain.audit@v1 · repo: alexar76/themis. "
                "En el mapa: nodo THEMIS junto a Hub/Factory — di «muéstrame THEMIS»."
                + live_hint
            )
        if "hestia" in q or "hogar" in q or "âtre" in q or "hearth" in q:
            return (
                "HESTIA (Ἑστία) — el hogar: runtime aislado y alojado para proveedores de "
                "capacidad AIMarket en las máquinas del operador. No es el catálogo del Hub, "
                "ni Factory, ni un tablón de empleos. Los agentes aparecen solo tras un "
                "despliegue firmado en este host; un roster vacío significa «aquí no hay "
                "nadie alojado», no «el mercado está vacío». Isolation first. THEMIS aún "
                "puede rechazar el arranque. Hub sigue siendo el mercado. Live: "
                "hestia.modelmarket.dev · landing: alexar76.github.io/hestia/ · repo: "
                "alexar76/hestia. En el mapa: esfera ámbar sobre Hub/THEMIS/Factory — "
                "di «muéstrame HESTIA»."
                + live_hint
            )
        if "treasury" in q or "tesorer" in q:
            return (
                "Treasury — pagador de bounty separado para hallazgos de MOMUS; clave y contenedor propios. "
                "Live: momus.modelmarket.dev/treasury · repo: alexar76/treasury."
                + live_hint
            )
        if "bridges" in q or "puente" in q or "langchain" in q or "crewai" in q or "autogen" in q:
            return (
                "Bridges (aimarket-bridges) — el tercer canal de invocación de pago, junto al hub y "
                "la mesh: capacidades de AIMarket como herramientas nativas en LangChain/LangGraph, "
                "CrewAI y AutoGen. Recibos firmados verificados con la clave del ORIGEN de la "
                "capacidad (no la del hub) y un techo budget_usd reservado ANTES de cada llamada. "
                "Es una biblioteca cliente (pip aimarket-bridges), no un servicio: corre dentro del "
                "proceso del comprador. Por eso el nodo NO muestra cifras de facturación — nadie las "
                "cuenta; métricas vacías significan «no medido», no «cero». "
                "Docs: modeldev.modelmarket.dev/bridges/."
                + live_hint
            )
        if "metis" in q:
            return (
                "METIS (μῆτις) — capa cognitiva distribuida sobre cualquier LLM con council, "
                "confidence gate fail-closed, MoA y verificador. API compatible con OpenAI."
                + live_hint
            )
        if "dioscuri" in q or "castor" in q or "pollux" in q:
            return "DIOSCURI — gemelos CASTOR (Telegram) y POLLUX (Discord) con MNEMOSYNE + AEGIS. THEOROS escribe #the-canon." + live_hint
        if "theoros" in q or "canon" in q:
            return "THEOROS — canon de soberanía de agentes; landing alexar76.github.io/theoros." + live_hint
        if "helios" in q:
            return "HELIOS — agente de medios/YouTube del ecosistema. Repo: alexar76/helios." + live_hint
        if "gaia" in q or "iot" in q or "sensor" in q or "dispositiv" in q:
            return (
                "GAIA — pasarela de oráculos del mundo físico, la tercera clase de oráculos "
                "(oráculos matemáticos → METIS cognitivo → GAIA física). Dispositivos IoT "
                "virtuales (clima, calidad del aire, energía): cada lectura se firma con una "
                "clave Ed25519 por dispositivo y pasa un verificador de plausibilidad antes de "
                "cobrar — con Pay-on-Verified un sensor mentiroso reembolsa automáticamente. "
                "Registro gratuito: gaia.fleet.status@v1. Demo: iot.modelmarket.dev · repo: "
                "alexar76/gaia. En el mapa es el nodo physical verde; al hacer clic muestra sus "
                "dispositivos y qué transmiten. La pasarela desplegada sirve 4 simuladores; los "
                "relés de sensores reales (NWS, openSenseMap, OGC SensorThings) están implementados "
                "y probados, pero aún no conectados en producción."
                + live_hint
            )
        if "sdk" in q:
            return "SDK Dart, TypeScript y Rust con el mismo flujo de protocolo."
        if "mode" in q or "test" in q or "tick" in q:
            return f"Modo actual: {(mode or MODE).upper()}. TEST simula; UNI cadena local + capas vivas; LIVE producción." + live_hint

        return _LIVE_OR("es", q, live_hint, state)
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
    if "skopos" in q:
        return (
            "SKOPOS (Σκοπός) is the fleet observability satellite: nginx/Apache analytics over SSH, "
            "Security Center with 3D threat map, scan history, and an AI analyst. "
            "Dashboard: skopos.modelmarket.dev · repo: alexar76/skopos. "
            "On the map it is the observability node on the west shelf near Metis."
            + live_hint
        )
    if "warden" in q or "firewall" in q:
        return (
            "WARDEN is the MCP firewall itself, shipped as its OWN zero-dependency npm package "
            "`@aimarket/warden` (repo: alexar76/warden). It IS on this map — a security-group node "
            "between MOMUS and ARGUS — but drawn as a LAYER, not a host: a library that runs "
            "in-process inside whatever MCP host loads it, with no port, no daemon and no /health of "
            "its own. Its telemetry is therefore borrowed from the two ends that do have addresses: "
            "MOMUS publishes the signed threat feed it consumes (feed records, publisher refusals, "
            "freshness against WARDEN's 24 h window, the pinned Ed25519 key), and ARGUS is the "
            "reference host, so blocks surface as ARGUS telemetry. `builtin_floor: 11` is what a "
            "WARDEN install enforces with no feed at all. Gate chain per connection: static scan of "
            "every advertised tool field (ruleset v12) -> signed threat feed -> origin "
            "(operator-declared vs remote catalog) -> tool-def and launch-identity pinning. It decides "
            "from local facts only: no oracle, no socket while vetting, and its 0..1 score is its own "
            "composite, NOT a LUMEN reputation score (that gate was removed). Usable in front of any "
            "MCP host without adopting ARGUS. THEMIS gates publication, WARDEN gates the invoke."
            + live_hint
        )
    if "momus" in q or "red team" in q:
        return (
            "MOMUS is the autonomous red team: safe read-only probes → Ed25519-signed findings; "
            "self-learning. Finds and signs but cannot pay itself — the Treasury (separate key) pays. "
            "Live: momus.modelmarket.dev · repo: alexar76/momus. On the map: security node near ARGUS."
            + live_hint
        )
    if (
        "themis" in q
        or "admission" in q
        or "supply-chain" in q
        or "supply chain" in q
    ):
        return (
            "THEMIS (Θέμις) is AIMarket's publish-time admission gate for third-party agents, "
            "MCP servers and plugins. Signed approve / review / reject from a bounded dossier. "
            "Not Metis (cognition) and not WARDEN (invoke-time firewall). Hub mode defaults to "
            "off until advisory/enforce. Capability: agent.security.supply-chain.audit@v1. "
            "Repo: alexar76/themis. On the map: THEMIS near Hub/Factory — say «show THEMIS»."
            + live_hint
        )
    if "hestia" in q or "hearth" in q or "hosted runtime" in q:
        return (
            "HESTIA (Ἑστία) is the hearth: an isolated hosted runtime for AIMarket "
            "capability providers on the operator's machines. Not the Hub catalogue, "
            "not Factory, not a job board. Agents appear only after an explicit signed "
            "deploy onto this host; an empty roster means nothing is hosted here, not "
            "that the market is empty. Isolation first. THEMIS can still refuse a start. "
            "Hub stays the market. Live: hestia.modelmarket.dev · landing: "
            "alexar76.github.io/hestia/ · repo: alexar76/hestia. On the map: ember "
            "sphere above Hub/THEMIS/Factory — say «show HESTIA»."
            + live_hint
        )
    if "treasury" in q or "bounty payer" in q or "bounty treasury" in q:
        return (
            "Treasury is the separate bounty payer for MOMUS findings — own key and container; "
            "pays only after independent verification. Live: momus.modelmarket.dev/treasury · "
            "repo: alexar76/treasury."
            + live_hint
        )
    if "bridges" in q or "langchain" in q or "langgraph" in q or "crewai" in q or "autogen" in q:
        return (
            "Bridges (aimarket-bridges) is the ecosystem's third paid invoke channel, after the hub "
            "and the mesh: AIMarket capabilities as native tools in LangChain/LangGraph, CrewAI and "
            "AutoGen. Signed receipts are verified against the capability's ORIGIN key rather than "
            "the hub's (42 of 47 capabilities are federated), and a hard budget_usd ceiling is "
            "claimed before each call. It is a client LIBRARY, not a service — it runs inside the "
            "buyer's own process, so the node shows NO billing figures: nothing counts invokes, "
            "receipts or budget rejections on the bridge side. Empty metrics there mean "
            "'not instrumented', not 'zero traffic'. Docs: modeldev.modelmarket.dev/bridges/ · "
            "repo: alexar76/aimarket-bridges."
            + live_hint
        )
    if "metis" in q:
        return (
            "METIS (μῆτις) is the distributed cognitive layer over any LLM — Understanding Council, "
            "fail-closed confidence gate, layered MoA, verifier-with-retry. OpenAI-compatible API; "
            "optional factory confidence gate. In-monitor chat when Metis is online."
            + live_hint
        )
    if "dioscuri" in q or "castor" in q or "pollux" in q:
        return (
            "DIOSCURI runs twin community agents — CASTOR (Telegram) and POLLUX (Discord) — "
            "with shared MNEMOSYNE knowledge (GitHub-sync, AEGIS firewall). THEOROS collaborates on #the-canon."
            + live_hint
        )
    if "theoros" in q or "canon" in q:
        return (
            "THEOROS is the Agent Sovereignty Canon (seven precepts). Landing: alexar76.github.io/theoros; "
            "weekly column via DIOSCURI #the-canon."
            + live_hint
        )
    if "helios" in q:
        return "HELIOS is the ecosystem YouTube/media growth agent (alexar76/helios)." + live_hint
    if "gaia" in q or "iot" in q or "sensor" in q or ("device" in q and "desktop" not in q):
        return (
            "GAIA is the physical-world oracle gateway — the ecosystem's third oracle class "
            "(math oracles → cognitive METIS → physical GAIA). Virtual IoT devices and live "
            "public-API relays (weather, air, tide, river, marine, grid, quake, energy) each "
            "sign every reading with a per-device Ed25519 key and pass a plausibility verifier "
            "(bounds / z-score / rate / sibling-consistency / stuck / cross-field physics) "
            "before billing — under Pay-on-Verified escrow a lying sensor automatically refunds "
            "the buyer. Free registry: gaia.fleet.status@v1. Live demo: iot.modelmarket.dev "
            "(also gaia.modelmarket.dev) · repo: alexar76/gaia. On the map it is the green "
            "physical node; clicking it lists the devices and what each transmits. LIVE vs SIM "
            "is marked by provenance ``source`` on the fleet status."
            + live_hint
        )
    if "sdk" in q:
        return "Three SDKs — Dart, TypeScript, Rust — share discover → open_channel → invoke → close_channel → verify."
    if "mode" in q or "test" in q or "tick" in q or "metric" in q:
        return (
            f"Monitor mode: {(mode or MODE).upper()}. TEST simulates; UNI uses local chain + live Hub/Mesh/Factory/Prometheus; "
            "LIVE reads production RPC and services from .env."
            + live_hint
        )
    return _LIVE_OR("en", q, live_hint, state)


# ---------------------------------------------------------------------------
# WebSocket — real-time streaming
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    if not monitor_websocket_origin_allowed(ws.headers.get("origin"), ws.headers.get("host")):
        await ws.close(code=1008)
        return
    auth_header = (ws.headers.get("authorization") or "").strip()
    ws_token = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else None
    ws_authed = monitor_ws_token_valid(ws_token, ws.cookies.get(MONITOR_SESSION_COOKIE))
    # Same read gate as the REST endpoints (require_monitor_read_auth): a
    # locked-down prod deploy (ALIEN_API_TOKEN set, ALIEN_PUBLIC_READ unset)
    # must not stream live state to an anonymous client. The public-demo tier
    # (ALIEN_PUBLIC_READ=1 or non-prod) and token-authed clients still pass.
    if not ws_authed and not monitor_public_read_allowed():
        await ws.close(code=1008)  # policy violation
        return
    await ws.accept()
    CONNECTED_CLIENTS.add(ws)
    _viewer_arrived.set()
    _ws_client_modes[id(ws)] = get_server_mode()
    _ws_client_authed[id(ws)] = ws_authed
    initial = _cached_monitor_state()
    if not initial and get_server_mode() == "universe" and get_universe().entities:
        initial = await asyncio.to_thread(_universe_fast_snapshot)
    if not initial:
        initial = await _fetch_monitor_state()
    if initial:
        await ws.send_text(json.dumps({
            "type": "state_update",
            "data": _state_for_ws(initial, ws_authed=ws_authed),
        }, default=str))
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            cmd = msg.get("cmd", "")
            if cmd == "set_mode":
                if not _ws_client_authed.get(id(ws), False) and not monitor_control_token_valid(msg.get("token")):
                    await ws.send_text(json.dumps({
                        "type": "error",
                        "detail": "unauthorized",
                        "cmd": cmd,
                    }))
                    continue
                requested = _normalize_mode(str(msg.get("mode", "")).strip().lower())
                if requested:
                    _ws_client_modes[id(ws)] = session_tick_mode(requested, get_server_mode())
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
                if not snap:
                    snap = await _fetch_monitor_state(client_mode)
                if snap:
                    await ws.send_text(json.dumps({
                        "type": "state_update",
                        "data": _state_for_ws(snap, ws_authed=_ws_client_authed.get(id(ws), False)),
                    }, default=str))
                await ws.send_text(json.dumps({"type": "mode_changed", "mode": client_mode}))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        CONNECTED_CLIENTS.discard(ws)
        _ws_client_modes.pop(id(ws), None)
        _ws_client_authed.pop(id(ws), None)


# ---------------------------------------------------------------------------
# Serve static frontend in production
# ---------------------------------------------------------------------------

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

# The build now ships its own webfonts instead of pulling them from Google, and StaticFiles
# types responses from `mimetypes`, which reads /etc/mime.types — absent from the slim image, so
# the faces went out as application/octet-stream. Browsers accept that because the stylesheet
# declares format('woff2'), but anything stricter in front of this (a CDN deciding what to
# compress, a nosniff-enforcing client) has no reason to.
mimetypes.add_type("font/woff2", ".woff2")

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
