"""The universe's topology links between entities."""

from __future__ import annotations


class TopologyLinksMixin:
    """Topology links between the universe's entities."""

    def get_topology_links(self) -> list[dict]:
        from lottery_layers import lottery_financial_links
        from argus_layers import argus_topology_links
        from oracle_family import CAVE, ORACLE_FAMILY, oracle_node_id

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
        oracle_draw_ids = [
            oracle_node_id(o["slug"])
            for o in ORACLE_FAMILY
            if o["slug"] in ("platon", "chronos", "lumen")
            and oracle_node_id(o["slug"]) in self.entities
        ]
        if not oracle_draw_ids:
            oracle_draw_ids = ["federation"] if "federation" in self.entities else []
        links.extend(lottery_financial_links(oracle_ids=oracle_draw_ids))
        if "argus" in self.entities:
            oracle_target = oracle_node_id("lumen")
            if oracle_target not in self.entities:
                oracle_target = "federation"
            links.extend(argus_topology_links(oracle_target=oracle_target))
        if "factory_agents" in self.entities:
            from factory_agents import factory_agents_topology_links

            links.extend(
                e
                for e in factory_agents_topology_links()
                if e["source"] in self.entities and e["target"] in self.entities
            )
        if "dioscuri" in self.entities:
            from dioscuri_layers import dioscuri_topology_links

            links.extend(dioscuri_topology_links())
        if "helios" in self.entities:
            from helios_layers import helios_topology_links

            links.extend(helios_topology_links())
        if "metis" in self.entities:
            from metis_layers import metis_topology_links

            links.extend(metis_topology_links())
        if "skopos" in self.entities:
            from skopos_layers import skopos_topology_links

            links.extend(skopos_topology_links())
        if "gaia" in self.entities:
            from gaia_layers import gaia_topology_links

            links.extend(gaia_topology_links())
        if "atlas" in self.entities:
            from atlas_layers import atlas_topology_links

            links.extend(atlas_topology_links())
        if "hephaestus" in self.entities:
            from hephaestus_layers import hephaestus_topology_links

            links.extend(hephaestus_topology_links())
        if "histor" in self.entities:
            from histor_layers import histor_topology_links

            for link in histor_topology_links():
                if link["source"] in self.entities and link["target"] in self.entities:
                    links.append(link)
        if "warden" in self.entities:
            from warden_layers import warden_topology_links

            for link in warden_topology_links():
                if link["source"] in self.entities and link["target"] in self.entities:
                    links.append(dict(link))
        if "momus" in self.entities or "treasury" in self.entities:
            from momus_layers import momus_topology_links

            links.extend(momus_topology_links())
        if "logos" in self.entities:
            from logos_layers import logos_topology_links

            links.extend(logos_topology_links())
        if "bridges" in self.entities:
            # Without this the node is seeded but floats unconnected in UNI mode, and the one
            # claim it exists to make — that this is a billed channel INTO the hub, the same
            # category as the mesh — is exactly the thing that goes missing. Seeding the entity
            # and drawing its edge are two separate wirings; the first one alone looks done.
            from bridges_layers import bridges_topology_links

            links.extend(bridges_topology_links())
        if "themis" in self.entities:
            from themis_layers import themis_topology_links

            links.extend(themis_topology_links())
        if "basanos" in self.entities:
            from basanos_layers import basanos_topology_links
            from dolos_layers import dolos_topology_links

            links.extend(basanos_topology_links())
            links.extend(dolos_topology_links())
        if "hestia" in self.entities:
            from hestia_layers import hestia_topology_links

            links.extend(hestia_topology_links())
        if "settlement" in self.entities:
            from settlement_layers import settlement_topology_links

            links.extend(settlement_topology_links())
        if any(eid in self.entities for eid in ("competing_hub", "signal_hunt_hub", "signal_hunt", "use_cases")):
            from competing_lab_layers import competing_lab_topology_links

            links.extend(competing_lab_topology_links())
        for prod in self.products:
            links.append({"source": "factory", "target": prod["id"], "label": "created"})
        for ag in self.agents:
            links.append({"source": "mesh", "target": ag["id"], "label": "registered"})
        for link in getattr(self, "_discovery_links", []):
            # Only between nodes that made it onto the map: a link to a peer that failed its
            # own build is an edge to nothing, and the frontend resolves endpoints by id.
            if link["source"] in self.entities and link["target"] in self.entities:
                if link.get("kind") == "shared" or link.get("label") == "its peer":
                    links.append(dict(link))
        for did in self._discovered_ids:
            ent = self.entities.get(did)
            parent = str(getattr(ent, "parent_id", "") or "federation")
            # Seeding an entity and drawing its edge are two separate wirings, and the first
            # one alone looks done: a hub's own peers were entities with a parent_id nothing
            # read, so they floated unconnected. Edge to the parent when it is on the map,
            # otherwise to our federation node.
            if parent != "federation" and parent in self.entities:
                links.append({"source": parent, "target": did, "label": "its peer"})
            else:
                links.append({"source": "federation", "target": did, "label": "Federation peer"})
        # Oracle family — always linked from Federation; the cave hangs off Platon.

        for o in ORACLE_FAMILY:
            oid = oracle_node_id(o["slug"])
            if oid in self.entities:
                links.append({"source": "federation", "target": oid, "label": "oracle family"})
        plat_id = oracle_node_id(CAVE["parent_slug"])
        if plat_id in self.entities and CAVE["id"] in self.entities:
            links.append({"source": plat_id, "target": CAVE["id"], "label": "live product"})
        return links
