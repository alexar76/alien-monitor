/**
 * The HESTIA card says which running agents run exactly the source the hearth publishes at /agents/
 * (backend/hestia_status: the roster's handler_sha256 against /agents/catalog.json), links each such
 * row to its entry in that catalogue, and claims nothing for a row the backend did not match.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { EcoNode } from '../App';
import HestiaCard from '../components/cards/HestiaCard';
import en from '../i18n/locales/en.json';
import ru from '../i18n/locales/ru.json';
import es from '../i18n/locales/es.json';
import fr from '../i18n/locales/fr.json';
import zh from '../i18n/locales/zh.json';

const SHA = 'a'.repeat(64);
const CATALOGUE = 'https://hestia.modelmarket.dev/agents/';

function hearth(over: Partial<NonNullable<EcoNode['hestia_live']>> = {}): EcoNode {
  return {
    id: 'hestia',
    label: 'HESTIA',
    group: 'hestia',
    icon: 'hestia',
    description: '',
    metrics: { tenants: 3, ours: 2, third_party: 1 },
    status: 'active',
    color: '#ff9a3c',
    position: { x: 0, y: 0, z: 0 },
    url: 'https://hestia.modelmarket.dev',
    links: { console: 'https://hestia.modelmarket.dev/ui/', catalogue: CATALOGUE },
    hestia_live: {
      version: '0.2.0',
      runtime: 'wasm',
      catalogue_url: CATALOGUE,
      published: 29,
      published_matching: 28,
      tenants: [
        { slug: 'x402-preflight', status: 'running', capability_id: 'x402.preflight@v1',
          owner: { kind: 'operator' }, handler_sha256: SHA, code: 'published' },
        { slug: 'timestamp', status: 'running', capability_id: 'timestamp.verify@v1',
          owner: { kind: 'operator' }, handler_sha256: 'b'.repeat(64), code: 'differs' },
        { slug: 'blackwell-storefront', status: 'running', capability_id: 'x.y@v1',
          owner: { kind: 'owner', label: 'Blackwell' }, handler_sha256: 'c'.repeat(64) },
      ],
      ...over,
    },
  } as EcoNode;
}

const t = (key: string, vars?: Record<string, string | number>, fallback?: string) =>
  (fallback || key).replace(/\{\{(\w+)\}\}/g, (_, k) => String(vars?.[k] ?? ''));

describe('HestiaCard: published code', () => {
  it('marks matching and differing rows and links them to the catalogue', () => {
    render(<HestiaCard node={hearth()} themeColor="#ff9a3c" t={t} />);
    const same = screen.getByText('code = catalogue');
    expect(same.closest('a')?.getAttribute('href')).toBe(`${CATALOGUE}#x402-preflight`);
    expect(same.closest('a')?.getAttribute('title')).toContain(SHA);
    const differs = screen.getByText('code ≠ catalogue');
    expect(differs.closest('a')?.getAttribute('href')).toBe(`${CATALOGUE}#timestamp`);
    // Another owner's agent is not in the catalogue: no mark either way.
    expect(screen.getAllByText(/code [=≠] catalogue/)).toHaveLength(2);
    expect(screen.getByText('28 of 29 catalogued agents run exactly the published code')).toBeTruthy();
    const open = screen.getByText(/Open the agent catalogue/);
    expect(open.closest('a')?.getAttribute('href')).toBe(CATALOGUE);
  });

  it('says nothing about published code when the catalogue was not read', () => {
    const node = hearth({ published: undefined, published_matching: undefined,
      tenants: [{ slug: 'a', status: 'running', owner: { kind: 'operator' }, handler_sha256: SHA }] });
    render(<HestiaCard node={node} themeColor="#ff9a3c" t={t} />);
    expect(screen.queryByText(/catalogued agents/)).toBeNull();
    expect(screen.queryByText(/code [=≠] catalogue/)).toBeNull();
  });

  it('has its words in every language', () => {
    const keys = ['open_catalogue', 'code_published', 'code_differs', 'code_title', 'published_summary'];
    for (const locale of [en, ru, es, fr, zh]) {
      const words = (locale as { hearth: Record<string, string> }).hearth;
      for (const key of keys) expect(words[key], key).toBeTruthy();
      expect(words.published_summary).toContain('{{matching}}');
      expect(words.code_title).toContain('{{sha}}');
    }
  });
});
