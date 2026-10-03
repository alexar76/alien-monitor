import type { EcoNode } from '../../App';

interface Props {
  node: EcoNode;
  themeColor: string;
  mobile?: boolean;
  t: (key: string, vars?: Record<string, string | number>, defaultValue?: string) => string;
}

const EMBER = '#ff9a3c';

/** Hearth panel: who is hosted here. Empty roster ≠ empty market. */
export default function HestiaCard({ node, themeColor, t }: Props) {
  const live = node.hestia_live;
  if (!live) {
    return (
      <div className="mb-4" onClick={(e) => e.stopPropagation()}>
        <div
          className="px-3 py-2 rounded text-[11px] font-mono leading-relaxed"
          style={{ background: '#ff9a3c12', border: '1px solid #ff9a3c44', color: '#ff9a3c' }}
        >
          {t(
            'hearth.unreachable',
            undefined,
            'The hearth is not answering. No roster is shown — nothing here is carried over from an earlier poll. TLS may be live while the API is still undeployed.',
          )}
        </div>
      </div>
    );
  }

  const tenants = Array.isArray(live.tenants) ? live.tenants.slice(0, 8) : [];
  const notList = Array.isArray(live.not) ? live.not : [];

  return (
    <div className="mb-4" onClick={(e) => e.stopPropagation()}>
      <div
        className="mb-3 px-3 py-2 rounded text-[11px] font-mono"
        style={{ background: '#00000030', border: `1px solid ${themeColor}33` }}
      >
        <div className="text-white/70 mb-1">
          {t(
            'hearth.role',
            undefined,
            'Hearth · isolated hosted runtime for capability providers',
          )}
        </div>
        <div className="text-white/45">
          {t(
            'hearth.empty_is_not_the_market',
            undefined,
            'Agents appear only after an explicit signed deploy onto this host. An empty roster means nothing is hosted here — not that the market is empty. Hub stays the catalogue.',
          )}
        </div>
        {notList.length > 0 ? (
          <div className="text-white/35 mt-1">
            {t('hearth.split', undefined, 'Not')}: {notList.join(' · ')}
          </div>
        ) : null}
      </div>

      <div className="grid grid-cols-2 gap-1.5 mb-3">
        <div className="px-2 py-1.5 rounded bg-white/5 text-[11px] font-mono">
          <span className="text-white/40">{t('hearth.version', undefined, 'Version')}:</span>{' '}
          <span style={{ color: themeColor }}>{live.version || '—'}</span>
        </div>
        <div className="px-2 py-1.5 rounded bg-white/5 text-[11px] font-mono">
          <span className="text-white/40">{t('hearth.runtime', undefined, 'Runtime')}:</span>{' '}
          <span style={{ color: themeColor }}>{live.runtime || '—'}</span>
        </div>
      </div>

      <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-2">
        {t('hearth.roster', undefined, 'Hearth roster')}
      </div>
      <div className="space-y-1 mb-3 max-h-40 overflow-y-auto">
        {tenants.length > 0 ? (
          tenants.map((row, i) => (
            <div key={row.slug || i} className="px-2 py-1.5 rounded bg-white/5 text-[11px] font-mono">
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-white/60 truncate">{row.slug || '—'}</span>
                <span className="text-white/35 ml-auto">{row.status || '—'}</span>
              </div>
              <div className="mt-0.5 flex items-center gap-2 text-[10px] text-white/40">
                <span className="truncate">{row.capability_id || row.name || '—'}</span>
                {row.announced ? (
                  <span style={{ color: EMBER }}>{t('hearth.announced', undefined, 'announced')}</span>
                ) : (
                  <span>{t('hearth.not_listed', undefined, 'not a Hub listing')}</span>
                )}
              </div>
            </div>
          ))
        ) : (
          <div className="text-white/40 text-[11px] font-mono">
            {t(
              'hearth.no_tenants',
              undefined,
              'No tenants deployed on this hearth yet.',
            )}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        {node.links?.console ? (
          <a
            href={node.links.console}
            target="_blank"
            rel="noreferrer"
            className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
            style={{
              backgroundColor: themeColor + '1e',
              border: `1px solid ${themeColor}55`,
              color: themeColor,
            }}
          >
            {t('hearth.open_console', undefined, 'Open HESTIA console')} ↗
          </a>
        ) : null}
        {node.links?.pages || node.links?.landing || node.url ? (
          <a
            href={node.links?.pages || node.links?.landing || node.url}
            target="_blank"
            rel="noreferrer"
            className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
            style={{ backgroundColor: EMBER + '18', border: `1px solid ${EMBER}44`, color: EMBER }}
          >
            {t('hearth.open_landing', undefined, 'Open HESTIA landing')} ↗
          </a>
        ) : null}
        {node.links?.github ? (
          <a
            href={node.links.github}
            target="_blank"
            rel="noreferrer"
            className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
            style={{ backgroundColor: '#a855f718', border: '1px solid #a855f744', color: '#c4b5fd' }}
          >
            {t('hearth.open_repo', undefined, 'Open HESTIA repo')} ↗
          </a>
        ) : null}
      </div>
    </div>
  );
}
