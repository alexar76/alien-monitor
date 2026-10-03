/**
 * The activity stream's free-trial rows.
 *
 * A sandbox visitor's call is recorded by the hub at price 0. The row used to show the
 * agent, the capability and a "USDT" badge but no figure — a paid call that seemed to have
 * lost its amount. A trial now says "$0 · trial"; a paid call keeps its real figure.
 */
import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { I18nProvider } from '../i18n';
import TransactionFlow from '../components/TransactionFlow';
import type { TxEvent } from '../App';

const ev = (over: Partial<TxEvent>): TxEvent => ({
  id: 'e', ts: new Date().toISOString(), agent: 'anonymous', action: 'invoke',
  target: 'gaia.weather.read@v1', amount: 0, token: '', ...over,
});

describe('TransactionFlow trial rows', () => {
  it('labels a $0 sandbox call as a trial and keeps a paid call\'s figure', () => {
    render(
      <I18nProvider>
        <TransactionFlow
          transactions={[]}
          themeColor="#00ffff"
          events={[
            ev({ id: 't', agent: 'sandbox:2a48e1bd919f', target: 'gaia.air.read@v1', trial: true }),
            ev({ id: 'p', amount: 0.001, token: 'USDT' }),
          ]}
        />
      </I18nProvider>,
    );
    expect(screen.getByText(/\$0 · trial/)).toBeTruthy();
    expect(screen.getByText('$0.001')).toBeTruthy();
    // one badge only: the paid call's — the trial carries no invented token
    expect(screen.getAllByText('USDT')).toHaveLength(1);
  });
});
