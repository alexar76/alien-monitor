import type { EcoNode } from '../../App';

interface Props {
  node: EcoNode;
  themeColor: string;
  mobile?: boolean;
  t: (key: string, vars?: Record<string, string | number>, defaultValue?: string) => string;
}

const GOLD = '#ffd58a';

function fmt(ts?: string | null): string {
  return ts ? ts.replace('T', ' ').replace('Z', '').slice(0, 16) : '—';
}

function n(v?: number | null): string {
  return v == null ? '—' : v.toLocaleString();
}

/** MCP transparency log panel. Every number keeps the window HISTOR publishes it under. */
export default function HistorCard({ node, themeColor, t }: Props) {
  const live = node.histor_live;
  // An interrupted or failed run is shown as one, not as "last finished" (the runs table remembers it).
  const failure = live ? live.last_run_error || live.last_crawl_error || null : null;
  if (!live) {
    return (
      <div className="mb-4" onClick={(e) => e.stopPropagation()}>
        <div
          className="px-3 py-2 rounded text-[11px] font-mono leading-relaxed"
          style={{ background: `${GOLD}12`, border: `1px solid ${GOLD}44`, color: GOLD }}
        >
          {t('histor.unreachable', undefined, 'The log is not answering. Nothing shown here is carried over from an earlier poll.')}
        </div>
      </div>
    );
  }
  const rows: [string, string][] = [
    [t('histor.labels', undefined, 'Labels in the log (all time)'), n(live.tree_size)],
    [t('histor.pinned', undefined, 'Tool sets pinned (now)'), n(live.pinned)],
    [t('histor.changes7', undefined, 'Changes (7 days)'), n(live.changes?.last7d)],
    [t('histor.changes30', undefined, 'Changes (30 days)'), n(live.changes?.last30d)],
    [t('histor.endpoints', undefined, 'Registry endpoints (last crawl)'), n(live.registry_endpoints)],
    [t('histor.answered', undefined, 'Answered tools/list (last crawl)'), n(live.answered_ok)],
    [t('histor.auth', undefined, 'Behind a login (last crawl)'), n(live.auth_required)],
    [t('histor.block', undefined, 'With block-tier matches (now)'), n(live.block_tier)],
  ];
  return (
    <div className="mb-4" onClick={(e) => e.stopPropagation()}>
      <div className="mb-3 px-3 py-2 rounded text-[11px] font-mono" style={{ background: '#00000030', border: `1px solid ${themeColor}33` }}>
        <div className="text-white/70 mb-1">
          {t('histor.role', undefined, 'Transparency log · what MCP servers advertised, and when it changed')}
        </div>
        <div className="text-white/45">
          {t('histor.scope', undefined, 'Advertised text only — no source read, no tool called. A change is a date and a diff, not an accusation. Never a safety rating.')}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-1.5 mb-3">
        {rows.map(([k, v]) => (
          <div key={k} className="px-2 py-1.5 rounded bg-white/5 text-[11px] font-mono">
            <div className="text-white/40">{k}</div>
            <div style={{ color: themeColor }}>{v}</div>
          </div>
        ))}
      </div>
      <div className="px-2 py-1.5 rounded bg-white/5 text-[11px] font-mono mb-2">
        <span className="text-white/40">{t('histor.sth', undefined, 'Signed tree head')}:</span>{' '}
        <span style={{ color: GOLD }}>{live.root_hash ? `${live.root_hash}…` : '—'}</span>{' '}
        <span className="text-white/40">· {fmt(live.sth_at)} UTC</span>
      </div>
      <div className="px-2 py-1.5 rounded bg-white/5 text-[11px] font-mono">
        <span className="text-white/40">{t('histor.crawl', undefined, 'Crawl')}:</span>{' '}
        <span style={{ color: !live.crawl_running && failure ? '#ff9d8f' : themeColor }}>
          {live.crawl_running
            ? t('histor.crawling', undefined, 'running now')
            : failure
              ? `${t('histor.failed', undefined, 'last crawl failed')} ${fmt(live.last_run_finished)} UTC: ${failure}`
              : `${t('histor.finished', undefined, 'last finished')} ${fmt(live.last_run_finished)} UTC`}
        </span>
      </div>
    </div>
  );
}
