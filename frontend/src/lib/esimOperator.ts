import type { EcoNode } from '../App';

/**
 * How an eSIM operator's sphere differs from its neighbours'. Its colour is its own shade of
 * the operators' green (backend/node_palette.esim_shade); here: how big and how bright.
 *
 *   size  — the reach of its catalogue, by countries, on a log scale: a shop for 200
 *           countries reads bigger than one for 10 without swallowing the map.
 *   glow  — a seller that sells shines; a demo, which only quotes, is dimmed; a seller whose
 *           node did not say is in between.
 */
export type EsimMode = 'selling' | 'demo' | 'unknown';

export interface EsimSphere {
  mode: EsimMode;
  size: number;
  /** Multiplier on emissive, corona and ring: 1 = selling. */
  glow: number;
}

const SIZE_FLOOR = 0.22;
const SIZE_PER_DOUBLING = 0.04;
const SIZE_CAP = 0.58;
const SIZE_UNKNOWN = 0.3;

export function esimMode(node: EcoNode): EsimMode {
  const demo = node.esim?.demo;
  return demo === false ? 'selling' : demo === true ? 'demo' : 'unknown';
}

export function esimSphere(node: EcoNode): EsimSphere {
  const mode = esimMode(node);
  const raw = node.esim?.countries ?? node.metrics?.countries;
  const countries = typeof raw === 'number' && Number.isFinite(raw) && raw > 0 ? raw : null;
  const size = countries == null
    ? SIZE_UNKNOWN
    : Math.min(SIZE_CAP, SIZE_FLOOR + SIZE_PER_DOUBLING * Math.log2(1 + countries));
  const glow = mode === 'selling' ? 1 : mode === 'demo' ? 0.45 : 0.65;
  return { mode, size, glow };
}

/** The body colour: a demo's sphere is darker as well as dimmer, or scene light makes it look
 *  as lit as a seller's. `factor` scales lightness; 1 for a seller. */
export function esimBodyFactor(glow: number): number {
  return 0.45 + 0.55 * glow;
}

