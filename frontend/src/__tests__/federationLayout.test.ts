import { describe, expect, it } from 'vitest';
import type { EcoNode } from '../App';
import {
  CHILD_RADIUS,
  LIT_HUB_BUDGET,
  PLANET_MIN_GAP,
  cameraRange,
  canExpand,
  constellationRadius,
  constellationSlots,
  hopOf,
  isHubRole,
  nearestHubs,
  neighborhoodNodes,
  newLazyNodes,
  normalizeHubUrl,
  visibleNodes,
  type Vec3,
} from '../lib/federationLayout';

const dist = (a: Vec3, b: Vec3) => Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);

function node(partial: Pick<EcoNode, 'id' | 'label' | 'group'> & Partial<EcoNode>): EcoNode {
  return {
    icon: 'network',
    description: '',
    metrics: {},
    status: 'idle',
    position: { x: 0, y: 0, z: 0 },
    ...partial,
  };
}

describe('hops decide what a node is', () => {
  it('treats a payload without a hop as this deployment’s own', () => {
    expect(hopOf({})).toBe(0);
    expect(hopOf({ hop: 2 })).toBe(2);
  });

  it('draws our hub and the hubs we federate with as suns', () => {
    expect(isHubRole(node({ id: 'hub', label: '', group: 'core', hop: 0 }))).toBe(true);
    expect(isHubRole(node({ id: 'p', label: '', group: 'peer_hub', hop: 1 }))).toBe(true);
    expect(isHubRole(node({ id: 'q', label: '', group: 'pending_hub', hop: 1 }))).toBe(true);
  });

  it('never draws a hub reached through somebody else as a sun', () => {
    // The whole defect in one assertion: a second-hop hub used to arrive as `peer_hub`,
    // which the scene lights, belts and haloes exactly like an independent galaxy.
    expect(isHubRole(node({ id: 'x', label: '', group: 'peer_hub', hop: 2 }))).toBe(false);
    expect(isHubRole(node({ id: 'y', label: '', group: 'peer_hub_node', hop: 2 }))).toBe(false);
  });

  it('leaves a satellite a planet — it has no neighborhood to expand', () => {
    expect(isHubRole(node({ id: 'atlas', label: '', group: 'physical' }))).toBe(false);
  });

  it('opens only a first-hop hub, so the crawl cannot walk a cycle', () => {
    const ours = node({ id: 'hub', label: '', group: 'core', url: 'https://us.example' });
    const peer = node({ id: 'p', label: '', group: 'peer_hub', hop: 1, url: 'https://p.example' });
    const theirs = node({ id: 'q', label: '', group: 'peer_hub_node', hop: 2, url: 'https://q.example' });
    const satellite = node({ id: 'atlas', label: '', group: 'physical', url: 'https://a.example' });
    expect(canExpand(ours)).toBe(true);
    expect(canExpand(peer)).toBe(true);
    expect(canExpand(theirs)).toBe(false);
    expect(canExpand(satellite)).toBe(false);
    expect(canExpand(node({ id: 'p2', label: '', group: 'peer_hub', hop: 1 }))).toBe(false);
  });
});

describe('a hub keeps its neighborhood', () => {
  it('places every neighbour in its own hub’s orbit', () => {
    const parent = { x: 30, y: 12, z: -20 };
    for (const count of [1, 3, 8, 9, 20]) {
      const slots = constellationSlots(parent, count);
      expect(slots).toHaveLength(count);
      const limit = constellationRadius(count) + 0.5;
      for (const slot of slots) {
        expect(dist(parent, slot)).toBeGreaterThanOrEqual(CHILD_RADIUS - 0.01);
        expect(dist(parent, slot)).toBeLessThanOrEqual(limit);
      }
    }
  });

  it('keeps siblings off each other at any size', () => {
    const parent = { x: 0, y: 0, z: 0 };
    for (const count of [2, 5, 8, 17, 40]) {
      const slots = constellationSlots(parent, count);
      for (let i = 0; i < slots.length; i += 1) {
        for (let j = i + 1; j < slots.length; j += 1) {
          expect(dist(slots[i], slots[j])).toBeGreaterThanOrEqual(PLANET_MIN_GAP);
        }
      }
    }
  });

  it('steps aside from anything already on the map', () => {
    const parent = { x: 0, y: 0, z: 0 };
    const occupied = constellationSlots({ x: 3, y: 0, z: 0 }, 6);
    const slots = constellationSlots(parent, 6, occupied);
    expect(slots).toHaveLength(6);
    for (const slot of slots) {
      for (const taken of occupied) {
        expect(dist(slot, taken)).toBeGreaterThanOrEqual(PLANET_MIN_GAP);
      }
    }
  });

  it('stays compact as the neighbourhood grows — it is a system, not a galaxy', () => {
    // Twelve second-hop hubs must not claim the room twelve SUNS would (18 units apart,
    // a ball 36 across). They are planets.
    expect(constellationRadius(12)).toBeLessThan(5);
    expect(constellationRadius(40)).toBeLessThan(11);
  });

  it('places nothing for an empty neighbourhood', () => {
    expect(constellationSlots({ x: 1, y: 2, z: 3 }, 0)).toEqual([]);
  });
});

describe('normalizeHubUrl', () => {
  it('reads one hub address the same way the backend does', () => {
    // hub_discovery._norm_url: lowercase, no trailing slash, no scheme.
    expect(normalizeHubUrl('http://108.165.32.182:9083/')).toBe('108.165.32.182:9083');
    expect(normalizeHubUrl('https://108.165.32.182:9083')).toBe('108.165.32.182:9083');
    expect(normalizeHubUrl('https://Oracles.ModelMarket.dev/family/')).toBe(
      'oracles.modelmarket.dev/family',
    );
    expect(normalizeHubUrl(undefined)).toBe('');
  });
});

describe('newLazyNodes', () => {
  it('folds a neighbour the server graph already carries', () => {
    const server = [node({ id: 'atlas', label: 'ATLAS', group: 'physical', url: 'https://atlas.example/' })];
    const lazy = [node({ id: 'lazy:atlas.example', label: 'ATLAS', group: 'peer_hub_node', url: 'http://atlas.example' })];
    expect(newLazyNodes(server, lazy)).toEqual([]);
  });

  it('folds the same hub arriving from two different parents', () => {
    const server = [node({ id: 'hub', label: 'Us', group: 'core' })];
    const fromA = node({
      id: 'lazy:oracles.modelmarket.dev',
      label: 'AIMarket Oracle Family',
      group: 'peer_hub_node',
      url: 'https://oracles.modelmarket.dev',
    });
    const fromB = node({ ...fromA, url: 'https://oracles.modelmarket.dev/' });
    expect(newLazyNodes(server, [fromA, fromB])).toHaveLength(1);
  });

  it('keeps a genuinely new hub', () => {
    const server = [node({ id: 'hub', label: 'Us', group: 'core', url: 'https://us.example' })];
    const lazy = [node({ id: 'lazy:new.example', label: 'New', group: 'peer_hub_node', url: 'https://new.example' })];
    expect(newLazyNodes(server, lazy).map((n) => n.id)).toEqual(['lazy:new.example']);
  });
});

/**
 * The map that produced the complaint, from the live payloads on 2026-09-02:
 * independentai.network/monitor, LIVE mode. Two federated hubs whose peer lists are eleven
 * twelfths the same list, and most of that list already on the map under its own names.
 */
const LIVE_NEIGHBORS = [
  { url: 'http://108.165.32.182:9083', name: 'Competing Lab Hub', trusted: true },
  { url: 'https://atlas.modelmarket.dev', name: 'ATLAS', trusted: true },
  { url: 'https://basanos.modelmarket.dev', name: 'BASANOS', trusted: true },
  { url: 'https://independentai.network/hub', name: 'Independent AI Hub', trusted: false },
  { url: 'https://iot.modelmarket.dev', name: 'GAIA', trusted: true },
  { url: 'https://logos.modelmarket.dev', name: 'LOGOS', trusted: true },
  { url: 'https://magic-ai-factory.com', name: 'Magic AI-Factory AI Market', trusted: true },
  { url: 'https://modelmarket.dev', name: 'modelmarket.dev', trusted: true },
  { url: 'https://momus.modelmarket.dev', name: 'MOMUS', trusted: true },
  { url: 'https://oracles.modelmarket.dev/family', name: 'AIMarket Oracle Family', trusted: true },
  { url: 'https://skopos.modelmarket.dev', name: 'SKOPOS', trusted: true },
  { url: 'https://themis.modelmarket.dev', name: 'THEMIS', trusted: true },
];

const LIVE_MAP: EcoNode[] = [
  node({ id: 'hub', label: 'Independent AI Hub', group: 'core', hop: 0, url: 'https://independentai.network/hub' }),
  node({ id: 'factory', label: 'AI-Factory', group: 'core', hop: 0, url: 'https://magic-ai-factory.com', position: { x: 4, y: 2, z: -2 } }),
  node({ id: 'atlas', label: 'ATLAS', group: 'physical', hop: 0, url: 'https://atlas.modelmarket.dev', position: { x: -4.5, y: 9, z: -8 } }),
  node({ id: 'gaia', label: 'GAIA', group: 'physical', hop: 0, url: 'https://iot.modelmarket.dev', position: { x: -6.5, y: 8.5, z: -6.5 } }),
  node({ id: 'momus', label: 'MOMUS', group: 'security', hop: 0, url: 'https://momus.modelmarket.dev', position: { x: -12.5, y: 3, z: -3 } }),
  node({ id: 'basanos', label: 'BASANOS', group: 'security', hop: 0, url: 'https://basanos.modelmarket.dev', position: { x: 8.5, y: -6, z: 2 } }),
  node({ id: 'logos', label: 'LOGOS', group: 'cognition', hop: 0, url: 'https://logos.modelmarket.dev', position: { x: -14.5, y: -2, z: 5.5 } }),
  node({ id: 'skopos', label: 'SKOPOS', group: 'observability', hop: 0, url: 'https://skopos.modelmarket.dev', position: { x: -11.5, y: -3.5, z: 1.5 } }),
  node({
    id: 'signal_hunt_hub',
    label: 'Signal Hunt Hub',
    group: 'peer_hub',
    hop: 1,
    url: 'https://hunt.modelmarket.dev',
    position: { x: 33, y: 13.5, z: -22.5 },
  }),
];

describe('the crowded live map', () => {
  it('draws a neighbour the map already has as itself, not as a second object', () => {
    const parent = LIVE_MAP.find((n) => n.id === 'signal_hunt_hub')!;
    const added = neighborhoodNodes(parent, LIVE_NEIGHBORS, LIVE_MAP);
    expect(added.map((n) => n.url)).toEqual([
      'http://108.165.32.182:9083',
      'https://modelmarket.dev',
      'https://oracles.modelmarket.dev/family',
      'https://themis.modelmarket.dev',
    ]);
  });

  it('makes them planets of the hub that named them, not new galaxies', () => {
    const parent = LIVE_MAP.find((n) => n.id === 'signal_hunt_hub')!;
    const added = neighborhoodNodes(parent, LIVE_NEIGHBORS, LIVE_MAP);
    for (const child of added) {
      expect(child.hop).toBe(2);
      expect(child.parent_id).toBe('signal_hunt_hub');
      expect(isHubRole(child)).toBe(false);
      expect(dist(child.position, parent.position)).toBeLessThan(5);
    }
  });

  it('never draws the same hub twice when two hubs peer with each other', () => {
    const first = LIVE_MAP.find((n) => n.id === 'signal_hunt_hub')!;
    const fromFirst = neighborhoodNodes(first, LIVE_NEIGHBORS, LIVE_MAP);
    const afterFirst = [...LIVE_MAP, ...fromFirst];
    const second = fromFirst.find((n) => n.url === 'http://108.165.32.182:9083')!;
    const secondList = [
      ...LIVE_NEIGHBORS.filter((e) => e.url !== 'http://108.165.32.182:9083'),
      { url: 'https://hunt.modelmarket.dev', name: 'Signal Hunt Hub', trusted: true },
    ];
    const fromSecond = neighborhoodNodes(second, secondList, afterFirst);
    expect(fromSecond).toEqual([]);
    const urls = [...fromFirst, ...fromSecond].map((n) => normalizeHubUrl(n.url));
    expect(new Set(urls).size).toBe(urls.length);
  });

  it('adds no new suns at all — a second hop is somebody else’s system', () => {
    const parent = LIVE_MAP.find((n) => n.id === 'signal_hunt_hub')!;
    const added = neighborhoodNodes(parent, LIVE_NEIGHBORS, LIVE_MAP);
    const suns = [...LIVE_MAP, ...added].filter(isHubRole);
    expect(suns.map((n) => n.id).sort()).toEqual(['factory', 'hub', 'signal_hunt_hub']);
  });
});

describe('render budget', () => {
  it('lights only the hubs the camera is near', () => {
    const hubs = Array.from({ length: 40 }, (_u, i) => ({
      id: `h${i}`,
      position: { x: i * 5, y: 0, z: 0 },
    }));
    const lit = nearestHubs(hubs, { x: 0, y: 0, z: 0 });
    expect(lit).toHaveLength(LIT_HUB_BUDGET);
    expect(lit.map((h) => h.id)).toEqual(
      Array.from({ length: LIT_HUB_BUDGET }, (_u, i) => `h${i}`),
    );
  });

  it('leaves a small federation entirely lit', () => {
    const hubs = [{ id: 'a', position: { x: 1, y: 0, z: 0 } }];
    expect(nearestHubs(hubs, { x: 0, y: 0, z: 0 })).toBe(hubs);
  });

  it('lets the camera pull back far enough to see the whole ball', () => {
    // A hundred hubs reach radius 54, a thousand reach 126. A fixed 52 could frame neither.
    expect(cameraRange([])).toBe(52);
    expect(cameraRange([{ position: { x: 0, y: 0, z: 10 } }])).toBe(52);
    expect(cameraRange([{ position: { x: 126, y: 0, z: 0 } }])).toBeGreaterThan(126);
  });
});

describe('constellations resolve as you approach', () => {
  const map: EcoNode[] = [
    node({ id: 'hub', label: 'Us', group: 'core', hop: 0 }),
    node({ id: 'near', label: 'Near hub', group: 'peer_hub', hop: 1 }),
    node({ id: 'far', label: 'Far hub', group: 'peer_hub', hop: 1 }),
    node({ id: 'near-a', label: 'a', group: 'peer_hub_node', hop: 2, parent_id: 'near' }),
    node({ id: 'far-a', label: 'b', group: 'peer_hub_node', hop: 2, parent_id: 'far' }),
    node({ id: 'orphan', label: 'c', group: 'peer_hub_node', hop: 2 }),
  ];

  it('draws only the constellation of a hub that is open', () => {
    const drawn = visibleNodes(map, new Set(['near'])).map((n) => n.id);
    expect(drawn).toEqual(['hub', 'near', 'far', 'near-a']);
  });

  it('never hides a hub, only what hangs off one', () => {
    const drawn = visibleNodes(map, new Set()).map((n) => n.id);
    expect(drawn).toEqual(['hub', 'near', 'far']);
  });

  it('returns the same array when nothing is hidden — no needless re-render', () => {
    const hubsOnly = map.filter((n) => (n.hop ?? 0) <= 1);
    expect(visibleNodes(hubsOnly, new Set())).toBe(hubsOnly);
  });
});
