import { describe, expect, it } from 'vitest';
import type { EcoNode } from '../App';
import { hasNodeScene, resolveNodeScene } from '../nodeScenes/resolve';

function node(over: Partial<EcoNode> & { id: string }): EcoNode {
  return {
    label: over.id,
    group: 'network',
    icon: 'planet',
    description: '',
    metrics: {},
    status: 'active',
    position: { x: 0, y: 0, z: 0 },
    ...over,
  };
}

describe('resolveNodeScene', () => {
  it('resolves oracles via oracleScenes meta (same slot as before)', () => {
    const n = node({ id: 'oracle-platon', group: 'oracle', color: '#6ee7ff' });
    const s = resolveNodeScene(n);
    expect(s?.kind).toBe('oracle');
    if (s?.kind === 'oracle') expect(s.slug).toBe('platon');
    expect(hasNodeScene(n)).toBe(true);
  });

  it('resolves momus / metis / use_cases / signal_hunt from the registry', () => {
    expect(resolveNodeScene(node({ id: 'momus' }))?.kind).toBe('momus');
    expect(resolveNodeScene(node({ id: 'metis' }))?.kind).toBe('metis');
    expect(resolveNodeScene(node({ id: 'use_cases', color: '#c4f542' }))?.kind).toBe('use_cases');
    expect(resolveNodeScene(node({ id: 'signal_hunt', color: '#ff5ec8' }))?.kind).toBe('signal_hunt');
  });

  it('requires atlas embed before showing a scene', () => {
    expect(resolveNodeScene(node({ id: 'atlas', group: 'core' }))).toBeNull();
    const withEmbed = node({
      id: 'atlas',
      group: 'core',
      atlas_live: { embed_url: 'https://atlas.modelmarket.dev/embed' },
    });
    expect(resolveNodeScene(withEmbed)?.kind).toBe('atlas');
  });

  it('returns null for nodes without a registered preview', () => {
    expect(resolveNodeScene(node({ id: 'factory' }))).toBeNull();
    expect(hasNodeScene(node({ id: 'factory' }))).toBe(false);
  });
});
