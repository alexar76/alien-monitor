import { useEffect, useRef, useState } from 'react';
import { apiUrl } from '../api';
import { useI18n } from '../i18n';

const providerNames = { laso: 'Laso', coinmarketcap: 'CoinMarketCap', tavily: 'Tavily' };
const statuses = ['succeeded', 'failed', 'attempted'] as const;

type Operation = Record<(typeof statuses)[number], number> & {
  source: 'argus' | 'metis';
  operation: 'card_quote' | 'card_issue' | 'card_checkout' | 'quotes' | 'search';
};

type Summary = {
  state: 'ok';
  window_seconds: number;
  providers: { id: keyof typeof providerNames; operations: Operation[] }[];
} | { state: 'disabled' | 'unavailable' };

interface Props {
  onClose: () => void;
  themeColor: string;
}

export default function ProviderEvents({ onClose, themeColor }: Props) {
  const { t, locale } = useI18n();
  const dialog = useRef<HTMLDialogElement>(null);
  const [summary, setSummary] = useState<Summary | null>(null);

  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    let next: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      try {
        const response = await fetch(apiUrl('/api/provider-events'), {
          cache: 'no-store',
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(5000)]),
        });
        if (!response.ok) throw new Error('Provider events unavailable');
        const value: Summary = await response.json();
        if (!controller.signal.aborted) setSummary(value);
      } catch {
        if (!controller.signal.aborted) setSummary({ state: 'unavailable' });
      }
      if (!controller.signal.aborted) next = setTimeout(refresh, 15000);
    };
    void refresh();
    return () => {
      controller.abort();
      clearTimeout(next);
    };
  }, []);

  const count = new Intl.NumberFormat(locale);

  return (
    <dialog
      ref={dialog}
      aria-labelledby="provider-events-heading"
      onClose={onClose}
      className="glass-panel fixed inset-0 m-auto max-h-[85dvh] w-[calc(100%-2rem)] max-w-xl overflow-y-auto rounded-xl p-4 text-white backdrop:bg-black/65 md:p-6"
      style={{ borderColor: themeColor + '55' }}
    >
      <header className="flex items-start justify-between gap-4">
        <div>
          <h2 id="provider-events-heading" className="text-base font-semibold" style={{ color: themeColor }}>
            {t('providerEvents.title')}
          </h2>
          <p className="mt-1 text-xs text-white/65">{t('providerEvents.scope')}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label={t('providerEvents.close')}
          className="min-h-10 min-w-10 rounded-md border border-white/15 text-xl leading-none hover:bg-white/10"
        >
          ×
        </button>
      </header>
      {summary?.state === 'ok' ? (
        <div className="mt-4 grid gap-3">
          {summary.providers.map(({ id, operations }) => (
            <section key={id} className="rounded-lg border border-white/15 px-3 py-2">
              <h3 className="mb-1 text-sm font-semibold">{providerNames[id]}</h3>
              <table className="w-full border-collapse text-left text-xs">
                <thead>
                  <tr className="text-white/55">
                    <th className="py-1 font-medium">{t('providerEvents.operation')}</th>
                    {statuses.map(status => (
                      <th key={status} className="py-1 text-right font-medium">{t(`providerEvents.${status}`)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {operations.map(operation => (
                    <tr key={`${operation.source}/${operation.operation}`} className="border-t border-white/10">
                      <th scope="row" className="py-1 pr-2 font-normal">
                        {t(`providerEvents.${operation.operation}`)}
                        <span className="ml-1 text-white/55">{operation.source.toUpperCase()}</span>
                      </th>
                      {statuses.map(status => (
                        <td key={status} className="py-1 text-right tabular-nums">{count.format(operation[status])}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          ))}
        </div>
      ) : (
        <p className="mt-4 text-sm text-white/65" role="status">
          {t(`providerEvents.${summary?.state ?? 'loading'}`)}
        </p>
      )}
    </dialog>
  );
}
