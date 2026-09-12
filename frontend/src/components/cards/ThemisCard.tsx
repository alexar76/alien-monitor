import type { EcoNode } from '../../App';

interface Props {
  node: EcoNode;
  themeColor: string;
  mobile?: boolean;
  t: (key: string, vars?: Record<string, string | number>, defaultValue?: string) => string;
}

const DECISION_COLOR: Record<string, string> = {
  approve: '#43e65a',
  review: '#ffcc33',
  reject: '#ff2d55',
};

const METIS_COLOR: Record<string, string> = {
  pending: '#a855f7',
  completed: '#00f0ff',
  not_performed: '#7a8699',
  timeout: '#ff6b3d',
  unavailable: '#ff6b3d',
  failed: '#ff2d55',
  skipped: '#7a8699',
};

function decisionColor(decision?: string | null): string {
  return DECISION_COLOR[String(decision || '').toLowerCase()] || '#7a8699';
}

function metisColor(status?: string | null): string {
  return METIS_COLOR[String(status || '').toLowerCase()] || '#a855f7';
}

function modeTone(mode?: string): { color: string; labelKey: string; fallback: string } {
  switch (mode) {
    case 'enforce':
      return { color: '#43e65a', labelKey: 'sca.mode_enforce', fallback: 'enforce · fail-closed' };
    case 'advisory':
      return { color: '#ffcc33', labelKey: 'sca.mode_advisory', fallback: 'advisory · never blocks' };
    case 'off':
      return { color: '#7a8699', labelKey: 'sca.mode_off', fallback: 'off · gate idle' };
    default:
      return { color: '#7a8699', labelKey: 'sca.mode_unknown', fallback: 'mode unknown' };
  }
}

/** Publish-time admission panel — dossier-free Hub receipts, not invoke-time WARDEN. */
export default function ThemisCard({ node, themeColor, t }: Props) {
  const live = node.themis_live;
  if (!live) {
    return (
      <div className="mb-4" onClick={(e) => e.stopPropagation()}>
        <div
          className="px-3 py-2 rounded text-[11px] font-mono leading-relaxed"
          style={{ background: '#ffcc3312', border: '1px solid #ffcc3344', color: '#ffcc33' }}
        >
          {t(
            'sca.unreachable',
            undefined,
            'Hub admission telemetry is unavailable. No audits, scores or decisions are shown — nothing here is carried over from an earlier poll.',
          )}
        </div>
      </div>
    );
  }

  const mode = modeTone(live.mode);
  const latest = live.latest;
  const recent = Array.isArray(live.recent) ? live.recent.slice(0, 8) : [];
  const latestDecision = latest?.decision ? String(latest.decision).toLowerCase() : null;
  const latestMetis = latest?.metis_status ? String(latest.metis_status).toLowerCase() : null;
  const score =
    typeof latest?.score === 'number' && Number.isFinite(latest.score) ? Math.round(latest.score) : null;

  return (
    <div className="mb-4" onClick={(e) => e.stopPropagation()}>
      <div
        className="mb-3 px-3 py-2 rounded text-[11px] font-mono"
        style={{ background: '#00000030', border: `1px solid ${themeColor}33` }}
      >
        <div className="text-white/70 mb-1">
          🛡{' '}
          {t(
            'sca.role',
            undefined,
            'Publish admission gate · before the public catalogue',
          )}
        </div>
        <div className="text-white/45">
          {t(
            'sca.split',
            undefined,
            'Auditor decides if an agent may be listed. WARDEN decides each invoke. Metis advises asynchronously. MOMUS takes review disputes.',
          )}
        </div>
        {live.simulated ? (
          <div className="text-white/35 mt-1">
            {t('sca.simulated', undefined, 'SIM telemetry · not a live Hub receipt')}
          </div>
        ) : null}
      </div>

      <div className="grid grid-cols-2 gap-1.5 mb-3">
        <div className="px-2 py-1.5 rounded bg-white/5 text-[11px] font-mono">
          <span className="text-white/40">{t('sca.mode', undefined, 'Mode')}:</span>{' '}
          <span style={{ color: mode.color }}>{t(mode.labelKey, undefined, mode.fallback)}</span>
        </div>
        <div className="px-2 py-1.5 rounded bg-white/5 text-[11px] font-mono">
          <span className="text-white/40">{t('sca.endpoint', undefined, 'Endpoint')}:</span>{' '}
          <span style={{ color: live.configured ? '#43e65a' : '#ff6b3d' }}>
            {live.configured
              ? t('sca.configured', undefined, 'configured')
              : t('sca.not_configured', undefined, 'not configured')}
          </span>
        </div>
      </div>

      <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-2">
        {t('sca.latest', undefined, 'Latest admission')}
      </div>

      {latestDecision ? (
        <div
          className="mb-3 px-3 py-2.5 rounded"
          style={{
            background: `linear-gradient(135deg, ${decisionColor(latestDecision)}14, #a855f722)`,
            border: `1px solid ${decisionColor(latestDecision)}55`,
            boxShadow:
              latestMetis === 'pending'
                ? '0 0 18px #a855f744'
                : `0 0 14px ${decisionColor(latestDecision)}22`,
          }}
        >
          <div className="flex flex-wrap items-center gap-1.5 mb-2">
            <span
              className="px-2 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider"
              style={{
                color: decisionColor(latestDecision),
                background: decisionColor(latestDecision) + '22',
                border: `1px solid ${decisionColor(latestDecision)}55`,
              }}
            >
              {latestDecision}
            </span>
            {score != null ? (
              <span className="text-[11px] font-mono" style={{ color: themeColor }}>
                {t('sca.score', undefined, 'score')} {score}
              </span>
            ) : null}
            {latest?.risk_tier ? (
              <span className="text-[10px] font-mono text-white/45">
                {t('sca.risk', undefined, 'risk')} · {latest.risk_tier}
              </span>
            ) : null}
          </div>
          <div className="text-[11px] font-mono text-white/70 break-all">
            {latest?.capability_id || live.capability_id || '—'}
          </div>
          <div className="mt-1.5 flex items-center gap-2 text-[10px] font-mono">
            <span className="text-white/40">{t('sca.metis', undefined, 'Metis')}:</span>
            <span
              className="px-1.5 py-0.5 rounded"
              style={{
                color: metisColor(latestMetis),
                background: metisColor(latestMetis) + '22',
                border: `1px solid ${metisColor(latestMetis)}44`,
                animation: latestMetis === 'pending' ? 'pulse 1.6s ease-in-out infinite' : undefined,
              }}
            >
              {latestMetis || '—'}
            </span>
            {latestMetis === 'completed' ? (
              <span style={{ color: '#00f0ff' }}>
                {t('sca.receipt_ready', undefined, 'signed receipt ready')}
              </span>
            ) : null}
          </div>
        </div>
      ) : (
        <div className="mb-3 text-[11px] font-mono text-white/40">
          {t('sca.no_latest', undefined, 'No admission receipt yet.')}
        </div>
      )}

      <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-2">
        {t('sca.recent', undefined, 'Recent audits')}
      </div>
      <div className="space-y-1 mb-3 max-h-48 overflow-y-auto">
        {recent.length > 0 ? (
          recent.map((row, i) => {
            const d = row.decision ? String(row.decision).toLowerCase() : null;
            const m = row.metis?.status ? String(row.metis.status).toLowerCase() : null;
            return (
              <div
                key={row.audit_id || `${row.capability_id}-${i}`}
                className="px-2 py-1.5 rounded bg-white/5 text-[11px]"
              >
                <div className="flex items-center gap-1.5 flex-wrap">
                  {d ? (
                    <span
                      className="px-1 rounded text-[9px] font-mono uppercase"
                      style={{
                        background: decisionColor(d) + '22',
                        color: decisionColor(d),
                        border: `1px solid ${decisionColor(d)}44`,
                      }}
                    >
                      {d}
                    </span>
                  ) : (
                    <span className="text-white/30 font-mono text-[9px]">—</span>
                  )}
                  <span className="text-white/55 font-mono text-[10px] truncate">
                    {row.capability_id || '—'}
                  </span>
                  {typeof row.score === 'number' ? (
                    <span className="text-white/35 font-mono text-[10px] ml-auto">
                      {Math.round(row.score)}
                    </span>
                  ) : null}
                </div>
                <div className="mt-0.5 flex items-center gap-2 text-[10px] font-mono text-white/40">
                  <span className="truncate">{row.publisher_id || '—'}</span>
                  {m ? (
                    <span style={{ color: metisColor(m) }}>
                      metis · {m}
                    </span>
                  ) : null}
                </div>
              </div>
            );
          })
        ) : (
          <div className="text-white/40 text-[11px] font-mono">
            {t('sca.no_recent', undefined, 'No recent audits reported.')}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        {node.links?.landing ? (
          <a
            href={node.links.landing}
            target="_blank"
            rel="noreferrer"
            className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
            style={{
              backgroundColor: themeColor + '1e',
              border: `1px solid ${themeColor}55`,
              color: themeColor,
            }}
          >
            {t('sca.open_landing', undefined, 'Open THEMIS landing')} ↗
          </a>
        ) : null}
        {node.links?.tutorial ? (
          <a
            href={node.links.tutorial}
            target="_blank"
            rel="noreferrer"
            className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
            style={{
              backgroundColor: '#66f7c518',
              border: '1px solid #66f7c544',
              color: '#66f7c5',
            }}
          >
            {t('sca.open_tutorial', undefined, 'Open THEMIS tutorial')} ↗
          </a>
        ) : null}
        {node.links?.github || node.url ? (
          <a
            href={node.links?.github || node.url}
            target="_blank"
            rel="noreferrer"
            className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
            style={{
              backgroundColor: '#a855f718',
              border: '1px solid #a855f744',
              color: '#c4b5fd',
            }}
          >
            {t('sca.open_repo', undefined, 'Open THEMIS repo')} ↗
          </a>
        ) : null}
      </div>
    </div>
  );
}
