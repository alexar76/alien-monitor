"""What the universe learns from outside: the factory catalogue, product materialization, the
oracle family's polls and discovered nodes.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from universe_entities import EcosystemEntity, _MAX_PRODUCT_ENTITIES, _norm_peer_url


class DiscoveryMixin:
    """Factory catalogue, materialization, oracle polls and discovery."""

    def sync_factory_catalog(
        self,
        app_url: str | None = None,
        *,
        timeout: float | None = None,
    ) -> int:
        """Import shipped products from Factory API as product planets (idempotent)."""
        from factory_products import resolve_factory_catalog

        url = app_url or os.environ.get("AICOM_API_URL", "http://127.0.0.1:9081")
        catalog, authoritative = resolve_factory_catalog(url, timeout=timeout)
        if catalog is None:
            print(f"[Universe] Factory catalog sync skipped — API unreachable ({url})")
            return 0

        catalog_ids = {str(p.get("id") or "") for p in catalog if p.get("id")}

        # Drop product nodes removed from Factory only on authoritative catalog reads.
        if authoritative:
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

    def _family_id_for_node(self, n: dict) -> str | None:
        """Map a discovered federation peer onto a node the map already draws.

        Family oracles and first-party satellites (MOMUS, GAIA, …) must enrich
        the canonical entity — a second violet oracle for MOMUS is a duplicate.
        """
        from canonical_peers import canonical_node_id_for_peer

        return canonical_node_id_for_peer(n)

    def _poll_oracle_family(self) -> None:
        """Throttled liveness poll of deployed oracles + the cave. A node flips to
        'live' (with a few real metrics) only when /api/health answers with
        status=ok; otherwise it reverts to idle. Polls the remote oracle host
        (oracles.modelmarket.dev by default), not loopback."""
        import urllib.request

        from oracle_family import CAVE, ORACLE_FAMILY, oracle_node_id

        targets = [(oracle_node_id(o["slug"]), o.get("live_url")) for o in ORACLE_FAMILY]
        targets.append((CAVE["id"], CAVE.get("live_url")))
        for eid, base in targets:
            ent = self.entities.get(eid)
            if ent is None or not base:
                continue
            health: dict | None = None
            try:
                req = urllib.request.Request(
                    f"{base.rstrip('/')}/api/health",
                    headers={"User-Agent": "alien-monitor", "Accept": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=3.0) as resp:  # noqa: S310
                    if getattr(resp, "status", 200) == 200:
                        body = json.loads(resp.read(65536).decode("utf-8", "replace"))
                        if isinstance(body, dict) and body.get("status") == "ok":
                            health = body
            except Exception:
                health = None
            if isinstance(health, dict):
                ent.status = "active"
                live: dict[str, int | float] = {"live": 1}
                for k in ("tick", "viewers", "capabilities", "kappa", "order_parameter"):
                    v = health.get(k)
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        live[k] = v
                caps = health.get("capabilities")
                if isinstance(caps, int) and "capabilities" not in live:
                    live["capabilities"] = caps
                ent.metrics = {**ent.metrics, **live}
            else:
                ent.metrics["live"] = 0

    def _apply_discovery(self, hub_url: str) -> None:
        """Hub-driven federation discovery in UNI mode — render peers (e.g. Platon)
        as oracle entities hydrated with live /api/health metrics. Defensive: any
        failure leaves the universe untouched."""
        if not hub_url:
            return
        try:
            from hub_discovery import discover_cached_sync
            # UNI is a local sim; allow loopback/private peers (spawned hubs etc.).
            disc = discover_cached_sync(hub_url, allow_private=True)
        except Exception:
            return

        self._discovery_events = list(disc.get("events") or [])
        # Edges discovery computed itself — hub-to-hub, and "we both know this node". They
        # connect two entities that already exist, so nothing else in this file would ever
        # produce them: `get_topology_links` builds from the entity table, and an edge
        # between two known nodes is not derivable from either one alone. Dropping them left
        # the federation looking like a star when it is a mesh.
        self._discovery_links = [
            dict(link) for link in (disc.get("links") or [])
            if isinstance(link, dict) and link.get("source") and link.get("target")
        ]
        # Every URL the map ALREADY draws, mapped to the node that draws it. This is the
        # rule; the host/name tables in `canonical_peers` are only the fallback for peers
        # whose URL is spelled differently from the node's own.
        #
        # It has to be derived from the graph rather than listed, because a list needs a
        # human edit every time a satellite gets a seed — and the requirement is the other
        # way round: adding a seed must never add a planet. ARGUS, DIOSCURI, HELIOS and
        # WARDEN do not publish a well-known today, so they cannot duplicate yet; the day
        # one of them does, nothing should have to be remembered.
        drawn_by_url: dict[str, str] = {}
        for eid, existing in self.entities.items():
            if getattr(existing, "type", "") == "federation":
                continue  # a discovered node is not something to fold onto
            url = _norm_peer_url(getattr(existing, "url", "") or "")
            if url:
                drawn_by_url.setdefault(url, eid)

        folded: dict[str, str] = {}
        current: set[str] = set()
        for n in disc.get("nodes", []):
            nid = n.get("id")
            if not nid:
                continue
            # UNI is the sealed universe. An unapproved stranger that announced itself to the
            # live hub has no business appearing in the simulation — and without this filter it
            # arrived styled exactly like a trusted oracle peer, because _apply_discovery gives
            # every unmatched node group="oracle". Strangers belong on the LIVE map only.
            if n.get("group") == "pending_hub" or n.get("status") == "pending":
                continue
            # If this peer is something the map already draws, enrich that node instead of
            # minting a duplicate. URL first — it needs no table and covers every satellite,
            # present and future — then the spelling fallback.
            # Host/name tables first so hunt HTTPS cannot be stolen by Competing
            # Lab Hub when an old env still pointed both suns at the same URL.
            # URL fallback still covers a satellite the tables have never listed.
            fam_id = self._family_id_for_node(n) \
                or drawn_by_url.get(_norm_peer_url(str(n.get("url") or "")))
            if fam_id:
                folded[nid] = fam_id
                if fam_id in self.entities:
                    fam = self.entities[fam_id]
                    fam.status = n.get("status") or "active"
                    fam.metrics = {**fam.metrics, **(n.get("metrics") or {}), "live": 1}
                # Legacy hub peers (e.g. "Platon Shadow Oracle") map onto the
                # family ring — never materialize them as extra federation nodes.
                continue
            ent = self.entities.get(nid)
            if ent is not None and getattr(ent, "type", "") != "federation":
                # id collides with a non-discovery entity (core/product/agent) —
                # never clobber a real node with peer-supplied data.
                continue
            # Honour the node's OWN group. This used to hardcode oracle/oracle/#a64dff for
            # every discovered node, so a peer that is itself a HUB — with peers of its own
            # hanging off it — arrived on the map dressed as an oracle, indistinguishable
            # from a capability service. Emitting a new group upstream was invisible until
            # this line stopped overwriting it.
            group = str(n.get("group") or "oracle")
            icon = str(n.get("icon") or ("hub" if group == "peer_hub" else ("network" if group.startswith("peer_hub") else "oracle")))
            if ent is None:
                ent = EcosystemEntity(
                    nid, str(n.get("label") or nid), "federation", group=group,
                    description=str(n.get("description") or ""), icon=icon,
                )
                self.entities[nid] = ent
            else:
                ent.group = group
                ent.icon = icon
            if n.get("role") or group == "peer_hub":
                ent.role = str(n.get("role") or "hub")
            ent.metrics = {k: v for k, v in (n.get("metrics") or {}).items()}
            ent.status = n.get("status", "active")
            ent.url = n.get("url")
            # The default used to be oracle violet, so every discovered service that was
            # not a hub arrived purple — three unrelated providers under one hub identical,
            # and a second operator's satellites the same purple again. Colour now says what
            # a thing does, from the same table the LIVE path stamps. See node_palette.
            from node_palette import color_for

            ent.color = n.get("color") or color_for(
                group, n.get("categories") or (), role=str(n.get("role") or ""), node_id=nid
            )
            # A hub's own peers hang off that hub, not off our federation node — that is the
            # whole shape the second hop exists to show.
            parent = str(n.get("parent_id") or "federation")
            parent = folded.get(parent, parent)
            fam_parent = self._family_id_for_node({"id": parent, "label": parent})
            if fam_parent and fam_parent in self.entities:
                parent = fam_parent
            ent.parent_id = parent
            if n.get("position"):
                ent.position = n["position"]
            current.add(nid)

        if folded:
            for link in self._discovery_links:
                link["source"] = folded.get(str(link.get("source")), link.get("source"))
                link["target"] = folded.get(str(link.get("target")), link.get("target"))
            self._discovery_links = [
                link for link in self._discovery_links
                if link.get("source") != link.get("target")
            ]

        # Moons of a folded sun were placed around the discovery clone. Pull them
        # onto the seeded planet so the operator can actually see that ecosystem.
        from collections import defaultdict

        from ecosystem_layout import peer_hub_child_position

        moons: dict[str, list] = defaultdict(list)
        for eid in current:
            ent = self.entities.get(eid)
            if ent is None or getattr(ent, "group", "") != "peer_hub_node":
                continue
            pid = str(getattr(ent, "parent_id", "") or "")
            if pid in folded:
                pid = folded[pid]
                ent.parent_id = pid
            moons[pid].append(ent)
        for pid, kids in moons.items():
            parent = self.entities.get(pid)
            if parent is None or not getattr(parent, "position", None):
                continue
            for index, child in enumerate(kids):
                child.position = peer_hub_child_position(parent.position, index, len(kids))

        # Prune entities that were discovered before but are no longer peers.
        for stale in self._discovered_ids - current:
            ent = self.entities.get(stale)
            if ent is not None and getattr(ent, "type", "") == "federation":
                self.entities.pop(stale, None)
        self._discovered_ids = current

    def _ensure_topology_seeded(self) -> None:
        """Graph skeleton must exist even when local Anvil bootstrap fails."""
        if not self.entities or "hub" not in self.entities:
            self.seed_entities()
            return
        if not any(eid.startswith("oracle-") for eid in self.entities):
            self._seed_oracle_family()
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
