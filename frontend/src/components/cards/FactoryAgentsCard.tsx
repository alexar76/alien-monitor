import { useMemo, useState } from 'react';
import type { EcoNode } from '../../App';

interface Props {
  node: EcoNode;
  themeColor: string;
  mobile?: boolean;
  t: (key: string, vars?: Record<string, string | number>, defaultValue?: string) => string;
}

type Row = NonNullable<NonNullable<EcoNode['factory_agents_live']>['agents']>[number];

const STATUS_COLOR: Record<string, string> = {
  live: '#3dd6c6',
  stale: '#e8b86d',
  offline: '#6b7280',
};

function money(usd: number): string {
  if (!usd) return '$0';
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

function age(seconds: number): string {
  if (!seconds || seconds < 60) return `${Math.max(0, Math.round(seconds))}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h`;
  return `${Math.round(seconds / 86400)}d`;
}

/* Factory Agents — roster of shipped agents with their economy counters. */
export default function FactoryAgentsCard({ node, themeColor, mobile, t }: Props) {
  const [q, setQ] = useState('');
  const live = node.factory_agents_live;
  const summary = live?.summary ?? {};

  const rows: Row[] = useMemo(() => {
    const all = live?.agents ?? [];
    const needle = q.trim().toLowerCase();
    const filtered = needle
      ? all.filter((a) =>
          [a.name, a.agent_id, a.sdk, a.product_id, ...(a.capabilities_used ?? [])]
            .join(' ')
            .toLowerCase()
            .includes(needle),
        )
      : all;
    return [...filtered].sort((a, b) => {
      const rank = (s: string) => (s === 'live' ? 0 : s === 'stale' ? 1 : 2);
      const byStatus = rank(a.status) - rank(b.status);
      if (byStatus !== 0) return byStatus;
      return (b.spend_usd_total ?? 0) - (a.spend_usd_total ?? 0);
    });
  }, [live?.agents, q]);

  const sdks = Object.entries(summary.sdks ?? {});

  return (
    <div className="mb-4" onClick={(e) => e.stopPropagation()}>
      <div
        className="mb-3 px-3 py-2 rounded text-[11px] font-mono flex flex-wrap items-center gap-x-3 gap-y-1"
        style={{ backgroundColor: themeColor + '10', border: `1px solid ${themeColor}30`, color: themeColor }}
      >
        <span style={{ color: STATUS_COLOR.live }}>
          {summary.agents_live ?? 0}/{summary.agents_total ?? 0}{' '}
          {t('agents.live', undefined, 'live')}
        </span>
        <span>
          {(summary.invokes_total ?? 0).toLocaleString()} {t('agents.invokes', undefined, 'invokes')}
        </span>
        <span style={{ color: '#e8b86d' }}>
          {money(summary.spend_usd_total ?? 0)} {t('agents.spent', undefined, 'spent')}
        </span>
        {live?.stale && (
          <span className="text-amber-300/80">{t('agents.stale', undefined, 'registry unreachable')}</span>
        )}
      </div>

      {sdks.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1">
          {sdks.map(([sdk, count]) => (
            <span
              key={sdk}
              className="px-2 py-0.5 rounded text-[10px] font-mono"
              style={{ backgroundColor: themeColor + '14', border: `1px solid ${themeColor}30`, color: themeColor }}
              title={t('agents.sdkTitle', undefined, 'SDK the agent integrates through')}
            >
              {sdk} · {count}
            </span>
          ))}
        </div>
      )}

      {(live?.agents?.length ?? 0) > 6 && (
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t('agents.search', undefined, 'Search agent, SDK, capability…')}
          className="w-full mb-2 px-2 py-1 rounded text-[11px] font-mono bg-black/40 outline-none"
          style={{ border: `1px solid ${themeColor}30`, color: themeColor }}
        />
      )}

      {rows.length === 0 ? (
        <div className="text-[11px] font-mono opacity-60">
          {live?.stale
            ? t('agents.unreachable', undefined, 'The agent registry did not answer — showing nothing rather than guessing.')
            : t('agents.empty', undefined, 'No factory-born agent has reported yet.')}
        </div>
      ) : (
        <div className={mobile ? 'space-y-2' : 'space-y-2 max-h-72 overflow-y-auto pr-1'}>
          {rows.map((a) => (
            <div
              key={a.agent_id}
              className="px-2 py-2 rounded"
              style={{ backgroundColor: '#00000040', border: `1px solid ${themeColor}22` }}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span
                    className="inline-block w-2 h-2 rounded-full shrink-0"
                    style={{ backgroundColor: STATUS_COLOR[a.status] ?? STATUS_COLOR.offline }}
                    aria-hidden="true"
                  />
                  <span className="text-[12px] font-mono truncate" style={{ color: themeColor }}>
                    {a.public_url ? (
                      <a href={a.public_url} target="_blank" rel="noopener noreferrer" className="hover:underline">
                        {a.name}
                      </a>
                    ) : (
                      a.name
                    )}
                  </span>
                  {!a.verified && (
                    <span className="text-[9px] font-mono px-1 rounded text-amber-300/90 border border-amber-300/30">
                      {t('agents.unverified', undefined, 'unverified')}
                    </span>
                  )}
                </div>
                <span className="text-[10px] font-mono opacity-60 shrink-0">
                  {a.status} · {age(a.age_sec ?? 0)}
                </span>
              </div>

              <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] font-mono opacity-80">
                {a.sdk && <span>SDK {a.sdk}</span>}
                <span>{(a.invokes_total ?? 0).toLocaleString()} inv</span>
                <span style={{ color: '#e8b86d' }}>{money(a.spend_usd_total ?? 0)}</span>
                {(a.errors_24h ?? 0) > 0 && (
                  <span style={{ color: '#ff6b4a' }}>{a.errors_24h} err/24h</span>
                )}
              </div>

              {(a.capabilities_used?.length ?? 0) > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {a.capabilities_used!.map((cap) => (
                    <span
                      key={cap}
                      className="px-1.5 py-0.5 rounded text-[9px] font-mono opacity-80"
                      style={{ border: `1px solid ${themeColor}25` }}
                    >
                      {cap}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
