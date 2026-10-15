/**
 * An eSIM operator running the kit gets its own card and scene — whatever its id, because every
 * operator is discovered rather than seeded (backend/hub_discovery.esim_operator_node).
 *
 * What the card must never do: invent a number (a seller that did not say how many offers it
 * has shows a dash, not 0), call a demo seller a seller, or turn a peer-supplied address that
 * is not a web page into a link.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { EcoNode } from '../App';
import { I18nProvider } from '../i18n';
import NodeDetail from '../components/NodeDetail';
import { resolveNodeScene } from '../nodeScenes/resolve';
import en from '../i18n/locales/en.json';
import ru from '../i18n/locales/ru.json';
import es from '../i18n/locales/es.json';
import fr from '../i18n/locales/fr.json';
import zh from '../i18n/locales/zh.json';

vi.mock('../components/OraclePrimitive3D', () => ({ default: () => null }));
vi.mock('../components/MetisChat', () => ({ default: () => null }));
vi.mock('../nodeScenes/EsimOperatorScene', () => ({ default: () => <div data-testid="esim-scene" /> }));

function operator(over: Partial<EcoNode> = {}): EcoNode {
  return {
    id: 'example-travel-esim',
    label: 'Example Travel eSIM',
    group: 'esim_operator',
    icon: 'esim',
    description: 'Travel eSIMs for 120 countries',
    metrics: { offers: 640, countries: 120, deliveries_30d: 7, buyers_30d: 5, refunds_30d: 1 },
    status: 'active',
    color: '#2ef2b0',
    position: { x: 0, y: 0, z: 0 },
    url: 'https://esim.example-operator.com',
    esim: {
      product_id: 'esim-example', demo: false, selling: true, refunds: 'automatic', catalog: 'live',
      offers: 640, countries: 120, deliveries_30d: { confirmed: 7, distinct_buyers: 5, refunded: 1 },
      site: 'https://esim.example-operator.com', kit_url: 'https://esim.modelmarket.dev/kit',
    },
    ...over,
  };
}

const panel = (node: EcoNode) =>
  render(
    <I18nProvider>
      <NodeDetail node={node} onClose={() => {}} themeColor="#2ef2b0" />
    </I18nProvider>,
  );

describe('eSIM operator node', () => {
  it('resolves its scene by group, so a new operator needs no registry edit', () => {
    const scene = resolveNodeScene(operator({ id: 'some-brand-new-shop' }));
    expect(scene?.kind).toBe('esim_operator');
    expect(scene && 'accent' in scene ? scene.accent : '').toBe('#2ef2b0');
  });

  it('shows a selling operator with its numbers, its site and the kit', async () => {
    panel(operator());
    expect(screen.getByTestId('esim-mode').textContent).toBe('Selling');
    expect(screen.getByTestId('esim-offers').textContent).toBe('640');
    expect(screen.getByTestId('esim-countries').textContent).toBe('120');
    expect(screen.getByTestId('esim-delivered').textContent).toBe('7');
    expect(screen.getByTestId('esim-buyers').textContent).toBe('5');
    expect(screen.getByTestId('esim-site').getAttribute('href')).toBe('https://esim.example-operator.com');
    expect(screen.getByTestId('esim-kit').getAttribute('href')).toBe('https://esim.modelmarket.dev/kit');
    expect(await screen.findByTestId('esim-scene')).toBeTruthy();
  });

  it('calls a demo seller a demo, and shows what nobody reported as a dash', () => {
    panel(operator({
      esim: { demo: true, offers: null, countries: null, deliveries_30d: { confirmed: 0, distinct_buyers: 0, refunded: 0 },
              site: 'https://esim.example-operator.com' },
    }));
    expect(screen.getByTestId('esim-mode').textContent).toBe('Demo');
    expect(screen.getByTestId('esim-offers').textContent).toBe('—');
    expect(screen.getByTestId('esim-delivered').textContent).toBe('0');
  });

  it('never links an address that is not a web page', () => {
    panel(operator({ url: 'javascript:alert(1)', esim: { demo: false, site: 'javascript:alert(1)', kit_url: 'ftp://x' } }));
    expect(screen.queryByTestId('esim-site')).toBeNull();
    expect(screen.queryByTestId('esim-kit')).toBeNull();
  });

  it('is translated in all five languages', () => {
    for (const catalog of [en, ru, es, fr, zh] as Record<string, any>[]) {
      for (const key of ['role', 'openSite', 'runKit', 'offers', 'countries', 'delivered', 'buyers', 'deliveriesNote']) {
        expect(catalog.esim?.[key], key).toBeTruthy();
      }
      expect(catalog.esim.mode.selling && catalog.esim.mode.demo).toBeTruthy();
      expect(catalog.group.esim_operator).toBeTruthy();
      expect(catalog.nodeDetail.scene.esim_operator).toBeTruthy();
    }
  });
});
