/**
 * Node scene registry — ONE place that decides which 3D / visual preview sits
 * under the title+description in every Alien Monitor node card.
 *
 * ## Standard (keep this the only entry path)
 *
 * Resolution order in `resolveNodeScene(node)`:
 *
 * 1. **Oracle prefix** — `node.id` matches `oracle-<slug>` AND slug is listed in
 *    `oracleScenes/meta.ts` → kind `oracle` (R3F scene or ambient iframe via
 *    `OraclePrimitive3D`). Source of truth for scenes remains
 *    `oracles/frontend/src/scenes/` (ported here under `oracleScenes/`).
 *
 * 2. **Explicit registry** — `NODE_SCENE_REGISTRY[node.id]` for non-oracle nodes
 *    (metis, momus, atlas, use_cases, signal_hunt, …). Each entry names a
 *    local thumbnail implementation under `nodeScenes/` or `components/`.
 *
 * 3. **Nothing** — no preview slot (metrics-only card).
 *
 * ## Adding a new preview
 *
 * 1. Prefer porting / adapting the product repo's signature scene (do not invent
 *    a third visual language).
 * 2. Add a lazy module under `nodeScenes/<Name>.tsx` (or reuse an existing
 *    component like `MomusEye` / `MetisStarCanvas`).
 * 3. Register it in `NODE_SCENE_REGISTRY` with `kind`, `accent`, `captionKey`.
 * 4. Oracles: add slug to `ORACLE_SCENE_META` + `SCENE_LOADERS` (or `ambient: true`).
 * 5. Wire nothing else in NodeDetail — `NodeSceneSlot` reads the resolver only.
 *
 * ## Framing
 *
 * Shared chrome (border, height, caption, "open full scene") lives in
 * `NodeSceneSlot`. Scene modules only render the canvas / eye / iframe content.
 */

import type { EcoNode } from '../App';
import { slugFromNodeId } from '../lib/oracleManifest';
import { oracleSceneMeta, type OracleSceneMeta } from '../oracleScenes/meta';

export type NodeSceneKind =
  | 'oracle'
  | 'momus'
  | 'metis'
  | 'atlas'
  | 'use_cases'
  | 'signal_hunt'
  | 'themis';

export interface NodeSceneEntry {
  kind: Exclude<NodeSceneKind, 'oracle'>;
  /** Default accent if the node has no color. */
  accent?: string;
  /** i18n key under nodeDetail.scene.* */
  captionKey: string;
  /** English fallback caption. */
  captionDefault: string;
  /** Show open-full-scene affordance when node.url is set. */
  liveUrlFromNode?: boolean;
}

/** Non-oracle node id → preview. Oracles are resolved by prefix + meta. */
export const NODE_SCENE_REGISTRY: Record<string, NodeSceneEntry> = {
  momus: {
    kind: 'momus',
    captionKey: 'nodeDetail.scene.momus',
    captionDefault: 'Unblinking eye · live corpus pulse',
    liveUrlFromNode: true,
  },
  metis: {
    kind: 'metis',
    accent: '#00e5ff',
    captionKey: 'nodeDetail.scene.metis',
    captionDefault: 'Procedural cosmic star · Fibonacci spikes',
    liveUrlFromNode: true,
  },
  atlas: {
    kind: 'atlas',
    captionKey: 'nodeDetail.scene.atlas',
    captionDefault: 'LIVE vs SIM planetary glass',
    liveUrlFromNode: true,
  },
  use_cases: {
    kind: 'use_cases',
    accent: '#c4f542',
    captionKey: 'nodeDetail.scene.use_cases',
    captionDefault: 'Use-cases portal · wire globe · idea pins',
    liveUrlFromNode: true,
  },
  signal_hunt: {
    kind: 'signal_hunt',
    accent: '#ff5ec8',
    captionKey: 'nodeDetail.scene.signal_hunt',
    captionDefault: 'Federation field · hunt constellation',
    liveUrlFromNode: true,
  },
  themis: {
    kind: 'themis',
    accent: '#66f7c5',
    captionKey: 'nodeDetail.scene.themis',
    captionDefault: 'Admission trail · Candidate → THEMIS → Hub',
    liveUrlFromNode: true,
  },
};

export type ResolvedNodeScene =
  | {
      kind: 'oracle';
      slug: string;
      meta: OracleSceneMeta;
      accent: string;
    }
  | {
      kind: Exclude<NodeSceneKind, 'oracle'>;
      entry: NodeSceneEntry;
      accent: string;
    };

/**
 * Single resolver used by NodeDetail. Returns null when the card has no preview.
 * Atlas requires a live embed URL — registered but resolved only when present.
 */
export function resolveNodeScene(node: EcoNode): ResolvedNodeScene | null {
  if (node.group === 'oracle' && node.id.startsWith('oracle-')) {
    const slug = slugFromNodeId(node.id);
    const meta = oracleSceneMeta(slug);
    if (!meta) return null;
    return {
      kind: 'oracle',
      slug,
      meta,
      accent: node.color || meta.accent,
    };
  }

  const entry = NODE_SCENE_REGISTRY[node.id];
  if (!entry) return null;

  if (entry.kind === 'atlas') {
    const embed = node.atlas_live?.embed_url || node.links?.embed;
    if (!embed) return null;
  }

  return {
    kind: entry.kind,
    entry,
    accent: node.color || entry.accent || '#00f0ff',
  };
}

export function hasNodeScene(node: EcoNode): boolean {
  return resolveNodeScene(node) != null;
}
