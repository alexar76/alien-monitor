import type { EcoNode } from '../../App';

interface Props {
  node: EcoNode;
  themeColor: string;
  mobile?: boolean;
  t: (key: string, vars?: Record<string, string | number>, defaultValue?: string) => string;
}

interface LogosSource {
  name: string;
  status: string;
  elapsed_ms?: number | null;
  value?: number | string | null;
  unit?: string;
}

/**
 * LOGOS — federation analytics engine.
 *
 * The card used to show two tiles and both were dashes: the poller only read
 * /health, which carries {status, service, version} and no counts at all.
 *
 * The counts now live in the panel's own METRICS grid, which already localises its
 * labels — repeating them here was four tiles of the same numbers. This card shows
 * what that grid cannot: every source LOGOS polled, whether it answered, what it
 * reported, and the round-trip LOGOS measured getting it. A source that did not
 * answer shows a dash, never a zero — a zero on a dashboard is a measurement, and
 * inventing one is worse than admitting a gap.
 */
export default function LogosCard({ node, themeColor, mobile, t }: Props) {
  const live = node.logos_live as Record<string, unknown> | undefined;
  const sources = (live?.sources as LogosSource[] | undefined) ?? [];

  const num = (v: unknown): string =>
    v === null || v === undefined ? '—' : String(v);

  const toneColor = (tone?: 'bad' | 'warn') =>
    tone === 'bad' ? '#ff2d55' : tone === 'warn' ? '#ffcc33' : themeColor;

  return (
    <div className="mb-4" onClick={(e) => e.stopPropagation()}>
      {!live ? (
        <div
          className="px-3 py-2 rounded text-[11px] font-mono leading-relaxed"
          style={{ background: '#ffcc3312', border: '1px solid #ffcc3344', color: '#ffcc33' }}
        >
          {t('logos.unreachable', undefined,
            'LOGOS could not be reached. No analytics data is shown.')}
        </div>
      ) : (
        <>
          {/* What LOGOS observed, with the latency it measured doing so. */}
          {sources.length > 0 && (
            <div className="mb-3">
              <div className="text-[9px] font-mono text-white/40 uppercase tracking-wider mb-1.5">
                {t('logos.sources', undefined, 'Polled sources · measured latency')}
              </div>
              <div className="space-y-1">
                {sources.map((s) => {
                  const ok = s.status === 'ok';
                  return (
                    <div
                      key={s.name}
                      className="flex items-center justify-between gap-2 px-2 py-1 rounded text-[10px] font-mono"
                      style={{ background: 'rgba(255,255,255,0.03)' }}
                    >
                      <span className="flex items-center gap-1.5">
                        <i
                          className="inline-block w-1.5 h-1.5 rounded-full"
                          style={{ background: ok ? '#4ade80' : '#ff2d55' }}
                        />
                        <span className="uppercase text-white/70">{s.name}</span>
                      </span>
                      <span className="flex items-center gap-2">
                        <span style={{ color: ok ? '#4ade80' : '#ff2d55' }}>
                          {ok ? num(s.value) : '—'}
                        </span>
                        {s.elapsed_ms != null && (
                          <span className="text-white/35">{Math.round(s.elapsed_ms)} ms</span>
                        )}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* A projection exists only when the hub published measured settlement
              volume; otherwise LOGOS says so, and so does this card. */}
          {live.spend_basis === 'measured_24h_settlement_volume' ? (
            <div className="px-2 py-1.5 rounded text-[10px] font-mono mb-3 text-white/60"
                 style={{ background: 'rgba(255,255,255,0.03)' }}>
              {t('logos.spendMeasured', undefined, '30-day projection')}:{' '}
              <span style={{ color: themeColor }}>${num(live.monthly_spend_usd)}</span>
            </div>
          ) : live.spend_basis ? (
            <div className="px-2 py-1.5 rounded text-[10px] font-mono mb-3 text-white/45 italic"
                 style={{ background: 'rgba(255,255,255,0.03)' }}>
              {t('logos.spendUnavailable', undefined,
                'Spend unavailable — the hub published no measured settlement volume')}
            </div>
          ) : null}

          {live.generated_at && (
            <div className="text-[9px] font-mono text-white/30 mb-2">
              {t('logos.snapshotAt', undefined, 'Snapshot')}: {String(live.generated_at).slice(0, 19)}
              {live.version ? ` · v${String(live.version)}` : ''}
            </div>
          )}

          {node.url && (
            <a
              href={node.url}
              target="_blank"
              rel="noreferrer"
              className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
              style={{
                backgroundColor: themeColor + '1e',
                border: `1px solid ${themeColor}55`,
                color: themeColor,
              }}
            >
              {t('logos.launch', undefined, '🧠 Open LOGOS dashboard')} ↗
            </a>
          )}
        </>
      )}
    </div>
  );
}
