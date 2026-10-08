/**
 * Mobile sheets must keep landing/live CTAs above the dock.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { I18nProvider } from '../i18n';
import HephaestusRuns from '../components/HephaestusRuns';
import NodeDetail from '../components/NodeDetail';
import type { EcoNode } from '../App';

vi.mock('../components/OraclePrimitive3D', () => ({ default: () => null }));
vi.mock('../nodeScenes/NodeSceneSlot', () => ({ default: () => null }));

const baseNode = (over: Partial<EcoNode> = {}): EcoNode =>
  ({
    id: 'probe',
    label: 'Probe',
    group: 'core',
    icon: '◆',
    description: 'probe node',
    metrics: {},
    status: 'active',
    position: { x: 0, y: 0, z: 0 },
    ...over,
  }) as EcoNode;

describe('mobile sheet CTAs stay visible', () => {
  it('pins the Hephaestus studio link outside the scrolling run list', () => {
    const node = baseNode({
      id: 'hephaestus',
      label: 'HEPHAESTUS',
      url: 'https://studio.example.test/',
      hephaestus_live: {
        studio_url: 'https://studio.example.test/',
        traces: [
          {
            trace_id: 'tr_deadbeef',
            total_usd: 0.003,
            hops: 2,
            duration_ms: 400,
            signed: true,
            completed_at: new Date().toISOString(),
            steps: [],
          },
        ],
        totals: {},
        catalogue: {},
      },
    } as unknown as Partial<EcoNode>);

    const { container } = render(
      <I18nProvider>
        <HephaestusRuns node={node} themeColor="#00f0ff" onClose={() => {}} mobile />
      </I18nProvider>,
    );

    const cta = screen.getByRole('link', { name: /open the forge/i });
    expect(cta.getAttribute('href')).toBe('https://studio.example.test/');
    const sheet = container.querySelector('.mobile-sheet');
    expect(sheet).toBeTruthy();
    expect(sheet?.className).not.toMatch(/\bbottom-0\b/);
    const scroll = sheet?.querySelector('.overflow-y-auto');
    expect(scroll).toBeTruthy();
    expect(scroll?.contains(cta)).toBe(false);
  });

  it('pins landing and live links on a node card', () => {
    const node = baseNode({
      url: 'https://live.example.test/',
      links: {
        landing: 'https://landing.example.test/',
        live: 'https://live.example.test/',
      },
    });

    render(
      <I18nProvider>
        <NodeDetail node={node} onClose={() => {}} themeColor="#00f0ff" mobile />
      </I18nProvider>,
    );

    expect(screen.getByRole('link', { name: /open landing/i }).getAttribute('href')).toBe(
      'https://landing.example.test/',
    );
    expect(screen.getByRole('link', { name: /open live/i }).getAttribute('href')).toBe(
      'https://live.example.test/',
    );
  });

  it('truncates a long explorer URL, reveals it on hover, and copies', async () => {
    const href = 'https://basescan.org/address/0xe7f1725e7734ce288f8367e1bb143e90bb3f0512';
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    render(
      <I18nProvider>
        <NodeDetail
          node={baseNode({ id: 'settlement', url: href })}
          onClose={() => {}}
          themeColor="#00f0ff"
        />
      </I18nProvider>,
    );

    const link = screen.getByRole('link');
    expect(link.getAttribute('href')).toBe(href);
    expect(link.textContent).toMatch(/…/);
    expect(link.textContent).not.toContain(href);

    const row = link.parentElement as HTMLElement;
    fireEvent.mouseEnter(row);
    expect(link.textContent).toContain(href);

    fireEvent.click(screen.getByRole('button', { name: /copy/i }));
    expect(writeText).toHaveBeenCalledWith(href);
  });
});
