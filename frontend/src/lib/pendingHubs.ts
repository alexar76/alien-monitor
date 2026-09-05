import type { EcoNode } from '../App';

/** Hubs that knocked and wait for sandbox assay / operator review — never mixed with trusted peers. */
export function isPendingHub(node: EcoNode): boolean {
  return node.group === 'pending_hub';
}

export function pendingHubsFrom(nodes: EcoNode[] | undefined | null): EcoNode[] {
  return (nodes ?? []).filter(isPendingHub);
}
