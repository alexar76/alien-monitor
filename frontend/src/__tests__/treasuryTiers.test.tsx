/**
 * Treasury settlement tiers — what the panel actually PUTS ON SCREEN.
 *
 * The backend tests (alien-monitor/tests/test_treasury_tiers.py) prove the data is honest. These
 * prove the honesty survives rendering, which is where it matters: a reader believes pixels, not
 * JSON. Three rules, asserted against the DOM:
 *
 *   offline is offline     an unreachable source renders its reason and NO figure
 *   zero ≠ absent          a measured 0 is shown (with the reason it is correct); a tier nobody
 *                          deployed renders "not connected" and never the character 0
 *   simulated is labelled  UNI says "simulated", TEST mode says "synthetic" — in the panel
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import type { EcoNode, TreasuryTier } from '../App';
import { I18nProvider } from '../i18n';
import NodeDetail from '../components/NodeDetail';

// The panel pulls in the 3D oracle scenes and the Metis chat; neither belongs to a Treasury node
// and neither survives jsdom, so they are stubbed at the module boundary.
vi.mock('../components/OraclePrimitive3D', () => ({ default: () => null }));
vi.mock('../components/MetisChat', () => ({ default: () => null }));

const UNI_OK: TreasuryTier = {
  tier: 'uni', label: 'UNI', state: 'ok', measured: true, simulated: true,
  read_at: '2026-08-09T10:11:12+00:00', source: 'treasury /vault (loopback)',
  balance_usd: 400, reserved_usd: 150, available_usd: 250, transactions: 5,
  settlement_mode: 'uni',
};

const UNI_DOWN: TreasuryTier = {
  tier: 'uni', label: 'UNI', state: 'unreachable', measured: false, simulated: true,
  read_at: '2026-08-09T10:11:12+00:00', source: 'treasury /vault (loopback)',
  detail: 'ConnectError: Connection refused',
};

const BASE_ZERO: TreasuryTier = {
  tier: 'base', label: 'BASE', state: 'ok', measured: true, simulated: false,
  read_at: '2026-08-09T10:11:12+00:00', chain: 'base', chain_id: 8453,
  address: '0x89A618F66767101B96977e536797838661A63426',
  eth: 0, usdc: 0, deployed: true, payout_optin_required: true, settlement_mode: 'uni',
  explorer: 'https://basescan.org/address/0x89A618F66767101B96977e536797838661A63426',
  errors: [],
};

const SOLANA_ABSENT: TreasuryTier = {
  tier: 'solana', label: 'SOLANA', state: 'not_connected', measured: false, simulated: false,
  read_at: '2026-08-09T10:11:12+00:00', account: null, sol: null, chain: 'solana',
  source: 'no Solana treasury account deployed — never queried',
};

function treasuryNode(tiers: TreasuryTier[], extra: Record<string, unknown> = {}): EcoNode {
  return {
    id: 'treasury', label: 'Treasury', group: 'infra', icon: '🏦',
    description: 'The separate payer', metrics: {}, status: 'active',
    position: { x: 0, y: 0, z: 0 },
    treasury_live: {
      health_online: true, treasury_pubkey: 'abc123', external_verifiers: 1,
      counts: { paid: 2, held: 1, refused: 0 }, tiers, ...extra,
    },
  } as EcoNode;
}

function paint(node: EcoNode) {
  return render(
    <I18nProvider>
      <NodeDetail node={node} onClose={() => {}} themeColor="#43e65a" />
    </I18nProvider>,
  );
}

/** The rendered row for one tier, so an assertion cannot accidentally match a neighbour's text. */
function row(label: string): HTMLElement {
  const heading = screen.getByText(label, { selector: 'span' });
  const box = heading.closest('div.rounded');
  if (!box) throw new Error(`no row found for tier ${label}`);
  return box as HTMLElement;
}

describe('Treasury settlement tiers — the panel', () => {
  it('renders all three tiers with their figures', () => {
    paint(treasuryNode([UNI_OK, BASE_ZERO, SOLANA_ABSENT]));
    expect(screen.getByText(/Balance by settlement tier/i)).toBeTruthy();

    const uni = within(row('UNI'));
    expect(uni.getByText('$400.00')).toBeTruthy();
    expect(uni.getByText('$150.00')).toBeTruthy();
    expect(uni.getByText('$250.00')).toBeTruthy();
    expect(uni.getByText('5')).toBeTruthy();

    const base = within(row('BASE'));
    expect(base.getByText('ETH')).toBeTruthy();
    expect(base.getByText('USDC')).toBeTruthy();
  });

  it('labels the UNI balance simulated — every time, measured or not', () => {
    const { unmount } = paint(treasuryNode([UNI_OK]));
    expect(within(row('UNI')).getByText('simulated')).toBeTruthy();
    expect(row('UNI').textContent).toContain('no value moves');
    unmount();

    paint(treasuryNode([UNI_DOWN]));
    expect(within(row('UNI')).getByText('simulated')).toBeTruthy();
  });

  it('shows no figure at all when the vault is unreachable, and says why', () => {
    paint(treasuryNode([UNI_DOWN, BASE_ZERO, SOLANA_ABSENT]));
    const uni = row('UNI');
    expect(uni.textContent).toContain('unreachable');
    expect(uni.textContent).toContain('Connection refused');
    expect(uni.textContent).toContain('no figure');
    expect(uni.textContent).not.toContain('$');
  });

  it('refuses to render a stale figure even when the payload still carries one', () => {
    // The backend drops the keys on an unreachable read, but the panel must not depend on that:
    // if a last-known number ever arrives with state=unreachable, showing it is the lie. The
    // timestamp is the only number allowed through, and it is labelled "tried", not "read".
    paint(treasuryNode([{ ...UNI_OK, state: 'unreachable', measured: false, detail: 'vault HTTP 502' }]));
    const uni = row('UNI');
    expect(uni.textContent).toContain('unreachable');
    expect(uni.textContent).toContain('vault HTTP 502');
    expect(uni.textContent).not.toContain('400');
    expect(uni.textContent).not.toContain('$');
    expect(uni.textContent).toContain('tried');
    expect(uni.textContent).not.toContain('read 1');
  });

  it('keeps each tier independent — a dead vault does not blank Base', () => {
    paint(treasuryNode([UNI_DOWN, BASE_ZERO, SOLANA_ABSENT]));
    expect(row('UNI').textContent).toContain('unreachable');
    // …and the neighbours are untouched.
    const base = row('BASE');
    expect(base.textContent).toContain('ETH');
    expect(base.textContent).toContain('measured');
    expect(row('SOLANA').textContent).toContain('not connected');
  });

  it('renders the Base zero WITH the reason it is the correct state', () => {
    paint(treasuryNode([UNI_OK, BASE_ZERO, SOLANA_ABSENT]));
    const base = row('BASE');
    expect(base.textContent).toContain('measured');   // the zero was read, not assumed
    expect(base.textContent).toContain('0');
    // Without this sentence a reader files 0/0 as "broken" instead of "not opted in".
    expect(base.textContent).toContain('zero is the correct state');
    expect(base.textContent).toContain('MOMUS_BOUNTY_ONCHAIN=1');
  });

  it('renders Solana as "not connected" and never as a zero', () => {
    paint(treasuryNode([UNI_OK, BASE_ZERO, SOLANA_ABSENT]));
    const sol = row('SOLANA');
    expect(sol.textContent).toContain('not connected');
    expect(sol.textContent).toContain('never queried');
    // The absence is explained by "nothing exists to ask", NOT by "a source failed" — the two
    // are different facts and the panel must not borrow the unreachable wording for this one.
    expect(sol.textContent).toContain('nothing deployed to query');
    expect(sol.textContent).not.toContain('could not be reached');
    // The strong form: the digit 0 does not appear anywhere in this row.
    expect(sol.textContent).not.toMatch(/\d/);
    expect(sol.textContent).not.toContain('SOL 0');
  });

  it('labels TEST-mode figures synthetic in the panel, not only in a tooltip', () => {
    const synth = (ti: TreasuryTier): TreasuryTier => ({ ...ti, synthetic: true, measured: false });
    paint(treasuryNode([synth(UNI_OK), synth(BASE_ZERO), synth(SOLANA_ABSENT)], { synthetic: true }));
    expect(screen.getByText(/TEST mode — every figure below is synthetic/i)).toBeTruthy();
    for (const label of ['UNI', 'BASE', 'SOLANA']) {
      expect(within(row(label)).getByText('synthetic')).toBeTruthy();
    }
    expect(row('UNI').textContent).toContain('these figures are invented');
  });

  it('hides the pubkey and the decision counters when the audit surface is offline', () => {
    // A 0 in "refused" would claim the Treasury turned everything down. We never asked it.
    paint(treasuryNode([UNI_OK, BASE_ZERO, SOLANA_ABSENT], {
      health_online: false, treasury_pubkey: undefined, counts: { paid: 0, held: 0, refused: 0 },
    }));
    expect(screen.getByText(/audit surface offline/i)).toBeTruthy();
    expect(screen.queryByText(/^refused 0$/)).toBeNull();
    expect(screen.queryByText(/^paid 0$/)).toBeNull();
    // The tiers read their own sources, so they are all still there.
    expect(within(row('UNI')).getByText('$400.00')).toBeTruthy();
    expect(row('BASE').textContent).toContain('ETH');
  });

  it('flags a partial Base read instead of pretending the missing figure is zero', () => {
    paint(treasuryNode([{ ...BASE_ZERO, usdc: null, eth: 0.25, errors: ['usdc: endpoint down'] }]));
    const base = row('BASE');
    expect(base.textContent).toContain('0.25');
    expect(base.textContent).toContain('partial read');
    expect(base.textContent).toContain('usdc: endpoint down');
    expect(base.textContent).not.toContain('USDC');
  });

  it('does not call a tier "zero" when one of its figures failed to read', () => {
    // ETH really is 0, but USDC is unknown. "Zero is the correct state" would assert something
    // about a figure we never got — the honest line here is the partial read, not the zero story.
    paint(treasuryNode([{ ...BASE_ZERO, usdc: null, errors: ['usdc: endpoint down'] }]));
    const base = row('BASE');
    expect(base.textContent).toContain('partial read');
    expect(base.textContent).not.toContain('zero is the correct state');
  });

  it('still offers the block explorer when our own Base read failed', () => {
    // We could not read it; the reader still can. The address is known statically.
    paint(treasuryNode([{ ...BASE_ZERO, state: 'unreachable', measured: false, eth: null, usdc: null, deployed: null, detail: 'all 5 RPC endpoint(s) for base failed' }]));
    const base = row('BASE');
    expect(base.textContent).toContain('unreachable');
    expect(within(base).getByRole('link', { name: /block explorer/i })).toBeTruthy();
    expect(base.textContent).not.toContain('ETH');
  });

  it('never renders a tier block at all when the backend sent no tiers', () => {
    paint(treasuryNode([]));
    expect(screen.queryByText(/Balance by settlement tier/i)).toBeNull();
  });
});
