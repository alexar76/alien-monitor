import { describe, expect, it } from 'vitest';
import type { EcoNode } from '../App';
import { isPendingHub, pendingHubsFrom } from '../lib/pendingHubs';

function node(partial: Pick<EcoNode, 'id' | 'label' | 'group'> & Partial<EcoNode>): EcoNode {
  return {
    icon: '',
    description: '',
    metrics: {},
    status: 'active',
    position: { x: 0, y: 0, z: 0 },
    ...partial,
  };
}

describe('pendingHubsFrom', () => {
  it('keeps knocking hubs out of the trusted peer list', () => {
    const nodes = [
      node({ id: 'hub', label: 'Us', group: 'core' }),
      node({ id: 'peer:https://a.example', label: 'Peer', group: 'peer_hub' }),
      node({
        id: 'pending:https://stranger.example',
        label: 'Stranger',
        group: 'pending_hub',
        status: 'pending',
        url: 'https://stranger.example',
      }),
    ];
    const pending = pendingHubsFrom(nodes);
    expect(pending).toHaveLength(1);
    expect(pending[0].id).toBe('pending:https://stranger.example');
    expect(nodes.filter((n) => !isPendingHub(n)).map((n) => n.group)).toEqual(['core', 'peer_hub']);
  });

  it('treats an empty graph as nobody knocking', () => {
    expect(pendingHubsFrom(undefined)).toEqual([]);
    expect(pendingHubsFrom([])).toEqual([]);
  });
});
