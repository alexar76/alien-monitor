"""The ecosystem map the monitor draws: the generic and AICOM topologies, and the live lottery
overlay.
"""

from __future__ import annotations

from factory_products import factory_public_url, mesh_public_url
from hub_affiliation import hub_public_url
from lottery_layers import lottery_financial_links, lottery_node_spec
from argus_layers import argus_node_spec, argus_topology_links
from hephaestus_layers import hephaestus_node_spec, hephaestus_topology_links
from factory_agents import factory_agents_node_spec, factory_agents_topology_links
from dioscuri_layers import dioscuri_node_spec, dioscuri_topology_links
from helios_layers import helios_node_spec, helios_topology_links
from metis_layers import metis_node_spec, metis_topology_links
from skopos_layers import skopos_node_spec, skopos_topology_links
from gaia_layers import gaia_node_spec, gaia_topology_links
from atlas_layers import atlas_node_spec, atlas_topology_links
from bridges_layers import bridges_node_spec, bridges_topology_links
from themis_layers import themis_node_spec, themis_topology_links
from basanos_layers import basanos_node_spec, basanos_topology_links
from hestia_layers import hestia_node_spec, hestia_topology_links
from dolos_layers import dolos_node_spec, dolos_topology_links
from settlement_layers import settlement_node_spec, settlement_topology_links
from competing_lab_layers import (
    competing_hub_node_spec,
    competing_lab_topology_links,
    signal_hunt_hub_node_spec,
    signal_hunt_node_spec,
    use_cases_node_spec,
)
from momus_layers import momus_node_spec, momus_topology_links, treasury_node_spec
from warden_layers import warden_node_spec, warden_topology_links
from histor_layers import histor_node_spec, histor_topology_links
from logos_layers import logos_node_spec, logos_topology_links
from live_lottery_feed import live_lottery_fresh


# ---------------------------------------------------------------------------
# Ecosystem topology — defines the graph structure
# ---------------------------------------------------------------------------


def build_topology() -> tuple[list[dict], list[dict]]:
    """Return (nodes, links) for the ecosystem graph.

    Which graph depends on the deployment profile. The built-in shelf below describes the
    AICOM ecosystem and nothing else; a Monitor pointed at somebody else's hub gets the
    generic map instead, and its own ecosystem arrives from what that hub declares.
    """
    from deployment_profile import owns_builtin_shelf

    if owns_builtin_shelf():
        nodes, links = build_aicom_topology()
        # The oracle ring is part of that shelf. It used to be appended by each caller
        # instead, which is how eighteen of our oracles kept arriving on a deployment
        # whose own map had already been reduced to two nodes.
        from oracle_family import append_oracle_family_graph

        append_oracle_family_graph(nodes, links)
    else:
        nodes, links = build_generic_topology()
    # Hop 0 is "ours": this hub and what it runs. Discovery tags everything further out,
    # and the scene reads the hop to decide what is a sun and what is a planet.
    for node in nodes:
        node.setdefault("hop", 0)
    return nodes, links


def build_generic_topology() -> tuple[list[dict], list[dict]]:
    """The map for a deployment that is not ours.

    Two nodes we can honestly assert — this hub, and the crawl that finds its peers —
    plus whatever the operator declared locally. Everything else is discovered: the hub's
    own providers come from its signed `ecosystem.nodes`, its peers from federation.
    """
    from deployment_profile import own_components
    from ecosystem_layout import primary_hub_child_position

    nodes: list[dict] = [
        {
            "id": "hub",
            "label": "AIMarket Hub",
            "group": "core",
            "icon": "hub",
            "role": "hub",
            "url": hub_public_url(),
            "description": "Federated capability catalog + payment routing",
            "metrics": {
                "peers": 0,
                "capabilities": 0,
                "channels_open": 0,
                "invocations_24h": 0,
                "trust_score": 1.0,
            },
            "status": "unknown",
            "hop": 0,
            "position": {"x": 0, "y": 0, "z": 0},
        },
        {
            "id": "federation",
            "label": "Federation",
            "group": "network",
            "icon": "globe",
            "description": "BFS peer discovery across federated hubs",
            "metrics": {"peers": 0, "crawls": 0},
            "status": "unknown",
            "hop": 0,
            "position": {"x": -2, "y": 5, "z": 1},
        },
    ]
    links: list[dict] = [
        {"source": "hub", "target": "federation", "label": "Peer crawl"},
    ]

    declared = own_components()
    for index, spec in enumerate(declared):
        node = dict(spec)
        node.setdefault("metrics", {})
        node["status"] = "unknown"
        node["hop"] = 0
        node["position"] = primary_hub_child_position(index, len(declared))
        nodes.append(node)
        links.append({
            "source": "hub", "target": node["id"], "label": "local component",
            "kind": "ecosystem",
        })
    return nodes, links


def build_aicom_topology() -> tuple[list[dict], list[dict]]:
    """The built-in AICOM shelf. Only ever drawn by a Monitor pointed at the AICOM hub."""
    nodes: list[dict] = [
        {
            "id": "hub",
            "label": "AIMarket Hub",
            "group": "core",
            "icon": "hub",
            "role": "hub",
            # Operator card link — public HTTPS edge, not Docker HUB_URL (:9083).
            "url": hub_public_url(),
            "description": "Federated capability catalog + payment routing",
            "metrics": {
                "peers": 0,
                "capabilities": 0,
                "channels_open": 0,
                "invocations_24h": 0,
                "trust_score": 1.0,
            },
            "status": "unknown",
            "position": {"x": 0, "y": 0, "z": 0},
        },
        {
            "id": "factory",
            "label": "AI-Factory",
            "group": "core",
            "icon": "factory",
            "role": "hub",
            "color": "#00f0ff",
            "url": factory_public_url(),
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
            # Public edge for the card; MESH_URL (loopback) is only how this process polls it.
            "url": mesh_public_url(),
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
        hephaestus_node_spec(),
        factory_agents_node_spec(),
        dioscuri_node_spec(),
        helios_node_spec(),
        metis_node_spec(),
        skopos_node_spec(),
        gaia_node_spec(),
        atlas_node_spec(),
        momus_node_spec(),
        warden_node_spec(),
        histor_node_spec(),
        treasury_node_spec(),
        logos_node_spec(),
        bridges_node_spec(),
        themis_node_spec(),
        basanos_node_spec(),
        hestia_node_spec(),
        dolos_node_spec(),
        settlement_node_spec(),
        competing_hub_node_spec(),
        signal_hunt_hub_node_spec(),
        signal_hunt_node_spec(),
        use_cases_node_spec(),
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
    links.extend(hephaestus_topology_links())
    links.extend(factory_agents_topology_links())
    links.extend(dioscuri_topology_links())
    links.extend(helios_topology_links())
    links.extend(metis_topology_links())
    links.extend(skopos_topology_links())
    links.extend(gaia_topology_links())
    links.extend(atlas_topology_links())
    links.extend(momus_topology_links())
    links.extend(warden_topology_links())
    links.extend(histor_topology_links())
    links.extend(logos_topology_links())
    links.extend(bridges_topology_links())
    links.extend(themis_topology_links())
    links.extend(basanos_topology_links())
    links.extend(hestia_topology_links())
    links.extend(dolos_topology_links())
    links.extend(settlement_topology_links())
    links.extend(competing_lab_topology_links())

    return nodes, links


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
