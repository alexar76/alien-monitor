import type { EcoNode } from '../App';

const CATALOG_CLUSTER_IDS = new Set(['cluster-catalog']);

/** host → canonical node. Path exceptions are handled in canonicalIdForUrl. */
const FIRST_PARTY_HOSTS: Record<string, string> = {
  'momus.modelmarket.dev': 'momus',
  'iot.modelmarket.dev': 'gaia',
  'gaia.modelmarket.dev': 'gaia',
  'atlas.modelmarket.dev': 'atlas',
  'themis.modelmarket.dev': 'themis',
  'basanos.modelmarket.dev': 'basanos',
  'skopos.modelmarket.dev': 'skopos',
  'metis.modelmarket.dev': 'metis',
  'logos.modelmarket.dev': 'logos',
  'lottery.modelmarket.dev': 'lottery',
  'use.modelmarket.dev': 'use_cases',
  'hub.modelmarket.dev': 'competing_hub',
  'magic-ai-factory.com': 'factory',
  'www.magic-ai-factory.com': 'factory',
};

/** Discovery slugs that are the same sun as a seeded hub. */
const HUB_ID_ALIASES: Record<string, string> = {
  'signal-hunt-hub': 'signal_hunt_hub',
  'fed-signal_hunt_hub': 'signal_hunt_hub',
  'competing-lab-hub': 'competing_hub',
  'fed-competing_hub': 'competing_hub',
  'magic-ai-factory-ai-market': 'factory',
  'magic-ai-factory': 'factory',
};

/** Same HTTPS host as Signal Hunt Hub, but a different ball (the game). */
const KEEP_EVEN_IF_URL_MATCHES = new Set(['signal_hunt']);

/**
 * Groups that are CONTENTS of a node, not a peer that could duplicate one.
 *
 * The catalogue nebula links to the factory storefront because that is where its products
 * live — and the fold below read that URL, resolved it to `factory`, saw the factory on
 * the map and deleted the nebula as a clone. "Products · 19" was in every payload and in
 * no browser: nineteen products invisible because of one link. Anything here is kept no
 * matter whose URL it carries; only things that can genuinely arrive twice get folded.
 */
const NEVER_A_DUPLICATE_PEER = new Set(['cluster', 'product', 'factory_product']);

/** True when the graph already has the factory catalog nebula (collapsed products). */
export function hasCatalogCluster(nodes: EcoNode[]): boolean {
  return nodes.some(
    (n) => n.group === 'cluster' && (CATALOG_CLUSTER_IDS.has(n.id) || n.id.startsWith('cluster-')),
  );
}

function canonicalIdForUrl(url: string | undefined): string | undefined {
  if (!url) return undefined;
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.toLowerCase();
    const path = `${parsed.pathname}${parsed.hash}`.toLowerCase();
    const port = parsed.port
      ? Number(parsed.port)
      : parsed.protocol === 'https:'
        ? 443
        : parsed.protocol === 'http:'
          ? 80
          : undefined;
    if (host === 'momus.modelmarket.dev' && path.includes('treasury')) return 'treasury';
    if (host === 'modelmarket.dev' && path.includes('studio')) return 'hephaestus';
    if (host === 'modeldev.modelmarket.dev' && path.includes('bridges')) return 'bridges';
    if (host === 'hunt.modelmarket.dev') {
      return port === 9083 ? 'competing_hub' : 'signal_hunt_hub';
    }
    if (host === 'magic-ai-factory.com' || host === 'www.magic-ai-factory.com') {
      if (path.includes('agents')) return 'factory_agents';
      if (path.includes('/product/')) return undefined;
      return 'factory';
    }
    return FIRST_PARTY_HOSTS[host];
  } catch {
    return undefined;
  }
}

/**
 * Hub federation lists first-party satellites as sellable peers. Discovery used
 * to mint a second violet oracle for each; drop those clones when the canonical
 * node is already on the map.
 */
export function dropFirstPartyDuplicates(nodes: EcoNode[]): EcoNode[] {
  if (!nodes.length) return nodes;
  const ids = new Set(nodes.map((n) => n.id));
  const filtered = nodes.filter((n) => {
    if (KEEP_EVEN_IF_URL_MATCHES.has(n.id)) return true;
    if (NEVER_A_DUPLICATE_PEER.has(n.group)) return true;
    const alias = HUB_ID_ALIASES[n.id];
    if (alias && n.id !== alias && ids.has(alias)) return false;
    // The backend resolved this from the hub, which resolved it from the operator's
    // pinned seed list. The tables below are a transcription of that same fact and had
    // already drifted from it — they stay as the fallback for payloads that carry no
    // answer, and shrink as more of them do.
    const canonical = n.canonical_id || canonicalIdForUrl(n.url);
    if (!canonical || n.id === canonical) return true;
    return !ids.has(canonical);
  });
  return filtered.length === nodes.length ? nodes : filtered;
}

/**
 * Drop loose product planets when a catalog cluster is present.
 * UNI materializes products as `group: product` entities; collapsed WS state uses
 * `cluster-catalog`. A stale /api/topology poll can briefly send both — stacked
 * labels near Factory until the next WebSocket tick.
 *
 * Also drop hub-discovered violet clones of first-party satellites (MOMUS, …)
 * and hyphen-id clones of seeded hub suns.
 */
/**
 * Last guard before the scene: one id, one object.
 *
 * The scene keys every sphere on `node.id`, so a repeated id is two meshes claiming one
 * slot — React warns, and whichever renders second wins the position. The producers are
 * meant to fold duplicates themselves (see `federationLayout.newLazyNodes`); this is the
 * floor under all of them, because a duplicate that reaches here is a visible defect.
 */
function dropRepeatedIds(nodes: EcoNode[]): EcoNode[] {
  const seen = new Set<string>();
  const unique = nodes.filter((n) => (seen.has(n.id) ? false : (seen.add(n.id), true)));
  return unique.length === nodes.length ? nodes : unique;
}

export function sanitizeEcoGraphNodes(nodes: EcoNode[]): EcoNode[] {
  if (!nodes.length) return nodes;
  const afterCatalog = hasCatalogCluster(nodes)
    ? nodes.filter((n) => n.group !== 'product')
    : nodes;
  const afterDupes = dropRepeatedIds(dropFirstPartyDuplicates(afterCatalog));
  if (afterDupes === nodes) return nodes;
  return afterDupes;
}

export function sanitizeEcoState<T extends { nodes?: EcoNode[] }>(state: T): T {
  if (!state?.nodes?.length) return state;
  const nodes = sanitizeEcoGraphNodes(state.nodes);
  if (nodes === state.nodes) return state;
  return { ...state, nodes };
}
