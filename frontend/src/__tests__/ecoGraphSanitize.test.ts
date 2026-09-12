import { describe, expect, it } from 'vitest';
import {
  dropFirstPartyDuplicates,
  hasCatalogCluster,
  sanitizeEcoGraphNodes,
} from '../lib/ecoGraphSanitize';
import type { EcoNode } from '../App';

function node(
  partial: Pick<EcoNode, 'id' | 'label' | 'group'> & Partial<EcoNode>,
): EcoNode {
  return {
    icon: '',
    description: '',
    metrics: {},
    status: 'active',
    position: { x: 0, y: 0, z: 0 },
    ...partial,
  };
}

describe('ecoGraphSanitize', () => {
  it('drops product planets when catalog cluster is present', () => {
    const nodes: EcoNode[] = [
      node({ id: 'factory', label: 'AI-Factory', group: 'core' }),
      node({ id: 'cluster-catalog', label: 'Products · 3', group: 'cluster', position: { x: 5, y: 0, z: 0 } }),
      node({ id: 'prod-a', label: 'Relay', group: 'product', position: { x: 2, y: 1, z: 0 } }),
      node({ id: 'prod-b', label: 'Sentinel', group: 'product', position: { x: 2, y: 1, z: 0 } }),
    ];
    expect(hasCatalogCluster(nodes)).toBe(true);
    const out = sanitizeEcoGraphNodes(nodes);
    expect(out.map((n) => n.id)).toEqual(['factory', 'cluster-catalog']);
  });

  it('keeps product planets when no cluster node exists', () => {
    const nodes: EcoNode[] = [
      node({ id: 'prod-a', label: 'Relay', group: 'product', position: { x: 2, y: 1, z: 0 } }),
    ];
    expect(sanitizeEcoGraphNodes(nodes)).toEqual(nodes);
  });

  it('drops hub-catalogue clones of first-party satellites, not gates into each other', () => {
    const nodes: EcoNode[] = [
      node({ id: 'momus', label: 'MOMUS', group: 'security', icon: 'eye' }),
      node({ id: 'themis', label: 'THEMIS', group: 'security', icon: 'shield' }),
      node({ id: 'lottery', label: 'Agent Lottery', group: 'economy' }),
      node({
        id: 'momus-adversarial-audit-satellite',
        label: 'MOMUS — adversarial-audit satellite',
        group: 'oracle',
        url: 'https://momus.modelmarket.dev',
      }),
      node({
        id: 'themis-clone',
        label: 'THEMIS supply-chain admission auditor',
        group: 'oracle',
        url: 'https://themis.modelmarket.dev',
      }),
      node({
        id: 'lottery-clone',
        label: 'Agent Lottery',
        group: 'oracle',
        url: 'https://lottery.modelmarket.dev',
      }),
    ];
    const out = dropFirstPartyDuplicates(nodes);
    expect(out.map((n) => n.id)).toEqual(['momus', 'themis', 'lottery']);
    expect(out.find((n) => n.id === 'momus')?.group).toBe('security');
    expect(out.find((n) => n.id === 'themis')?.group).toBe('security');
  });

  it('does not swallow the primary hub or competing-lab hub', () => {
    const nodes: EcoNode[] = [
      node({ id: 'hub', label: 'AIMarket Hub', group: 'core', url: 'https://modelmarket.dev' }),
      node({
        id: 'competing_hub',
        label: 'Competing Lab Hub',
        group: 'peer_hub',
        url: 'http://hunt.modelmarket.dev:9083',
      }),
      node({
        id: 'signal_hunt_hub',
        label: 'Signal Hunt Hub',
        group: 'peer_hub',
        url: 'https://hunt.modelmarket.dev',
      }),
      node({
        id: 'signal_hunt',
        label: 'Signal Hunt',
        group: 'client',
        url: 'https://hunt.modelmarket.dev',
      }),
    ];
    expect(dropFirstPartyDuplicates(nodes).map((n) => n.id)).toEqual([
      'hub',
      'competing_hub',
      'signal_hunt_hub',
      'signal_hunt',
    ]);
  });

  it('drops hyphen-id clones of seeded hub suns', () => {
    const nodes: EcoNode[] = [
      node({
        id: 'signal_hunt_hub',
        label: 'Signal Hunt Hub',
        group: 'network',
        url: 'https://hunt.modelmarket.dev',
      }),
      node({
        id: 'signal-hunt-hub',
        label: 'Signal Hunt Hub',
        group: 'peer_hub',
        url: 'https://hunt.modelmarket.dev',
      }),
      node({
        id: 'competing_hub',
        label: 'Competing Lab Hub',
        group: 'network',
        url: 'http://hunt.modelmarket.dev:9083',
      }),
      node({
        id: 'competing-lab-hub',
        label: 'Competing Lab Hub',
        group: 'peer_hub',
        url: 'http://hunt.modelmarket.dev:9083',
      }),
    ];
    expect(dropFirstPartyDuplicates(nodes).map((n) => n.id)).toEqual([
      'signal_hunt_hub',
      'competing_hub',
    ]);
  });

  it('drops a Magic AI-Factory well-known clone next to the factory sun', () => {
    const nodes: EcoNode[] = [
      node({
        id: 'factory',
        label: 'AI-Factory',
        group: 'core',
        url: 'https://magic-ai-factory.com',
      }),
      node({
        id: 'magic-ai-factory-ai-market',
        label: 'Magic AI-Factory AI Market',
        group: 'peer_hub',
        url: 'https://magic-ai-factory.com',
      }),
      node({
        id: 'factory_agents',
        label: 'Agents',
        group: 'agent',
        url: 'https://magic-ai-factory.com/agents',
      }),
    ];
    expect(dropFirstPartyDuplicates(nodes).map((n) => n.id)).toEqual([
      'factory',
      'factory_agents',
    ]);
  });

  it('keeps a foreign peer that is not on a first-party host', () => {
    const nodes: EcoNode[] = [
      node({ id: 'momus', label: 'MOMUS', group: 'security' }),
      node({
        id: 'impostor',
        label: 'MOMUS — adversarial-audit satellite',
        group: 'oracle',
        url: 'https://evil.example/momus',
      }),
    ];
    expect(dropFirstPartyDuplicates(nodes)).toEqual(nodes);
  });
});

describe('canonical_id from the hub', () => {
  const node = (over: Partial<EcoNode> & { id: string }): EcoNode =>
    ({
      label: over.id,
      group: 'oracle',
      icon: 'oracle',
      description: '',
      metrics: {},
      status: 'active',
      position: { x: 0, y: 0, z: 0 },
      ...over,
    }) as EcoNode;

  it('drops a clone the local tables have never heard of', () => {
    // A satellite at a brand-new hostname: no host rule can reach it, and before the
    // hub started answering, this pair drew two planets for one thing.
    const nodes = [
      node({ id: 'skopos' }),
      node({ id: 'fed-skopos-2', url: 'https://skopos-relocated.example', canonical_id: 'skopos' }),
    ];
    expect(sanitizeEcoGraphNodes(nodes).map((n) => n.id)).toEqual(['skopos']);
  });

  it('keeps the clone when the canonical node is not on the map', () => {
    const nodes = [
      node({ id: 'fed-skopos-2', url: 'https://skopos-relocated.example', canonical_id: 'skopos' }),
    ];
    expect(sanitizeEcoGraphNodes(nodes).map((n) => n.id)).toEqual(['fed-skopos-2']);
  });

  it('still falls back to the host tables when no answer travels with the node', () => {
    const nodes = [
      node({ id: 'momus' }),
      node({ id: 'fed-momus', url: 'https://momus.modelmarket.dev' }),
    ];
    expect(sanitizeEcoGraphNodes(nodes).map((n) => n.id)).toEqual(['momus']);
  });

  it('never folds a node onto itself', () => {
    const nodes = [node({ id: 'skopos', url: 'https://skopos.modelmarket.dev', canonical_id: 'skopos' })];
    expect(sanitizeEcoGraphNodes(nodes).map((n) => n.id)).toEqual(['skopos']);
  });
});

describe('the catalogue nebula survives the browser', () => {
  const n = (over: Partial<EcoNode> & { id: string }): EcoNode =>
    ({
      label: over.id,
      group: 'core',
      icon: 'x',
      description: '',
      metrics: {},
      status: 'active',
      position: { x: 0, y: 0, z: 0 },
      ...over,
    }) as EcoNode;

  it('keeps "Products · N" even though it links to the factory storefront', () => {
    // It was in every payload and in no browser: the nebula carries the storefront URL,
    // the fold resolved that to `factory`, saw the factory on the map, and deleted the
    // nebula as a clone. Nineteen products invisible because of one link.
    const nodes = [
      n({ id: 'factory', url: 'https://magic-ai-factory.com' }),
      n({
        id: 'cluster-catalog',
        group: 'cluster',
        label: 'Products · 19',
        url: 'https://magic-ai-factory.com',
        metrics: { count: 19 },
      }),
    ];
    expect(sanitizeEcoGraphNodes(nodes).map((x) => x.id)).toEqual(['factory', 'cluster-catalog']);
  });

  it('keeps the pinned product moons, which link into the same storefront', () => {
    const nodes = [
      n({ id: 'factory', url: 'https://magic-ai-factory.com' }),
      n({
        id: 'prod-bdb1634806de',
        group: 'factory_product',
        url: 'https://magic-ai-factory.com/product/prod-bdb1634806de',
      }),
    ];
    expect(sanitizeEcoGraphNodes(nodes)).toHaveLength(2);
  });

  it('still folds a discovered peer that IS a duplicate', () => {
    const nodes = [
      n({ id: 'momus' }),
      n({ id: 'fed-momus', group: 'oracle', url: 'https://momus.modelmarket.dev' }),
    ];
    expect(sanitizeEcoGraphNodes(nodes).map((x) => x.id)).toEqual(['momus']);
  });

  it('never hands the scene one id twice', () => {
    // The scene keys each sphere on node.id. Two lazily-expanded hubs listing the same
    // peer used to arrive as two nodes under one id, fighting for one position.
    const nodes = [
      n({ id: 'lazy:modelmarket.dev', group: 'peer_hub', url: 'https://modelmarket.dev' }),
      n({ id: 'lazy:modelmarket.dev', group: 'peer_hub', url: 'https://modelmarket.dev' }),
    ];
    expect(sanitizeEcoGraphNodes(nodes)).toHaveLength(1);
  });
});
