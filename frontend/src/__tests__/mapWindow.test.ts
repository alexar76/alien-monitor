import { describe, expect, it, vi } from 'vitest';
import type { EcoLink, EcoNode } from '../App';
import {
  EMPTY_CHART,
  KIND_FAR,
  KIND_LOCAL,
  KIND_PEER_HUB,
  KIND_PENDING,
  chartFromNodes,
  chartFromRows,
  fetchChart,
  kindOfNode,
  mergeWindow,
  windowIsStale,
  type DigestRow,
} from '../lib/mapWindow';

function node(partial: Pick<EcoNode, 'id'> & Partial<EcoNode>): EcoNode {
  return {
    label: partial.id,
    group: 'core',
    icon: '',
    description: '',
    metrics: {},
    status: 'idle',
    position: { x: 0, y: 0, z: 0 },
    ...partial,
  };
}

const link = (source: string, target: string): EcoLink => ({ source, target, label: '' });

describe('the star chart never becomes objects', () => {
  it('decodes rows straight into typed arrays', () => {
    const rows: DigestRow[] = [
      ['a', 1, 2, 3, KIND_LOCAL],
      ['b', -4, 5, 6, KIND_PENDING],
    ];
    const chart = chartFromRows(rows, 'e1', 2);
    expect(chart.ids).toEqual(['a', 'b']);
    expect(chart.positions).toBeInstanceOf(Float32Array);
    expect(Array.from(chart.positions)).toEqual([1, 2, 3, -4, 5, 6]);
    expect(chart.colors).toBeInstanceOf(Float32Array);
    expect(chart.colors).toHaveLength(6);
    // Two kinds must not paint the same colour, or the far field says nothing.
    expect(Array.from(chart.colors.slice(0, 3))).not.toEqual(Array.from(chart.colors.slice(3)));
  });

  it('holds a hundred thousand stars in 1.2 MB and no objects', () => {
    const rows: DigestRow[] = Array.from({ length: 100_000 }, (_u, i) => [
      `peer-${i}`, i % 500, (i % 97) - 48, (i % 313) - 156, i % 4,
    ] as DigestRow);
    const chart = chartFromRows(rows, 'big', rows.length);
    expect(chart.positions.byteLength).toBe(100_000 * 3 * 4);
    expect(chart.total).toBe(100_000);
  });

  it('derives the same shape locally when the map is small', () => {
    const chart = chartFromNodes([
      node({ id: 'hub', hop: 0 }),
      node({ id: 'p', hop: 1, group: 'peer_hub', position: { x: 18, y: 0, z: 0 } }),
    ]);
    expect(chart.ids).toEqual(['hub', 'p']);
    expect(Array.from(chart.positions.slice(3))).toEqual([18, 0, 0]);
  });

  it('reads a kind off a node the same way the server does', () => {
    expect(kindOfNode(node({ id: 'a', hop: 0 }))).toBe(KIND_LOCAL);
    expect(kindOfNode(node({ id: 'b', hop: 1, group: 'peer_hub' }))).toBe(KIND_PEER_HUB);
    expect(kindOfNode(node({ id: 'c', hop: 2, group: 'peer_hub_node' }))).toBe(KIND_FAR);
    expect(kindOfNode(node({ id: 'd', hop: 1, group: 'pending_hub' }))).toBe(KIND_PENDING);
  });
});

describe('fetchChart', () => {
  const url = (p: string) => p;

  it('follows the cursor to the end', async () => {
    const pages = [
      { epoch: 'e', total: 3, cursor: 0, next_cursor: 2, rows: [['a', 0, 0, 0, 0], ['b', 1, 0, 0, 1]] },
      { epoch: 'e', total: 3, cursor: 2, next_cursor: null, rows: [['c', 2, 0, 0, 2]] },
    ];
    let call = 0;
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => pages[call++],
    })));
    const chart = await fetchChart(url, {}, 2);
    expect(chart.ids).toEqual(['a', 'b', 'c']);
    expect(chart.total).toBe(3);
    vi.unstubAllGlobals();
  });

  it('refuses to stitch two epochs into one map', async () => {
    const pages = [
      { epoch: 'e1', total: 4, cursor: 0, next_cursor: 2, rows: [['a', 0, 0, 0, 0]] },
      { epoch: 'e2', total: 4, cursor: 2, next_cursor: null, rows: [['b', 1, 0, 0, 0]] },
    ];
    let call = 0;
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => pages[call++] })));
    await expect(fetchChart(url, {}, 1)).rejects.toThrow(/epoch changed/);
    vi.unstubAllGlobals();
  });
});

describe('windowIsStale', () => {
  it('asks for the first window unconditionally', () => {
    expect(windowIsStale(null, { x: 0, y: 0, z: 0, radius: 40 })).toBe(true);
  });

  it('ignores a camera that has barely moved', () => {
    const prev = { x: 0, y: 0, z: 0, radius: 40 };
    expect(windowIsStale(prev, { x: 3, y: 0, z: 0, radius: 41 })).toBe(false);
  });

  it('refetches once the camera is somewhere else', () => {
    const prev = { x: 0, y: 0, z: 0, radius: 40 };
    expect(windowIsStale(prev, { x: 30, y: 0, z: 0, radius: 40 })).toBe(true);
  });

  it('refetches on a real zoom either way', () => {
    const prev = { x: 0, y: 0, z: 0, radius: 40 };
    expect(windowIsStale(prev, { x: 0, y: 0, z: 0, radius: 120 })).toBe(true);
    expect(windowIsStale(prev, { x: 0, y: 0, z: 0, radius: 10 })).toBe(true);
  });
});

describe('mergeWindow', () => {
  const tickNodes = [node({ id: 'hub' }), node({ id: 'federation' })];
  const tickLinks = [link('hub', 'federation')];

  it('is a pass-through when there is no window', () => {
    const out = mergeWindow(tickNodes, tickLinks, null);
    expect(out.nodes).toBe(tickNodes);
    expect(out.links).toBe(tickLinks);
  });

  it('adds what the window brought', () => {
    const out = mergeWindow(tickNodes, tickLinks, {
      nodes: [node({ id: 'peer-7', hop: 1, group: 'peer_hub' })],
      links: [link('federation', 'peer-7')],
    });
    expect(out.nodes.map((n) => n.id)).toEqual(['hub', 'federation', 'peer-7']);
    expect(out.links).toHaveLength(2);
  });

  it('never lets a window snapshot shadow a live tick node', () => {
    // The tick is live and the window is a snapshot; for our own ecosystem the tick wins.
    const stale = node({ id: 'hub', label: 'STALE', status: 'offline' });
    const out = mergeWindow(tickNodes, tickLinks, { nodes: [stale], links: [] });
    expect(out.nodes).toBe(tickNodes);
    expect(out.nodes.find((n) => n.id === 'hub')!.label).toBe('hub');
  });
});

describe('the empty chart', () => {
  it('is safe to render before anything has loaded', () => {
    expect(EMPTY_CHART.ids).toHaveLength(0);
    expect(EMPTY_CHART.positions).toHaveLength(0);
  });
});
