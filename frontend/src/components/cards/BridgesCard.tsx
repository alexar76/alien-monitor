import type { EcoNode } from '../../App';

interface Props {
  node: EcoNode;
  themeColor: string;
  mobile?: boolean;
  t: (key: string, vars?: Record<string, string | number>, defaultValue?: string) => string;
}

/* BRIDGES — the third paid invoke channel, and the only one nothing counts.
   This panel exists to answer "how much is billed through it" and, today, to say plainly
   that nobody knows — without ever printing a 0 or an amount that would be read as one. */
export default function BridgesCard({ node, themeColor, t }: Props) {
        const b = node.bridges_live!;
        const counters = b.counters || {};
        const settlement = b.settlement || {};
        // Money is rendered only WITH its settlement word. An undeclared settlement is treated as
        // simulated, because that is the direction in which a wrong guess is harmless.
        const hasSpend = typeof b.spend_usd === 'number';
        const realValue = settlement.moves_real_value === true;
        const reasonText =
          b.reason === 'unreachable'
            ? t('bridges.reason_unreachable', undefined,
                'A telemetry endpoint is configured but did not answer. No figures are shown rather than stale ones.')
            : b.reason === 'no-counters'
              ? t('bridges.reason_no_counters', undefined,
                  'The endpoint answered, but reported no counters.')
              : t('bridges.reason_no_endpoint', undefined,
                  'No telemetry endpoint exists — the monitor never asked, because there is nothing to ask.');
        const labels: Record<string, string> = {
          tools_exported: t('bridges.counter.tools_exported', undefined, 'tools exported'),
          paid_invokes: t('bridges.counter.paid_invokes', undefined, 'paid invokes'),
          receipts_issued: t('bridges.counter.receipts_issued', undefined, 'receipts issued'),
          receipts_verified: t('bridges.counter.receipts_verified', undefined, 'receipts verified'),
          budget_rejections: t('bridges.counter.budget_rejections', undefined, 'budget-capped rejections'),
        };
        const order = ['tools_exported', 'paid_invokes', 'receipts_issued', 'receipts_verified', 'budget_rejections'];
        return (
          <div className="mb-4" onClick={(e) => e.stopPropagation()}>
            {/* What this channel is — descriptive, never counted as traffic. */}
            <div className="mb-3 px-3 py-2 rounded text-[11px] font-mono"
                 style={{ background: '#00000030', border: `1px solid ${themeColor}33` }}>
              <div className="text-white/70 mb-1">🌉 {t('bridges.channel', undefined, 'Third paid invoke channel · after the hub and the mesh')}</div>
              <div className="text-white/45">{t('bridges.role', undefined, 'Framework-native tools · signed receipts · hard budget ceiling')}</div>
              <div className="text-white/50 mt-1">
                {t('bridges.frameworks', undefined, 'Frameworks')}: {(b.frameworks || []).join(' · ') || '—'}
              </div>
              <div className="text-white/35 mt-0.5">
                {b.package || 'aimarket-bridges'}{b.version ? ` · v${b.version}` : ''}
              </div>
            </div>

            {/* The question the viewer came with. Unmeasured names render "—", never 0. */}
            <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-2">
              {t('bridges.billed', undefined, 'Billed through this channel')}
            </div>
            <div className="space-y-1 mb-3">
              {order.map((k) => {
                const measured = Object.prototype.hasOwnProperty.call(counters, k);
                return (
                  <div key={k}
                       className="flex items-center justify-between px-2 py-1.5 rounded bg-white/5 text-[11px] font-mono">
                    <span className="text-white/50">{labels[k]}</span>
                    {measured ? (
                      <span style={{ color: themeColor }}>{counters[k]}</span>
                    ) : (
                      /* "—" and the word, not 0: a zero would claim we measured and found none. */
                      <span className="text-white/30">— {t('bridges.not_measured', undefined, 'not measured')}</span>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Money — only ever printed next to the word that says whether it moved. */}
            {hasSpend ? (
              <div className="mb-3 px-2 py-1.5 rounded text-[11px] font-mono"
                   style={{ background: '#00000030', border: `1px solid ${realValue ? '#ff6b3d44' : '#43e65a44'}` }}>
                <span className="text-white/40">{t('bridges.spend', undefined, 'Billed')}:</span>{' '}
                <span style={{ color: themeColor }}>${Number(b.spend_usd).toFixed(2)}</span>
                <span className="text-white/50"> · {(settlement.mode || 'uni').toUpperCase()} · </span>
                <span style={{ color: realValue ? '#ff6b3d' : '#43e65a' }}>
                  {realValue
                    ? t('bridges.real_value', undefined, 'real value')
                    : t('bridges.simulated', undefined, 'simulated · no money moves')}
                </span>
                {settlement.declared === false && (
                  <div className="text-white/35 mt-0.5">
                    {t('bridges.undeclared', undefined, 'settlement undeclared by the source · treated as simulated')}
                  </div>
                )}
              </div>
            ) : (
              <div className="mb-3 text-[10px] font-mono text-white/30">
                {t('bridges.no_money', undefined, 'No amount is shown — no counter reports one.')}
              </div>
            )}

            {b.window && (
              <div className="mb-3 text-[10px] font-mono text-white/35">
                {t('bridges.window', undefined, 'Window')}: {b.window}
              </div>
            )}

            {/* Why there are no figures. The panel says which of the three states it is in. */}
            {!b.instrumented && (
              <div className="mb-3 px-3 py-2 rounded text-[11px] font-mono"
                   style={{ background: '#ffcc3310', border: '1px solid #ffcc3333' }}>
                <div style={{ color: '#ffcc33' }} className="mb-1">
                  ⚠ {t('bridges.not_instrumented', undefined, 'This channel is not instrumented')}
                </div>
                <div className="text-white/55">{reasonText}</div>
                <div className="text-white/40 mt-1">
                  {t('bridges.library_note', undefined,
                    'aimarket-bridges is a client library that runs inside the buyer’s own process, so its spend counter and receipt checks never leave it. No aggregate reaches the monitor.')}
                </div>
              </div>
            )}

            {node.links?.github && (
              <a href={node.links.github} target="_blank" rel="noreferrer"
                 className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
                 style={{ backgroundColor: themeColor + '12', border: `1px solid ${themeColor}33`, color: themeColor }}>
                {t('nodeDetail.community.github')} ↗
              </a>
            )}
          </div>
        );
}

