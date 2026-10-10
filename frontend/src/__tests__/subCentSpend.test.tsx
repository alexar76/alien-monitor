/**
 * Spend figures on the agent panels — rendered, not just formatted.
 *
 * money.test.ts proves formatUsd keeps sub-cent digits. These prove the panels actually call it:
 * each of them used to carry its own toFixed, which printed a $0.015 agent as "$0.01" and a
 * $0.00001 hop as "$0.0000" — a paid call reading as free.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import type { EcoNode } from '../App';
import { I18nProvider } from '../i18n';
import FactoryAgentsCard from '../components/cards/FactoryAgentsCard';
import HephaestusRuns from '../components/HephaestusRuns';
import ArgusRun from '../components/ArgusRun';

const t = (_key: string, _vars?: Record<string, string | number>, fallback?: string) => fallback ?? _key;

const baseNode = (over: Record<string, unknown>): EcoNode =>
  ({
    id: 'probe', label: 'Probe', group: 'core', icon: '◆', description: 'probe node',
    metrics: {}, status: 'active', position: { x: 0, y: 0, z: 0 },
    ...over,
  }) as unknown as EcoNode;

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('FactoryAgentsCard spend', () => {
  it('keeps half a cent and a tenth of a cent on screen', () => {
    const node = baseNode({
      id: 'factory-agents',
      factory_agents_live: {
        agents: [
          { agent_id: 'ag_half', name: 'Half', status: 'live', spend_usd_total: 0.015 },
          { agent_id: 'ag_tenth', name: 'Tenth', status: 'live', spend_usd_total: 0.0015 },
        ],
        summary: { agents_total: 2, agents_live: 2, spend_usd_total: 0.0165 },
      },
    });
    render(<FactoryAgentsCard node={node} themeColor="#3dd6c6" t={t} />);
    expect(screen.getByText('$0.015')).toBeTruthy();
    expect(screen.getByText('$0.0015')).toBeTruthy();
    expect(screen.getByText(/\$0\.0165 spent/)).toBeTruthy();
    expect(screen.queryByText('$0.01')).toBeNull();
    expect(screen.queryByText('$0.02')).toBeNull();
  });
});

describe('HephaestusRuns spend', () => {
  it('prints a sub-cent hop price instead of $0.0000', () => {
    const node = baseNode({
      id: 'hephaestus',
      label: 'HEPHAESTUS',
      hephaestus_live: {
        traces: [
          {
            trace_id: 'tr_subcent',
            total_usd: 0.015,
            hops: 1,
            steps: [{ id: 's1', capability_id: 'gaia.weather.read', success: true, price_usd: 0.00001 }],
          },
        ],
        totals: { runs: 1, spend_usd: 0.0015 },
        catalogue: {},
      },
    });
    render(
      <I18nProvider>
        <HephaestusRuns node={node} themeColor="#ff8844" onClose={() => {}} />
      </I18nProvider>,
    );
    expect(screen.getByText('$0.0015')).toBeTruthy();   // totals.spend_usd
    expect(screen.getByText('$0.00001')).toBeTruthy();  // the hop
    expect(screen.getByText(/\$0\.015 ·/)).toBeTruthy(); // the trace line
    expect(screen.queryByText('$0.0000')).toBeNull();
  });
});

describe('ArgusRun receipt spend', () => {
  it('shows a sub-mill spend instead of $0.002', () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 404 })));
    const node = baseNode({
      id: 'argus',
      label: 'ARGUS',
      argus_run: { id: 'run_subcent', goal: 'g', beats: [], spendUsd: 0.0015, receiptHash: '0xabc', signer: '0x12' },
    });
    render(
      <I18nProvider>
        <ArgusRun node={node} mode="real" themeColor="#00f0ff" onClose={() => {}} />
      </I18nProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: /^run$/i }));
    // No beats: the first tick of the player seals the run and the receipt appears.
    act(() => { vi.advanceTimersByTime(1100); });
    expect(screen.getByText('$0.0015')).toBeTruthy();
    expect(screen.queryByText('$0.002')).toBeNull();
  });
});
