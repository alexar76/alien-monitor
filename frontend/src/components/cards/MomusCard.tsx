import type { EcoNode } from '../../App';
import { MOMUS_SEVERITIES, hasSeverityBreakdown } from '../MomusEye';

interface Props {
  node: EcoNode;
  themeColor: string;
  mobile?: boolean;
  t: (key: string, vars?: Record<string, string | number>, defaultValue?: string) => string;
}

/* MOMUS — red-team scan parameters, live findings, self-learning, key-separation proof.
   Rendered for the momus node whether or not MOMUS answered: when it did not,
   the eye freezes and this block says so, rather than vanishing without a word. */
export default function MomusCard({ node, themeColor, mobile, t }: Props) {
  return (
    <>
        {/* The eye moved to the slot under the title — see cards/NodeVisual.tsx. */}
        <div className="mb-4" onClick={(e) => e.stopPropagation()}>
          {!node.momus_live && (
            <div className="px-3 py-2 rounded text-[11px] font-mono leading-relaxed"
                 style={{ background: '#ffcc3312', border: '1px solid #ffcc3344', color: '#ffcc33' }}>
              {t('momus.unreachable', undefined,
                'MOMUS could not be reached. No scan parameters, findings or counts are shown — nothing here is carried over from an earlier poll.')}
            </div>
          )}
        </div>

      {node.momus_live && (() => {
        const m = node.momus_live!;
        const sevColor: Record<string, string> = {
          critical: '#ff2d55', high: '#ff6b3d', medium: '#ffcc33', low: '#4db8ff', info: '#7a8699',
        };
        const counts = m.finding_counts;
        const countsReported = hasSeverityBreakdown(counts);
        const scores = m.intel?.category_scores || {};
        const topScores = Object.entries(scores).sort((a, b) => b[1] - a[1]).slice(0, 6);
        const maxScore = topScores.length ? Math.max(...topScores.map(([, v]) => v)) : 1;
        return (
          <div className="mb-4" onClick={(e) => e.stopPropagation()}>
            {/* Parameters row */}
            <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-2">
              {t('momus.params', undefined, 'Scan parameters')}
            </div>
            <div className="grid grid-cols-2 gap-1.5 mb-3">
              <div className="px-2 py-1.5 rounded bg-white/5 text-[11px] font-mono">
                <span className="text-white/40">{t('momus.llm', undefined, 'LLM')}:</span>{' '}
                <span style={{ color: themeColor }}>{m.provider?.provider || '—'}</span>
                {m.provider?.model ? <span className="text-white/50"> · {m.provider.model}</span> : null}
                {m.provider?.reachable === false ? <span style={{ color: '#ff6b3d' }}> · {t('common.offline', undefined, 'offline')}</span> : null}
              </div>
              <div className="px-2 py-1.5 rounded bg-white/5 text-[11px] font-mono">
                <span className="text-white/40">{t('momus.posture', undefined, 'Posture')}:</span>{' '}
                <span style={{ color: m.prod ? '#43e65a' : '#ffcc33' }}>{m.prod ? 'prod' : 'dev'}</span>
                <span className="text-white/50"> · {m.crypto_enabled ? t('momus.crypto_on', undefined, 'crypto on') : t('momus.crypto_off', undefined, 'crypto off')}</span>
              </div>
            </div>

            {/* Settlement tier + persistent corpus — what "paid" means, and what MOMUS remembers. */}
            <div className="grid grid-cols-2 gap-1.5 mb-3">
              <div className="px-2 py-1.5 rounded bg-white/5 text-[11px] font-mono">
                <span className="text-white/40">{t('momus.settlement', undefined, 'Settlement')}:</span>{' '}
                <span style={{ color: m.settlement?.moves_real_value ? '#ff6b3d' : '#43e65a' }}>
                  {(m.settlement?.mode || 'uni').toUpperCase()}
                </span>
                <span className="text-white/50">
                  {' '}· {m.settlement?.moves_real_value
                    ? t('momus.real_value', undefined, 'real value')
                    : t('momus.simulated', undefined, 'simulated · no money moves')}
                </span>
              </div>
              <div className="px-2 py-1.5 rounded bg-white/5 text-[11px] font-mono">
                <span className="text-white/40">{t('momus.corpus', undefined, 'Corpus')}:</span>{' '}
                <span style={{ color: themeColor }}>{m.corpus?.total_findings ?? 0}</span>
                <span className="text-white/50">
                  {' '}{t('momus.bugs', undefined, 'bugs')} · {m.corpus?.recurring ?? 0}{' '}
                  {t('momus.recurring', undefined, 'recurring')} · {m.corpus?.backend || '—'}
                </span>
              </div>
            </div>

            {/* Key-separation proof — the "someone else pays" invariant, visible. */}
            <div className="mb-3 px-3 py-2 rounded text-[11px] font-mono"
                 style={{ background: '#00000030', border: `1px solid ${themeColor}33` }}>
              <div className="text-white/70 mb-1">🔑 {t('momus.separation', undefined, 'Finds & signs — cannot pay itself')}</div>
              <div className="text-white/45 break-all">scanner {m.scanner_pubkey || '—'}…</div>
              <div style={{ color: m.holds_treasury_key ? '#ff2d55' : '#43e65a' }}>
                {m.holds_treasury_key
                  ? '⚠ holds treasury key (misconfigured!)'
                  : t('momus.no_treasury', undefined, '✓ does NOT hold the Treasury key')}
              </div>
            </div>

            {/* Findings by severity */}
            <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-2">
              {t('momus.findings', undefined, 'Findings')}
            </div>
            {/* A count is drawn only where MOMUS reported one. With no breakdown at all the
                chips are withheld and the reason is named — five zeros would claim a clean
                sweep nobody measured. */}
            {countsReported ? (
              <div className="flex flex-wrap gap-1.5 mb-2">
                {MOMUS_SEVERITIES.map((s) => (
                  <span key={s} className="px-2 py-0.5 rounded text-[10px] font-mono"
                        style={{ background: sevColor[s] + '22', color: sevColor[s], border: `1px solid ${sevColor[s]}44` }}>
                    {s} {typeof counts?.[s] === 'number' ? counts[s] : '—'}
                  </span>
                ))}
              </div>
            ) : (
              <div className="mb-2 text-[10px] font-mono" style={{ color: '#ffcc33' }}>
                {t('momus.counts_unreported', undefined, 'no severity breakdown reported — this is not a count of zero')}
              </div>
            )}
            <div className="space-y-1 mb-3 max-h-48 overflow-y-auto">
              {(m.findings || []).slice(0, 8).map((f, i) => (
                <div key={f.finding_id || i} className="px-2 py-1.5 rounded bg-white/5 text-[11px]">
                  <div className="flex items-center gap-1.5">
                    <span className="px-1 rounded text-[9px] font-mono"
                          style={{ background: (sevColor[String(f.severity)] || '#7a8699') + '22', color: sevColor[String(f.severity)] || '#7a8699' }}>
                      {f.severity}
                    </span>
                    <span className="text-white/40 font-mono text-[10px]">{f.probe}</span>
                    {f.signed ? <span className="text-[9px]" title="Ed25519-signed">🔏</span> : null}
                  </div>
                  <div className="text-white/70 mt-0.5">{f.title}</div>
                </div>
              ))}
              {(!m.findings || m.findings.length === 0) && (
                <div className="text-white/40 text-[11px] font-mono">{t('momus.no_findings', undefined, 'No findings surfaced yet.')}</div>
              )}
            </div>

            {/* Self-learning: which attack classes it probes first */}
            {topScores.length > 0 && (
              <>
                <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-1">
                  {t('momus.learning', undefined, 'Self-learning · probe priority')}
                  {m.intel?.cards_total ? <span className="text-white/30"> · {m.intel.cards_total} {t('momus.cards', undefined, 'intel cards')}</span> : null}
                </div>
                <div className="space-y-1 mb-2">
                  {topScores.map(([cat, v]) => (
                    <div key={cat} className="flex items-center gap-2 text-[10px] font-mono">
                      <span className="text-white/50 w-24 truncate">{cat}</span>
                      <div className="flex-1 h-1.5 rounded bg-white/10 overflow-hidden">
                        <div className="h-full rounded" style={{ width: `${Math.round((v / maxScore) * 100)}%`, background: themeColor }} />
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}

            {node.links?.landing && (
              <a href={node.links.landing} target="_blank" rel="noreferrer"
                 className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
                 style={{ backgroundColor: themeColor + '1e', border: `1px solid ${themeColor}55`, color: themeColor }}>
                {t('momus.launch', undefined, '🔴 Open live panel · launch a scan')} ↗
              </a>
            )}
          </div>
        );
      })()}
    </>
  );
}

