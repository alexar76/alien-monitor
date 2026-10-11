import { describe, expect, it, vi, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { I18nProvider } from '../i18n';
import ChainScanner from '../components/ChainScanner';

/** A scan payload with only the fields the panel reads. */
function scan(extra: Record<string, unknown>) {
  return {
    chain_id: 31337,
    head: 7908,
    txs: [],
    scanned_blocks: 1,
    note: '',
    chain_mismatch: null,
    network: {
      source: 'settings-network',
      realm: 'live',
      mode: 'real',
      crypto_enabled: true,
      chain: 'base',
      name: 'Base',
      chain_id: 8453,
    },
    ...extra,
  };
}

function mockScan(payload: unknown) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => payload,
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ChainScanner chain-identity banner', () => {
  it('says out loud that the panel is not on the network it advertises', async () => {
    // The LIVE monitor rendered a "Base" header over a local Anvil: both chain ids were in
    // the payload and only the raw field disagreed. The reader has to be told.
    mockScan(scan({
      chain_mismatch: {
        declared_chain: 'base',
        declared_chain_id: 8453,
        observed_chain_id: 31337,
        message: 'RPC answers as chainId 31337 …',
      },
    }));

    render(
      <I18nProvider>
        <ChainScanner themeColor="#00f0ff" realm="real" onClose={() => {}} />
      </I18nProvider>,
    );

    const banner = await waitFor(() => screen.getByRole('status'));
    expect(banner.textContent).toContain('31337');
    expect(banner.textContent).toContain('BASE');
    expect(banner.textContent).toContain('8453');
  });

  it('names the network whose transactions are on screen', async () => {
    // "в блоке аналога эферскана должна быть хорошо видимая пометка, транзакции какой
    // именно сети отображаются" — a bare chain id is not that label.
    mockScan(scan({}));
    render(
      <I18nProvider>
        <ChainScanner themeColor="#00f0ff" realm="real" onClose={() => {}} />
      </I18nProvider>,
    );
    expect(await waitFor(() => screen.getByText(/Base · 8453/))).toBeTruthy();
  });

  it('says so when a LIVE panel is showing the bubble because crypto is off', async () => {
    mockScan(scan({
      chain_id: 31337,
      network: {
        source: 'uni-bubble', realm: 'live', mode: 'real', crypto_enabled: false,
        chain: 'uni', name: 'UNI Anvil', chain_id: 31337,
      },
    }));
    render(
      <I18nProvider>
        <ChainScanner themeColor="#00f0ff" realm="real" onClose={() => {}} />
      </I18nProvider>,
    );
    expect(await waitFor(() => screen.getByText(/UNI Anvil · 31337/))).toBeTruthy();
    const note = screen.getByRole('note');
    expect(note.textContent).toMatch(/crypto is off/i);
    // deliberate, not an error: no alarm banner
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('shows no banner when the chain is the one configured', async () => {
    mockScan(scan({ chain_mismatch: null }));

    render(
      <I18nProvider>
        <ChainScanner themeColor="#00f0ff" realm="universe" onClose={() => {}} />
      </I18nProvider>,
    );

    // wait for the first load to land before asserting an absence
    await waitFor(() => expect(screen.getByText(/7908/)).toBeTruthy());
    expect(screen.queryByRole('status')).toBeNull();
  });
});
