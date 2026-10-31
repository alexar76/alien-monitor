import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { EcoNode } from '../App';
import { I18nProvider } from '../i18n';
import NodeDetail from '../components/NodeDetail';
import { currentProductLabel, productDisplayNodes, productDisplayState } from '../lib/productDisplay';

vi.mock('../components/OraclePrimitive3D', () => ({ default: () => null }));
vi.mock('../components/MetisChat', () => ({ default: () => null }));

function legacyNode(extra: Partial<EcoNode> = {}): EcoNode {
  return {
    id: 'emporion', label: 'EMPORION — public-record facts', group: 'peer_hub_provider',
    icon: 'oracle', description: 'EMPORION checks public registries.', status: 'active',
    metrics: { capabilities: 16 }, position: { x: 0, y: 0, z: 0 },
    url: 'https://emporion.modelmarket.dev/', ...extra,
  };
}

describe('current SYMMARTYS display over observed provider data', () => {
  it('renders the current name while the remote provider still has its former identity', () => {
    const observed = legacyNode();
    const [shown] = productDisplayNodes([observed]);
    render(<I18nProvider><NodeDetail node={shown!} onClose={() => {}} themeColor="#00f0ff" /></I18nProvider>);
    expect(screen.getByTitle('SYMMARTYS — public-record facts').textContent).toContain('SYMMARTYS');
    expect(shown!.id).toBe('emporion');
    expect(shown!.url).toBe(observed.url);
    expect(observed.label).toBe('EMPORION — public-record facts');
  });

  it('projects only human labels and retains signed data, graph ids and operational URLs verbatim', () => {
    const signed = { product_id: 'emporion', capability_id: 'emporion.vat.check@v1', signature: { value: 'signed-bytes' } };
    const observed = { nodes: [{ ...legacyNode(), manifest: signed }],
      links: [{ source: 'emporion', target: 'hub', label: 'EMPORION facts' }],
      events: [{ product_id: 'emporion', label: 'EMPORION result', receipt: signed }], signature: signed.signature };
    const original = JSON.stringify(observed);
    const shown = productDisplayState(observed);
    expect(shown.nodes[0]!.label).toBe('SYMMARTYS — public-record facts');
    expect(shown.nodes[0]!.description).toBe('SYMMARTYS checks public registries.');
    expect(shown.nodes[0]!.manifest).toBe(signed);
    expect(shown.links[0]).toEqual({ source: 'emporion', target: 'hub', label: 'SYMMARTYS facts' });
    expect(shown.events).toBe(observed.events);
    expect(shown.signature).toBe(observed.signature);
    expect(JSON.stringify(observed)).toBe(original);
  });

  it('does not rename an unrelated same-named provider or alter technical identifiers in text', () => {
    const stranger = legacyNode({ id: 'stranger-provider', url: 'https://other.example/' });
    const nodes = [stranger];
    expect(productDisplayNodes(nodes)).toBe(nodes);
    expect(currentProductLabel('EMPORION · emporion.vat.check@v1 · https://emporion.modelmarket.dev · aimarket-emporion'))
      .toBe('SYMMARTYS · emporion.vat.check@v1 · https://emporion.modelmarket.dev · aimarket-emporion');
    expect(currentProductLabel('ЭМПОРИОН / Емпорион — публичные факты'))
      .toBe('SYMMARTYS / SYMMARTYS — публичные факты');
    expect(currentProductLabel('суперэмпорион')).toBe('суперэмпорион');
  });
});
