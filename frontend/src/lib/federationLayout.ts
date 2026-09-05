import type { EcoNode } from '../App';

/**
 * How far out a node is, and what that makes it on the map.
 *
 * The federation is a cyclic graph — hubs peer with each other, and with us — so "draw the
 * peers, then their peers" has no natural end. Hop distance is what bounds it, and it is
 * also the only honest answer to "whose infrastructure is this":
 *
 *   hop 0  this hub and what it runs. Full detail, live status, our own poller.
 *   hop 1  a hub we federate with directly. A SUN: its own place in the ball of hubs,
 *          with aggregates (capabilities, peers, trust) and no components of its own.
 *   hop 2  reached only THROUGH somebody else. A PLANET in that hub's constellation —
 *          never a sun, never expanded further, never polled.
 *
 * The Monitor used to have no such rule. Clicking a hub dropped every neighbour it named
 * onto a fixed 3.4-unit ring as a full sun — orbit belts, corona, gravity well, its own
 * point light — including the eight that were already on the map under their own names.
 * Ten of those inside a 7-unit ball is one lit knot, which is what the live map showed.
 */

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

/** Hop of a node, defaulting to 0 — a payload without one is this deployment's own. */
export function hopOf(node: Partial<EcoNode> & { hop?: number }): number {
  const raw = Number(node.hop);
  return Number.isFinite(raw) ? Math.max(0, Math.trunc(raw)) : 0;
}

/** Nodes the 3D scene draws as a SUN — own sphere, orbit belts, corona, gravity well, light. */
export function isHubRole(
  node: Pick<EcoNode, 'id' | 'group' | 'icon'> & Partial<EcoNode> & { hop?: number },
): boolean {
  // A hub reached through another hub is a planet in THAT hub's system. Drawing it as a
  // sun is what turned one neighbourhood into a second galaxy on top of the first.
  if (hopOf(node) > 1) return false;
  return (
    node.id === 'hub'
    || node.role === 'hub'
    || node.group === 'peer_hub'
    || node.group === 'pending_hub'
    || node.id === 'factory'
    || node.id === 'competing_hub'
    || node.id === 'signal_hunt_hub'
    || (node.icon === 'hub' && node.id.includes('hub'))
  );
}

/** Only a hub has a neighbourhood, and only a first-hop one may be opened. */
export function canExpand(node: Partial<EcoNode> & { hop?: number }): boolean {
  return Boolean(node.url) && hopOf(node) <= 1 && isHubRole(node as EcoNode);
}

// ── A hub's constellation ────────────────────────────────────────────────────
// Mirrors `ecosystem_layout.peer_hub_child_position` exactly. Discovery already places a
// hub's own peers this way when it unpacks them server-side; a neighbourhood loaded in the
// browser is the same thing arriving later, and it has to land in the same shape or the
// same hub looks different depending on whether you clicked it.

export const CHILD_RADIUS = 2.2;
export const CHILD_SHELL_STEP = 1.6;
export const CHILDREN_PER_SHELL = 8;
export const CHILD_Y = 0.42;

/** Planet-scale clearance — `space_map.MIN_SEPARATION` on the backend. */
export const PLANET_MIN_GAP = 0.9;

function childSlot(parent: Vec3, index: number, count: number): Vec3 {
  const i = Math.max(0, Math.trunc(index));
  const n = Math.max(1, Math.trunc(count));
  const shell = Math.floor(i / CHILDREN_PER_SHELL);
  const inShell = i % CHILDREN_PER_SHELL;
  const remaining = n - shell * CHILDREN_PER_SHELL;
  const perShell = Math.max(1, Math.min(CHILDREN_PER_SHELL, remaining));
  const radius = CHILD_RADIUS + shell * CHILD_SHELL_STEP;
  const angle = (2 * Math.PI * inShell) / perShell + (Math.PI / perShell) * (shell % 2);
  const tier = CHILD_Y * (i % 2 === 0 ? 1 : -1);
  return {
    x: parent.x + radius * Math.cos(angle),
    y: parent.y + tier,
    z: parent.z + radius * Math.sin(angle),
  };
}

function distance(a: Vec3, b: Vec3): number {
  return Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
}

/** How much room a hub's constellation of `count` planets takes up. */
export function constellationRadius(count: number): number {
  const n = Math.max(0, Math.trunc(count));
  if (!n) return 0;
  const shells = 1 + Math.floor((n - 1) / CHILDREN_PER_SHELL);
  return CHILD_RADIUS + (shells - 1) * CHILD_SHELL_STEP;
}

/**
 * Slots for one hub's neighbourhood, in orbit around that hub.
 *
 * Grouped by construction — every slot belongs to its own hub's shells. `occupied` is
 * everything already on the map: a slot that lands on one of them is skipped for the next,
 * so a peer the hub shares with its neighbour does not get drawn inside another planet.
 */
export function constellationSlots(parent: Vec3, count: number, occupied: Vec3[] = []): Vec3[] {
  const wanted = Math.max(0, Math.trunc(count));
  if (!wanted) return [];
  for (let attempt = 0; attempt < 3; attempt += 1) {
    // Exactly as many slots as neighbours first — that is the even spread. Only a clash
    // with something already on the map buys spare slots, and with them another shell.
    const total = wanted * (1 + attempt);
    const chosen: Vec3[] = [];
    for (let i = 0; i < total && chosen.length < wanted; i += 1) {
      const point = childSlot(parent, i, total);
      if (occupied.some((taken) => distance(point, taken) < PLANET_MIN_GAP)) continue;
      if (chosen.some((taken) => distance(point, taken) < PLANET_MIN_GAP)) continue;
      chosen.push(point);
    }
    if (chosen.length === wanted) return chosen;
  }
  // Never lose a neighbour to a crowded shell; the backend's spacing pass is the floor.
  return Array.from({ length: wanted }, (_unused, i) => childSlot(parent, i, wanted));
}

/**
 * One spelling for one hub, so two peer lists agree about what is the same node.
 *
 * Deliberately the same rule as the backend's `hub_discovery._norm_url`: lowercase, no
 * trailing slash, no scheme. Two hubs that list the same peer as `http://x:9083/` and
 * `https://X:9083` were minting two objects for one address.
 */
export function normalizeHubUrl(url: string | null | undefined): string {
  const text = String(url ?? '').trim().replace(/\/+$/, '').toLowerCase();
  for (const prefix of ['https://', 'http://']) {
    if (text.startsWith(prefix)) return text.slice(prefix.length);
  }
  return text;
}

/** One row of `/api/federation/neighborhood` — a hub as its neighbour describes it. */
export interface NeighborEntry {
  url?: string;
  name?: string;
  trusted?: boolean;
  capabilities_count?: number;
  categories?: string[];
}

/**
 * One hub's neighbourhood, as hop-2 nodes ready to drop on the map.
 *
 * Two decisions, in this order, and the order is the point. First fold: a neighbour whose
 * address is already on the map is that node — our own satellites are in every peer's list,
 * and so is our own hub, so a straight `map()` over the payload minted a second, hub-styled
 * copy of ATLAS, MOMUS, LOGOS, the factory and ourselves. Then place: what survived becomes
 * planets in this hub's constellation, sized for however many there are.
 */
export function neighborhoodNodes(
  parent: EcoNode,
  neighbors: NeighborEntry[],
  onMap: EcoNode[],
): EcoNode[] {
  const taken = new Set(onMap.map((node) => normalizeHubUrl(node.url)).filter(Boolean));
  const fresh: NeighborEntry[] = [];
  for (const entry of neighbors) {
    const url = normalizeHubUrl(entry?.url);
    if (!url || taken.has(url)) continue;
    taken.add(url);
    fresh.push(entry);
  }
  const occupied = onMap.map((node) => node.position).filter(Boolean);
  const slots = constellationSlots(parent.position, fresh.length, occupied);
  return fresh.map((entry, index) => {
    const url = String(entry.url || '').replace(/\/+$/, '');
    return {
      id: `lazy:${normalizeHubUrl(url)}`,
      label: String(entry.name || url).slice(0, 80),
      // Same groups discovery gives a second hop it unpacked itself. Not `peer_hub`:
      // that is the group the scene draws as a sun.
      group: entry.trusted ? 'peer_hub_node' : 'pending_hub_node',
      icon: 'network',
      role: 'peer',
      hop: 2,
      parent_id: parent.id,
      description: entry.trusted
        ? 'Peer of this hub — reached through it, not by us.'
        : 'Observed by this hub — visible, approved by nobody.',
      metrics: { capabilities: Number(entry.capabilities_count || 0) },
      status: entry.trusted ? 'idle' : 'unknown',
      position: slots[index],
      url,
      categories: entry.categories,
    } as EcoNode;
  });
}

/**
 * The lazily-loaded nodes that are genuinely new to the map.
 *
 * Two filters, and the map needed both. A neighbour already on the server graph is the same
 * object under another name. And two EXPANDED hubs list each other's peers, so the same
 * address arrives twice from two different parents; the old filter compared lazy nodes
 * against the server graph only, which is how one oracle family ended up on screen three
 * times, each copy fighting for a slot.
 */
export function newLazyNodes(serverNodes: EcoNode[], lazyNodes: EcoNode[]): EcoNode[] {
  const takenIds = new Set(serverNodes.map((node) => node.id));
  const takenUrls = new Set(
    serverNodes.map((node) => normalizeHubUrl(node.url)).filter(Boolean),
  );
  const fresh: EcoNode[] = [];
  for (const node of lazyNodes) {
    const url = normalizeHubUrl(node.url);
    if (takenIds.has(node.id) || (url && takenUrls.has(url))) continue;
    takenIds.add(node.id);
    if (url) takenUrls.add(url);
    fresh.push(node);
  }
  return fresh;
}

// ── Render budget ────────────────────────────────────────────────────────────
// A thousand hubs is a stated goal, and the scene hangs a `pointLight` on every one of
// them. three.js recompiles its shaders per light count and pays for each light on every
// fragment, so this dies long before a hundred — and the labels (`<Text>`, one SDF mesh
// each) are not far behind. Detail is therefore a budget spent on what the camera is
// actually near, not a property of the node.

export const LIT_HUB_BUDGET = 12;

/**
 * How many labels may exist at once.
 *
 * Each one is a `<Html>` overlay — a real DOM node that drei repositions every frame. A
 * hundred of those is free and five thousand is the single most expensive thing on the
 * page, ahead of every mesh in the scene.
 */
export const LABEL_BUDGET = 60;

/**
 * Is this node the live federation itself, rather than the shelf drawn around it?
 *
 * Three separate budgets stand between "discovered" and "labelled" — real-object count,
 * lazy-reveal of a hub's children, and the label pool — and a node has to clear all three.
 * Fixing one of them moved the failure to the next: the map still could not name the hub it
 * was federated with. There are single digits of these nodes and they are the subject of the
 * map, so they are exempt from all three rather than competing for slots with a seeded SDK.
 */
export function isFederation(node: { group?: string }): boolean {
  const g = String(node.group || '');
  return g === 'peer_hub' || g === 'peer_hub_provider' || g === 'peer_hub_node';
}

/**
 * Label priority: what a node IS outranks where it happens to sit.
 *
 * Labels were handed out by distance alone, and the seeded ecosystem sits near the centre —
 * so the sixty slots filled with Dart SDK, Solana, CLI Tools, Fermat, Landauer… while the
 * live federation went unlabelled. On the modelmarket map that meant "Independent AI Hub"
 * and "KOVA" fell off the end of the budget: present in the scene, drawn, and anonymous.
 *
 * A peer hub discovered live, and the providers of its own star system, are the subject of
 * this map. A seeded satellite is context. Lower number wins; distance still decides within
 * a rank, so approaching something still brings it forward.
 */
export function labelRank(node: { group?: string; hop?: number }): number {
  const g = String(node.group || '');
  if (g === 'peer_hub') return 0;
  if (g === 'peer_hub_provider' || g === 'peer_hub_node') return 1;
  if (hopOf(node) >= 1) return 2;
  return 3;
}

/** The `budget` most label-worthy items: by rank first, then by distance within a rank. */
export function labelTargets<T extends { position: Vec3; group?: string; hop?: number }>(
  nodes: T[],
  camera: Vec3,
  budget: number = LABEL_BUDGET,
): T[] {
  if (nodes.length <= budget) return nodes;
  const fed = nodes.filter(isFederation);
  const rest = nodes.filter((n) => !isFederation(n));
  const room = Math.max(0, budget - fed.length);
  return [
    ...fed,
    ...[...rest]
      .sort((a, b) => distance(a.position, camera) - distance(b.position, camera))
      .slice(0, room),
  ];
}

/** The `budget` items nearest the camera — the only ones worth their expensive parts. */
export function nearestHubs<T extends { position: Vec3 }>(
  hubs: T[],
  camera: Vec3,
  budget: number = LIT_HUB_BUDGET,
): T[] {
  if (hubs.length <= budget) return hubs;
  return [...hubs]
    .sort((a, b) => distance(a.position, camera) - distance(b.position, camera))
    .slice(0, Math.max(0, budget));
}

/**
 * How many nodes are built as real objects — a `<group>` with meshes, materials and a frame
 * callback each. Everything else still exists on the map, as a point in one instanced cloud.
 *
 * This is the number that decides whether the map survives its own success. Five thousand
 * real nodes measured 2 fps and a 65-second load; the cost is per-object and linear, so a
 * hundred thousand is not a slower version of the same thing, it is a page that never
 * finishes. One point cloud is one draw call whatever is in it.
 */
export const REAL_NODE_BUDGET = 150;

/**
 * Which nodes the scene should draw at all.
 *
 * A federation of a thousand hubs carries every hub's constellation with it, and drawing
 * all of them at once is both unreadable and unrenderable. A constellation belongs to its
 * hub, so it appears when that hub does: when it is selected, or when the camera has come
 * close enough for it to be one of the near ones. That is the lazy detail the map promised
 * — approach a hub and its system resolves — expressed as what is on screen.
 */
export function visibleNodes<T extends { id: string; hop?: number; parent_id?: string; group?: string }>(
  nodes: T[],
  openHubIds: ReadonlySet<string>,
): T[] {
  let hidden = false;
  const out = nodes.filter((node) => {
    if (hopOf(node) <= 1) return true;
    // A peer hub's own declared providers travel with it: hiding them until the hub is
    // clicked meant a federated node appeared as a lone dot with no system, which is the
    // one thing this map exists to show.
    if (isFederation(node)) return true;
    const keep = Boolean(node.parent_id && openHubIds.has(node.parent_id));
    if (!keep) hidden = true;
    return keep;
  });
  return hidden ? out : nodes;
}

/**
 * How far the camera must be able to pull back to see everything.
 *
 * A fixed 52 was fine for one ecosystem and is a wall for a federation: a hundred hubs
 * reach radius 54, a thousand reach 126, and neither can be framed by a camera that stops
 * at 52. The limit follows the map instead.
 */
export function cameraRange(nodes: { position?: Vec3 | null }[], floor = 52): number {
  let far = 0;
  for (const node of nodes) {
    const p = node.position;
    if (!p) continue;
    const r = Math.hypot(p.x, p.y, p.z);
    if (Number.isFinite(r) && r > far) far = r;
  }
  return Math.max(floor, far * 1.6);
}
