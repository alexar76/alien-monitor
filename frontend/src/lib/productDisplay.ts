import type { EcoLink, EcoNode } from '../App';

/** A display projection during rollout; identities, routes and signed evidence stay observed. */
export function currentProductLabel(value: string): string {
  // A human brand token only: do not rewrite hosts, package names or capability ids.
  return value.replace(/(?<![\p{L}\p{N}_./:@-])(?:emporion|эмпорион|емпорион)(?![\p{L}\p{N}_./:@-])/giu, 'SYMMARTYS');
}

export function isSymmartysNode(node: Pick<EcoNode, 'id'> & Partial<EcoNode>): boolean {
  if (['emporion', 'symmartys'].includes(node.id) ||
    ['emporion', 'symmartys'].includes(node.canonical_id ?? '')) return true;
  try {
    const url = new URL(node.url ?? '');
    return ['emporion.modelmarket.dev', 'symmartys.modelmarket.dev'].includes(url.hostname) ||
      (url.hostname === 'modelmarket.dev' &&
        ['/providers/emporion', '/providers/symmartys'].includes(url.pathname.replace(/\/$/, '')));
  } catch { return false; }
}

export function productDisplayNodes(nodes: EcoNode[]): EcoNode[] {
  let changed = false;
  const projected = nodes.map((node) => {
    if (!isSymmartysNode(node)) return node;
    const label = currentProductLabel(node.label);
    const description = currentProductLabel(node.description);
    if (label === node.label && description === node.description) return node;
    changed = true;
    return { ...node, label, description };
  });
  return changed ? projected : nodes;
}

export function productDisplayState<T extends { nodes?: EcoNode[]; links?: EcoLink[] }>(state: T): T {
  if (!state.nodes?.length) return state;
  const nodes = productDisplayNodes(state.nodes);
  const brandedIds = new Set(state.nodes.filter(isSymmartysNode).map((node) => node.id));
  let linksChanged = false;
  const links = state.links?.map((link) => {
    if (!brandedIds.has(link.source) && !brandedIds.has(link.target)) return link;
    const label = currentProductLabel(link.label);
    if (label === link.label) return link;
    linksChanged = true;
    return { ...link, label };
  });
  if (nodes === state.nodes && !linksChanged) return state;
  return { ...state, nodes, ...(linksChanged ? { links } : {}) };
}
