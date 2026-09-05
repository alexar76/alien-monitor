import type { EcoLink, EcoNode } from '../App';
import { hopOf } from './federationLayout';

/**
 * The map as two things: a chart you can hold, and a window you can read.
 *
 * Measured before this existed: 5 005 nodes took 35 s to load, 15 005 sat at the software
 * renderer's floor, and 50 005 killed the browser process. Not by drawing — the far field
 * has been one draw call since the batching pass — but by building fifty thousand React
 * components and Object3Ds to describe dots. So past a threshold the client stops receiving
 * the graph and receives this instead:
 *
 *   STAR CHART   every node as five numbers, decoded straight into typed arrays and never
 *                turned into an object. A hundred thousand of these is 1.2 MB of Float32
 *                and one `<points>`.
 *   WINDOW       full nodes near the camera, capped by the server. These become real
 *                objects, because these are the ones a reader can actually resolve.
 *
 * Below the threshold the server sends the whole graph exactly as before and the chart is
 * built locally from it, so there is one rendering path rather than two.
 */

export interface StarChart {
  epoch: string;
  total: number;
  ids: string[];
  positions: Float32Array;
  colors: Float32Array;
}

/** Server-side kind codes — see `map_window.kind_of`. */
export const KIND_LOCAL = 0;
export const KIND_PEER_HUB = 1;
export const KIND_FAR = 2;
export const KIND_PENDING = 3;

/**
 * One colour per kind, because a digest row has no group to look one up from. Matches the
 * palette the real nodes use: core cyan, peer-hub blue, its peers paler, a stranger amber.
 */
const KIND_RGB: [number, number, number][] = [
  [0.0, 0.94, 1.0],
  [0.22, 0.88, 1.0],
  [0.5, 0.83, 1.0],
  [1.0, 0.8, 0.3],
];

export type DigestRow = [string, number, number, number, number];

export interface DigestPage {
  epoch: string;
  total: number;
  cursor: number;
  next_cursor: number | null;
  rows: DigestRow[];
}

export interface MapPointer {
  windowed?: boolean;
  total?: number;
  local?: number;
  epoch?: string;
  digest_page?: number;
  window_limit?: number;
}

export const EMPTY_CHART: StarChart = {
  epoch: '',
  total: 0,
  ids: [],
  positions: new Float32Array(0),
  colors: new Float32Array(0),
};

function paint(colors: Float32Array, at: number, kind: number): void {
  const rgb = KIND_RGB[kind] ?? KIND_RGB[0];
  colors[at] = rgb[0];
  colors[at + 1] = rgb[1];
  colors[at + 2] = rgb[2];
}

/** Decode digest rows into the arrays the point cloud draws from. */
export function chartFromRows(rows: DigestRow[], epoch: string, total?: number): StarChart {
  const ids: string[] = new Array(rows.length);
  const positions = new Float32Array(rows.length * 3);
  const colors = new Float32Array(rows.length * 3);
  for (let i = 0; i < rows.length; i += 1) {
    const [id, x, y, z, kind] = rows[i];
    ids[i] = id;
    positions[i * 3] = x;
    positions[i * 3 + 1] = y;
    positions[i * 3 + 2] = z;
    paint(colors, i * 3, kind);
  }
  return { epoch, total: total ?? rows.length, ids, positions, colors };
}

/** The same chart, derived locally — the path a small map takes. */
export function chartFromNodes(nodes: EcoNode[]): StarChart {
  const usable = nodes.filter((n) => n.position);
  const ids: string[] = new Array(usable.length);
  const positions = new Float32Array(usable.length * 3);
  const colors = new Float32Array(usable.length * 3);
  usable.forEach((node, i) => {
    ids[i] = node.id;
    positions[i * 3] = node.position.x;
    positions[i * 3 + 1] = node.position.y;
    positions[i * 3 + 2] = node.position.z;
    paint(colors, i * 3, kindOfNode(node));
  });
  return { epoch: `local:${usable.length}`, total: usable.length, ids, positions, colors };
}

export function kindOfNode(node: EcoNode): number {
  if (node.group === 'pending_hub' || node.group === 'pending_hub_node') return KIND_PENDING;
  const hop = hopOf(node);
  if (hop === 0) return KIND_LOCAL;
  if (hop === 1) return KIND_PEER_HUB;
  return KIND_FAR;
}

/**
 * Pull the whole chart, page by page.
 *
 * `signal` matters more than it looks: a hundred thousand rows is twenty-five pages, and an
 * epoch that changes mid-fetch would otherwise leave half of one chart stitched to half of
 * another. The caller aborts and starts again rather than merging two truths.
 */
export async function fetchChart(
  url: (path: string) => string,
  init: RequestInit,
  pageSize = 4000,
): Promise<StarChart> {
  const rows: DigestRow[] = [];
  let cursor: number | null = 0;
  let epoch = '';
  let total = 0;
  let pages = 0;
  while (cursor !== null) {
    const res = await fetch(url(`/api/map/digest?cursor=${cursor}&limit=${pageSize}`), init);
    if (!res.ok) throw new Error(`digest HTTP ${res.status}`);
    const page = (await res.json()) as DigestPage;
    if (epoch && page.epoch !== epoch) {
      // The map moved under us. Half of one chart plus half of another is not a map.
      throw new Error('digest epoch changed mid-fetch');
    }
    epoch = page.epoch;
    total = page.total;
    rows.push(...(page.rows || []));
    cursor = page.next_cursor;
    pages += 1;
    if (pages > 500) break; // two million rows: something is wrong upstream
  }
  return chartFromRows(rows, epoch, total);
}

export interface WindowRequest {
  x: number;
  y: number;
  z: number;
  radius: number;
  focus?: string[];
}

export interface MapWindow {
  nodes: EcoNode[];
  links: EcoLink[];
  truncated?: boolean;
}

export async function fetchWindow(
  url: (path: string) => string,
  init: RequestInit,
  req: WindowRequest,
): Promise<MapWindow> {
  const focus = (req.focus || []).filter(Boolean).join(',');
  const query =
    `x=${req.x.toFixed(2)}&y=${req.y.toFixed(2)}&z=${req.z.toFixed(2)}`
    + `&radius=${req.radius.toFixed(2)}`
    + (focus ? `&focus=${encodeURIComponent(focus)}` : '');
  const res = await fetch(url(`/api/map/window?${query}`), init);
  if (!res.ok) throw new Error(`window HTTP ${res.status}`);
  const body = await res.json();
  const links: EcoLink[] = (Array.isArray(body?.links) ? body.links : []).map(
    (l: { source: string; target: string; label?: string }) => ({
      source: l.source,
      target: l.target,
      // EcoLink requires a label; a link the server did not name is still a link.
      label: l.label ?? '',
    }),
  );
  return {
    nodes: Array.isArray(body?.nodes) ? body.nodes : [],
    links,
    truncated: Boolean(body?.truncated),
  };
}

/**
 * Has the camera moved far enough to be looking at somewhere else?
 *
 * A window is a request; asking for one every frame is how a scaling fix becomes a
 * different load problem. The camera has to travel a real fraction of the window it already
 * has before the next one is worth fetching.
 */
export function windowIsStale(
  previous: { x: number; y: number; z: number; radius: number } | null,
  next: { x: number; y: number; z: number; radius: number },
): boolean {
  if (!previous) return true;
  const moved = Math.hypot(previous.x - next.x, previous.y - next.y, previous.z - next.z);
  if (moved > previous.radius * 0.35) return true;
  const zoom = next.radius / Math.max(1e-6, previous.radius);
  return zoom > 1.5 || zoom < 0.66;
}

/**
 * The graph the scene draws: what the tick gave us, plus whatever the window filled in.
 *
 * Window nodes never replace a tick node — the tick is live and the window is a snapshot,
 * so for our own ecosystem the tick is the fresher of the two.
 */
export function mergeWindow(
  tickNodes: EcoNode[],
  tickLinks: EcoLink[],
  windowed: MapWindow | null,
): { nodes: EcoNode[]; links: EcoLink[] } {
  if (!windowed || (!windowed.nodes.length && !windowed.links.length)) {
    return { nodes: tickNodes, links: tickLinks };
  }
  const have = new Set(tickNodes.map((n) => n.id));
  const extraNodes = windowed.nodes.filter((n) => !have.has(n.id));
  const linkKey = (l: EcoLink) => `${l.source}|${l.target}`;
  const haveLinks = new Set(tickLinks.map(linkKey));
  const extraLinks = windowed.links.filter((l) => !haveLinks.has(linkKey(l)));
  if (!extraNodes.length && !extraLinks.length) return { nodes: tickNodes, links: tickLinks };
  return { nodes: [...tickNodes, ...extraNodes], links: [...tickLinks, ...extraLinks] };
}
