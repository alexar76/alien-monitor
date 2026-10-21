import type { EcoNode } from '../../App';
import { openableFor } from '../../lib/nodeUrls';

interface Props {
  node: EcoNode;
  themeColor: string;
  mobile?: boolean;
  t: (key: string, vars?: Record<string, string | number>, defaultValue?: string) => string;
}

const SELLING = '#2ef2b0';
const DEMO = '#ffcc4d';
const CAPABILITIES = ['esim.quote@v1', 'esim.order@v1', 'esim.status@v1'];
/** Metrics this card shows itself; NodeDetail leaves them out of its generic grid. */
export const ESIM_CARD_METRICS = new Set(['offers', 'countries', 'deliveries_30d', 'buyers_30d', 'refunds_30d']);

/**
 * An operator running the eSIM operator kit: a seller in the AI economy whose travel eSIMs
 * agents buy over x402, straight to its wallet. Every number here is the seller's own
 * (/agents/healthz) or our hub's (buyers' signed delivery receipts, checked on Base) —
 * a number nobody reported is shown as a dash, never as zero.
 */
export default function EsimOperatorCard({ node, themeColor, t }: Props) {
  const esim = node.esim || {};
  const site = openableFor(esim.site || node.url);
  const kit = openableFor(esim.kit_url);
  const deliveries = esim.deliveries_30d || {};
  const accent = themeColor || SELLING;
  const dash = (v: number | null | undefined) => (typeof v === 'number' ? v.toLocaleString() : '—');

  const mode =
    esim.demo === false
      ? { color: SELLING, label: t('esim.mode.selling', undefined, 'Selling'),
          note: t('esim.mode.sellingNote', undefined, 'Agents pay this seller over x402, in USDC on Base, straight to its wallet.') }
      : esim.demo === true
        ? { color: DEMO, label: t('esim.mode.demo', undefined, 'Demo'),
            note: t('esim.mode.demoNote', undefined, 'Live prices, no sales: every order is refused with demo_mode.') }
        : { color: '#8a93a6', label: t('esim.mode.unknown', undefined, 'Mode unknown'),
            note: t('esim.mode.unknownNote', undefined, 'The seller node did not answer at /agents/healthz.') };

  const stats: { key: string; label: string; value: string }[] = [
    { key: 'offers', label: t('esim.offers', undefined, 'Offers'), value: dash(esim.offers) },
    { key: 'countries', label: t('esim.countries', undefined, 'Countries'), value: dash(esim.countries) },
    { key: 'delivered', label: t('esim.delivered', undefined, 'Delivered, 30 d'), value: dash(deliveries.confirmed) },
    { key: 'buyers', label: t('esim.buyers', undefined, 'Buyers, 30 d'), value: dash(deliveries.distinct_buyers) },
    { key: 'refunded', label: t('esim.refunded', undefined, 'Refunded, 30 d'), value: dash(deliveries.refunded) },
    {
      key: 'refunds',
      label: t('esim.refunds', undefined, 'Refunds'),
      value: esim.refunds === 'automatic'
        ? t('esim.refundsAutomatic', undefined, 'automatic')
        : esim.refunds === 'operator'
          ? t('esim.refundsOperator', undefined, 'by the operator')
          : '—',
    },
  ];

  return (
    <div className="mb-4" onClick={(e) => e.stopPropagation()} data-testid="esim-operator-card">
      <div
        className="mb-3 px-3 py-2 rounded-sm text-[11px] font-mono leading-relaxed"
        style={{ background: '#00000030', border: `1px solid ${accent}33` }}
      >
        <div className="flex items-center gap-2 mb-1">
          <span
            className="px-1.5 py-0.5 rounded-sm text-[10px] uppercase tracking-wider"
            style={{ color: mode.color, border: `1px solid ${mode.color}66`, background: `${mode.color}14` }}
            data-testid="esim-mode"
          >
            {mode.label}
          </span>
          <span className="text-white/70">
            {t('esim.role', undefined, 'eSIM operator · runs the eSIM operator kit')}
          </span>
        </div>
        <div className="text-white/45">{mode.note}</div>
        {esim.catalog === 'snapshot' ? (
          <div className="mt-1" style={{ color: DEMO }}>
            {t('esim.snapshot', undefined, 'Its wholesaler is not answering: it serves the last catalogue it had.')}
          </div>
        ) : null}
      </div>

      <div className="grid grid-cols-3 gap-1.5 mb-2">
        {stats.map((s) => (
          <div key={s.key} className="px-2 py-1.5 rounded-sm bg-white/5 text-[11px] font-mono">
            <div className="text-white/40 text-[10px] leading-tight">{s.label}</div>
            <div style={{ color: accent }} data-testid={`esim-${s.key}`}>{s.value}</div>
          </div>
        ))}
      </div>
      <div className="text-[10px] font-mono text-white/35 mb-3 leading-snug">
        {t(
          'esim.deliveriesNote',
          undefined,
          'Deliveries are counted from buyers’ signed receipts, each checked against its transfer on Base by the hub. The hub sees no amounts.',
        )}
      </div>

      <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-1">
        {t('esim.capabilities', undefined, 'What agents call')}
      </div>
      <div className="flex flex-wrap gap-1 mb-3">
        {CAPABILITIES.map((c) => (
          <span key={c} className="px-1.5 py-0.5 rounded-sm bg-white/5 text-[10px] font-mono text-white/60">{c}</span>
        ))}
      </div>

      <div className="flex flex-col gap-1.5">
        {site ? (
          <a
            href={site}
            target="_blank"
            rel="noopener noreferrer"
            className="block px-3 py-2 rounded-sm text-xs font-mono transition-colors hover:brightness-110"
            style={{ backgroundColor: accent + '1e', border: `1px solid ${accent}55`, color: accent }}
            data-testid="esim-site"
          >
            {t('esim.openSite', undefined, 'Open the operator’s site')} ↗
          </a>
        ) : null}
        {kit ? (
          <a
            href={kit}
            target="_blank"
            rel="noopener noreferrer"
            className="block px-3 py-2 rounded-sm text-xs font-mono transition-colors hover:brightness-110 text-white/70"
            style={{ border: '1px solid #ffffff22' }}
            data-testid="esim-kit"
          >
            {t('esim.runKit', undefined, 'Sell eSIMs to agents too: the operator kit')} ↗
          </a>
        ) : null}
      </div>
    </div>
  );
}
