"""Seeding the universe's entities: one per ecosystem component, the competing lab and the
oracle family.
"""

from __future__ import annotations


from universe_entities import EcosystemEntity


class EntitySeedingMixin:
    """Seed the universe's entities."""

    def seed_entities(self):
        """Seed topology skeleton — metrics filled on first tick from live layers."""
        from lottery_layers import lottery_node_spec
        from factory_products import factory_public_url
        from universe_layers import layer_urls
        from ecosystem_layout import NODE_POSITIONS, node_position

        urls = layer_urls()
        from hub_affiliation import hub_public_url

        specs = [
            # Operator card uses public HTTPS; layer_urls()[\"hub\"] stays the Docker API poll target.
            ("hub", "AIMarket Hub", "core", "core", "hub", {"x": 0, "y": 0, "z": 0}, hub_public_url()),
            ("factory", "AI-Factory", "core", "core", "factory", {"x": 4, "y": 2, "z": -2}, factory_public_url()),
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
            # Prefer the shared layout anchors — hard-coded UNI slots drifted and
            # stacked Federation on top of factory Agents.
            ent.position = dict(NODE_POSITIONS[eid]) if eid in NODE_POSITIONS else pos
            ent.url = url
            ent.metrics = {}
            if eid == "hub":
                ent.role = "hub"
            if eid == "factory":
                ent.role = "hub"
                ent.color = "#00f0ff"
            self.entities[eid] = ent
        lot_spec = lottery_node_spec()
        lot = EcosystemEntity(
            lot_spec["id"],
            lot_spec["label"],
            "economy",
            lot_spec["group"],
            icon=lot_spec["icon"],
            description=lot_spec["description"],
        )
        lot.position = lot_spec["position"]
        lot.url = lot_spec.get("url")
        lot.metrics = dict(lot_spec.get("metrics") or {})
        lot.color = "#ffd700"
        self.entities[lot.id] = lot
        from argus_layers import argus_node_spec

        arg_spec = argus_node_spec(mode="universe")
        arg = EcosystemEntity(
            arg_spec["id"],
            arg_spec["label"],
            "agent",
            arg_spec["group"],
            icon=arg_spec["icon"],
            description=arg_spec["description"],
        )
        arg.position = arg_spec["position"]
        arg.url = arg_spec["url"]
        arg.metrics = dict(arg_spec.get("metrics") or {})
        arg.status = arg_spec.get("status", "offline")
        arg.color = "#36e6ff"
        self.entities[arg.id] = arg

        # Universe mode renders self.entities, NOT build_topology() — a node seeded
        # only there is invisible here (the lesson MOMUS and LOGOS both taught).
        from factory_agents import factory_agents_node_spec

        fa_spec = factory_agents_node_spec(mode="universe")
        fa = EcosystemEntity(
            fa_spec["id"],
            fa_spec["label"],
            "agent",
            fa_spec["group"],
            icon=fa_spec["icon"],
            description=fa_spec["description"],
        )
        # Always re-anchor from the shared layout (never a stale seed copy).
        fa.position = node_position("factory_agents", fallback=fa_spec["position"])
        fa.url = fa_spec["url"]
        fa.metrics = dict(fa_spec.get("metrics") or {})
        fa.status = fa_spec.get("status", "idle")
        fa.color = "#7ee787"
        self.entities[fa.id] = fa

        from dioscuri_layers import dioscuri_node_spec

        dio_spec = dioscuri_node_spec(mode="universe")
        dio = EcosystemEntity(
            dio_spec["id"],
            dio_spec["label"],
            "community",
            dio_spec["group"],
            icon=dio_spec["icon"],
            description=dio_spec["description"],
        )
        dio.position = dio_spec["position"]
        dio.url = dio_spec["url"]
        dio.metrics = dict(dio_spec.get("metrics") or {})
        dio.status = dio_spec.get("status", "offline")
        dio.color = "#c9a227"
        self.entities[dio.id] = dio
        from helios_layers import helios_node_spec

        hel_spec = helios_node_spec(mode="universe")
        hel = EcosystemEntity(
            hel_spec["id"],
            hel_spec["label"],
            "broadcast",
            hel_spec["group"],
            icon=hel_spec["icon"],
            description=hel_spec["description"],
        )
        hel.position = hel_spec["position"]
        hel.url = hel_spec["url"]
        hel.metrics = dict(hel_spec.get("metrics") or {})
        hel.status = hel_spec.get("status", "offline")
        hel.color = "#ff6b35"
        self.entities[hel.id] = hel
        self._seed_metis_entity()
        self._seed_skopos_entity()
        self._seed_gaia_entity()
        self._seed_atlas_entity()
        self._seed_hephaestus_entity()
        self._seed_momus_entity()
        self._seed_warden_entity()
        self._seed_histor_entity()
        self._seed_treasury_entity()
        self._seed_logos_entity()
        self._seed_bridges_entity()
        self._seed_themis_entity()
        self._seed_basanos_entity()
        self._seed_hestia_entity()
        self._seed_dolos_entity()
        self._seed_settlement_entity()
        self._seed_competing_lab_entities()
        self._seed_oracle_family()
        print(f"[Universe] {len(self.entities)} nodes ready (incl. oracle family) — awaiting layer poll")

    def _seed_hephaestus_entity(self) -> None:
        """The forge. Universe mode builds its graph from these entities, NOT from
        build_topology(), and the apply_*_graph helpers only DECORATE a node that already
        exists — so a satellite registered only in build_topology() is invisible here."""
        if "hephaestus" in self.entities:
            return
        from hephaestus_layers import hephaestus_node_spec

        spec = hephaestus_node_spec(mode="universe")
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "studio",
            spec["group"],
            icon=spec.get("icon"),
            description=spec.get("description"),
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "offline")
        ent.color = "#ffa94d"
        self.entities[ent.id] = ent

    def _seed_momus_entity(self) -> None:
        """Adversarial-audit red team — the offensive complement to ARGUS's defensive WARDEN.

        Universe mode builds its graph from these entities, NOT from build_topology(), and the
        apply_*_graph helpers only DECORATE a node that already exists. So a satellite that is only
        registered in build_topology() is invisible here — which is exactly what happened: the map
        had no MOMUS node and the assistant, asked "where is momus", reported that it was not part of
        the ecosystem at all.
        """
        if "momus" in self.entities:
            return
        from momus_layers import momus_node_spec

        spec = momus_node_spec(mode="universe")
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "security",
            spec["group"],
            icon=spec.get("icon"),
            description=spec.get("description"),
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "offline")
        ent.color = "#ff2d6f"
        self.entities[ent.id] = ent

    def _seed_warden_entity(self) -> None:
        """The invoke-time firewall, drawn as a LAYER.

        WARDEN is a library — no port, no /health — so it is the one security node with no host of
        its own. It was left off the graph for exactly that reason, and the assistant then answered
        "where is WARDEN?" with "inside ARGUS": a firewall the whole ecosystem depends on, rendered
        as one agent's internal feature. Its telemetry is borrowed from the two ends that do have
        addresses (MOMUS publishes the signed feed, ARGUS enforces it).
        """
        if "warden" in self.entities:
            return
        from warden_layers import warden_node_spec

        spec = warden_node_spec(mode="universe")
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "security",
            spec["group"],
            icon=spec.get("icon"),
            description=spec.get("description"),
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "idle")
        ent.color = "#4ad9c4"
        self.entities[ent.id] = ent

    def _seed_treasury_entity(self) -> None:
        """The separately-keyed payer. A distinct node on purpose: the whole design rests on MOMUS
        and the Treasury being different principals, and a map that drew them as one would show the
        opposite of the property that matters."""
        if "treasury" in self.entities:
            return
        from momus_layers import treasury_node_spec

        spec = treasury_node_spec(mode="universe")
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "security",
            spec["group"],
            icon=spec.get("icon"),
            description=spec.get("description"),
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "offline")
        ent.color = "#f6a92b"
        self.entities[ent.id] = ent

    def _seed_histor_entity(self) -> None:
        """The MCP transparency log; must exist because UNI ignores build_topology()."""
        if "histor" in self.entities:
            return
        from histor_layers import histor_node_spec

        spec = histor_node_spec(mode="universe")
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "security",
            spec["group"],
            icon=spec.get("icon"),
            description=spec.get("description"),
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "offline")
        ent.color = spec.get("color", "#ffd58a")
        self.entities[ent.id] = ent

    def _seed_logos_entity(self) -> None:
        """Read-only federation intelligence must exist in the graph before live data decorates it.

        Universe mode renders ``self.entities`` rather than ``build_topology()``.  Keeping LOGOS
        only in the static topology made ``apply_logos_to_nodes`` a silent no-op in this mode and
        left the monitor claiming that a documented, deployed component was absent.
        """
        if "logos" in self.entities:
            return
        from logos_layers import logos_node_spec

        spec = logos_node_spec()
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "analytics",
            spec["group"],
            icon=spec.get("icon"),
            description=spec.get("description"),
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "unknown")
        ent.color = "#00e5ff"
        self.entities[ent.id] = ent

    def _seed_bridges_entity(self) -> None:
        """The third paid invoke channel (hub, mesh, bridges) — framework-native tool export.

        Seeded here and not only in build_topology() for the reason the MOMUS gap taught: universe
        mode renders ``u.entities``, and ``apply_bridges_graph`` only DECORATES, returning early
        when the node is absent. A satellite registered in build_topology() alone is invisible in
        this mode while looking perfectly wired in the diff.

        The entity keeps ``metrics = {}`` from the spec — empty, not zeroed. Nothing in the UNI
        simulator fills it in later either: this channel is uninstrumented everywhere, and the
        simulator inventing a turnover for it would be the worst possible place to do so.
        """
        if "bridges" in self.entities:
            return
        from bridges_layers import bridges_node_spec

        spec = bridges_node_spec(mode="universe")
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "channel",
            spec["group"],
            icon=spec.get("icon"),
            description=spec.get("description"),
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "offline")
        ent.color = "#5ad1ff"
        self.entities[ent.id] = ent

    def _seed_themis_entity(self) -> None:
        """Publish admission gate; must exist because UNI ignores build_topology()."""
        if "themis" in self.entities:
            return
        from themis_layers import themis_node_spec

        spec = themis_node_spec(mode="universe")
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "security",
            spec["group"],
            icon=spec.get("icon"),
            description=spec.get("description"),
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "offline")
        ent.color = spec.get("color", "#66f7c5")
        self.entities[ent.id] = ent

    def _seed_settlement_entity(self) -> None:
        """The settlement node exists in UNI too: the universe has its own escrow, and the
        node's job is to show where an authorisation becomes chain state on whatever chain
        this mode is pointed at."""
        if "settlement" in self.entities:
            return
        from settlement_layers import settlement_node_spec

        spec = settlement_node_spec(mode="universe")
        # An EcosystemEntity, not a dict: the universe calls `.to_node()` on everything in
        # `entities`, so a plain dict here is a 500 on /api/topology — which is exactly what it
        # was until this line was fixed.
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "crypto",
            spec["group"],
            icon=spec.get("icon"),
            description=spec.get("description"),
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "offline")
        ent.color = spec.get("color", "#5ad1a8")
        self.entities[ent.id] = ent

    def _seed_basanos_entity(self) -> None:
        """Solidity touchstone; must exist because UNI ignores build_topology()."""
        if "basanos" in self.entities:
            return
        from basanos_layers import basanos_node_spec

        spec = basanos_node_spec(mode="universe")
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "security",
            spec["group"],
            icon=spec.get("icon"),
            description=spec.get("description"),
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "offline")
        ent.color = spec.get("color", "#e8c36a")
        self.entities[ent.id] = ent

    def _seed_hestia_entity(self) -> None:
        """The hearth; must exist because UNI ignores build_topology()."""
        if "hestia" in self.entities:
            return
        from hestia_layers import hestia_node_spec

        spec = hestia_node_spec(mode="universe")
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "infra",
            spec["group"],
            icon=spec.get("icon"),
            description=spec.get("description"),
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "offline")
        ent.color = spec.get("color", "#ff9a3c")
        self.entities[ent.id] = ent

    def _seed_dolos_entity(self) -> None:
        """Dynamic EVM red team; must exist because UNI ignores build_topology()."""
        if "dolos" in self.entities:
            return
        from dolos_layers import dolos_node_spec

        spec = dolos_node_spec(mode="universe")
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "security",
            spec["group"],
            icon=spec.get("icon"),
            description=spec.get("description"),
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "idle")
        ent.color = spec.get("color", "#e5484d")
        self.entities[ent.id] = ent

    def _seed_competing_lab_entities(self) -> None:
        """Second galaxy: Competing Lab Hub + Signal Hunt + use-cases portal.

        Far-offset positions live in ecosystem_layout.COMPETING_GALAXY_ANCHOR so the cluster
        does not collapse into the primary federation ring. Universe mode must seed these
        here — build_topology() alone is invisible in UNI.
        """
        from competing_lab_layers import (
            competing_hub_node_spec,
            signal_hunt_hub_node_spec,
            signal_hunt_node_spec,
            use_cases_node_spec,
        )

        colors = {
            "competing_hub": "#ff8c42",
            "signal_hunt_hub": "#d946ef",
            "signal_hunt": "#ff5ec8",
            "use_cases": "#c4f542",
        }
        for spec in (
            competing_hub_node_spec(),
            signal_hunt_hub_node_spec(),
            signal_hunt_node_spec(),
            use_cases_node_spec(),
        ):
            eid = spec["id"]
            if eid in self.entities:
                # Refresh identity so role/icon drift is corrected (hub vs game).
                ent = self.entities[eid]
                if spec.get("role") is not None:
                    ent.role = spec.get("role")
                if spec.get("icon"):
                    ent.icon = spec["icon"]
                if spec.get("group"):
                    ent.group = spec["group"]
                if spec.get("galaxy"):
                    ent.galaxy = spec["galaxy"]
                if colors.get(eid):
                    ent.color = colors[eid]
                if spec.get("description"):
                    ent.description = spec["description"]
                if spec.get("label"):
                    ent.name = spec["label"]
                continue
            ent = EcosystemEntity(
                eid,
                spec["label"],
                "network",
                spec["group"],
                icon=spec.get("icon"),
                description=spec.get("description"),
            )
            ent.position = spec["position"]
            ent.url = spec.get("url")
            ent.metrics = dict(spec.get("metrics") or {})
            ent.status = spec.get("status", "unknown")
            ent.color = colors.get(eid, "#ff8c42")
            # Stash hub role / galaxy on the entity so to_node can forward them.
            ent.role = spec.get("role")
            ent.galaxy = spec.get("galaxy")
            self.entities[eid] = ent

    def _seed_gaia_entity(self) -> None:
        """Physical-oracle gateway — third oracle class (math → METIS → GAIA)."""
        if "gaia" in self.entities:
            return
        from gaia_layers import gaia_node_spec

        spec = gaia_node_spec(mode="universe")
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "physical",
            spec["group"],
            icon=spec["icon"],
            description=spec["description"],
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "offline")
        ent.color = "#43e65a"
        self.entities[ent.id] = ent

    def _seed_atlas_entity(self) -> None:
        """Physical sensor map surface over GAIA live relays."""
        if "atlas" in self.entities:
            return
        from atlas_layers import atlas_node_spec

        spec = atlas_node_spec(mode="universe")
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "physical",
            spec["group"],
            icon=spec["icon"],
            description=spec["description"],
        )
        ent.position = spec["position"]
        ent.url = spec.get("url")
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "offline")
        ent.color = "#3dd6c6"
        self.entities[ent.id] = ent

    def _seed_metis_entity(self) -> None:
        if "metis" in self.entities:
            return
        from metis_layers import metis_node_spec

        met_spec = metis_node_spec(mode="universe")
        met = EcosystemEntity(
            met_spec["id"],
            met_spec["label"],
            "cognition",
            met_spec["group"],
            icon=met_spec["icon"],
            description=met_spec["description"],
        )
        met.position = met_spec["position"]
        met.url = met_spec["url"]
        met.metrics = dict(met_spec.get("metrics") or {})
        met.status = met_spec.get("status", "offline")
        met.color = "#9b59ff"
        self.entities[met.id] = met

    def _seed_skopos_entity(self) -> None:
        if "skopos" in self.entities:
            return
        from skopos_layers import skopos_node_spec

        spec = skopos_node_spec(mode="universe")
        ent = EcosystemEntity(
            spec["id"],
            spec["label"],
            "observability",
            spec["group"],
            icon=spec["icon"],
            description=spec["description"],
        )
        ent.position = spec["position"]
        ent.url = spec["url"]
        ent.metrics = dict(spec.get("metrics") or {})
        ent.status = spec.get("status", "offline")
        ent.color = "#00e5cc"
        self.entities[ent.id] = ent

    def _seed_oracle_family(self) -> None:
        """Seed the 17-oracle family + Platon's UMBRAL cave as always-present nodes.

        These render regardless of deployment (the family is the showcase). Live
        status/metrics are filled later by _poll_oracle_family and federation
        discovery; until an endpoint answers they stay 'declared' — no fake data.
        """
        from oracle_family import CAVE, ORACLE_FAMILY, oracle_node_id, ring_position, scene_url

        n = len(ORACLE_FAMILY)
        for i, o in enumerate(ORACLE_FAMILY):
            eid = oracle_node_id(o["slug"])
            ent = EcosystemEntity(eid, o["name"], "oracle-family", group="oracle", icon="oracle",
                                  description=f"{o['skill']} · caps: {', '.join(o['caps'])}")
            ent.position = ring_position(i, n)
            ent.color = o["accent"]
            ent.url = scene_url(o["slug"])
            ent.parent_id = "federation"
            ent.status = "idle"  # 'active' once a live endpoint answers; metrics.live carries the truth
            ent.metrics = {
                "capability_count": len(o["caps"]),
                "tests": o["tests"],
                "deployed": 1 if o.get("live_url") else 0,
                "live": 0,
            }
            self.entities[eid] = ent

        cave = EcosystemEntity(CAVE["id"], CAVE["name"], "oracle-cave", group="oracle",
                               icon="cave", description=CAVE["skill"])
        plat = self.entities.get(oracle_node_id(CAVE["parent_slug"]))
        if plat:
            cave.position = {"x": plat.position["x"] + 1.6,
                             "y": plat.position["y"] - 1.1,
                             "z": plat.position["z"] + 1.2}
        cave.color = CAVE["accent"]
        cave.url = CAVE["url"]
        cave.parent_id = oracle_node_id(CAVE["parent_slug"])
        cave.status = "idle"
        cave.metrics = {"live": 0}
        self.entities[CAVE["id"]] = cave
