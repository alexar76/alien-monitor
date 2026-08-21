import { useMemo } from 'react';
import type { EcoNode } from '../../App';
import { sensorMatchesQuery, sensorSearchHaystack } from '../../lib/sensorSearch';

interface Props {
  node: EcoNode;
  themeColor: string;
  mobile?: boolean;
  t: (key: string, vars?: Record<string, string | number>, defaultValue?: string) => string;
  sensorQ: string;
  setSensorQ: (q: string) => void;
}

/* GAIA — physical-oracle device fleet: click-through device list + what each transmits. */
export default function GaiaCard({ node, themeColor, mobile, t, sensorQ, setSensorQ }: Props) {
  const gaiaDevices = useMemo(() => {
    const devices = node.gaia_live?.devices;
    if (!Array.isArray(devices)) return [];
    return [...devices]
      .filter((d) =>
        sensorMatchesQuery(
          sensorSearchHaystack(
            d.id,
            d.model,
            d.site,
            d.source,
            d.fault,
            d.live ? 'live' : 'sim',
            d.online ? 'online' : 'offline',
            ...(d.fields || []).map((f) => `${f.name} ${f.unit || ''}`),
          ),
          sensorQ,
        ),
      )
      .sort((a, b) => (b.live ? 1 : 0) - (a.live ? 1 : 0));
  }, [node.gaia_live?.devices, sensorQ]);

  return (
        <div className="mb-4" onClick={(e) => e.stopPropagation()}>
          {node.gaia_live && (() => {
            const total = node.gaia_live!.device_count ?? (node.gaia_live!.devices?.length || 0);
            const live = node.gaia_live!.live_relays ?? 0;
            const sim = Math.max(0, total - live);
            return (
              <div
                className="mb-3 px-3 py-2 rounded text-[11px] font-mono flex flex-wrap items-center gap-x-3 gap-y-1"
                style={{ backgroundColor: themeColor + '10', border: `1px solid ${themeColor}30`, color: themeColor }}
              >
                {live > 0 && (
                  <span style={{ color: '#43e65a' }}>🌍 {live} {t('gaia.n_live', undefined, 'live')} · {t('gaia.real_apis', undefined, 'real public-API sensors')}</span>
                )}
                {sim > 0 && (
                  <span className="text-white/45">⚙ {sim} {t('gaia.n_sim', undefined, 'simulated (deterministic)')}</span>
                )}
              </div>
            );
          })()}
          {Array.isArray(node.gaia_live?.devices) && node.gaia_live!.devices!.length > 0 && (
            <>
              <div className="flex items-center justify-between gap-2 mb-2">
                <div className="text-[10px] font-mono uppercase tracking-wider text-white/40">
                  {t('gaia.devices', undefined, 'Devices')}{' '}
                  {(() => {
                    const shown = node.gaia_live!.devices_shown ?? node.gaia_live!.devices!.length;
                    const total = node.gaia_live!.devices_total ?? node.gaia_live!.device_count ?? shown;
                    if (sensorQ.trim()) {
                      return `(${gaiaDevices.length}/${shown}${total > shown ? ` of ${total}` : ''})`;
                    }
                    return total > shown ? `(${shown} of ${total})` : `(${shown})`;
                  })()}
                </div>
              </div>
              <input
                type="search"
                value={sensorQ}
                onChange={(e) => setSensorQ(e.target.value)}
                placeholder={t('gaia.search', undefined, 'Search id, site, model, field…')}
                aria-label={t('gaia.search', undefined, 'Search id, site, model, field…')}
                className="w-full mb-2 rounded-lg px-2.5 py-1.5 text-[11px] font-mono bg-black/40 text-white/85 outline-none"
                style={{ border: `1px solid ${themeColor}33` }}
              />
              <div className="space-y-2 max-h-64 overflow-auto pr-1">
                {gaiaDevices.length === 0 && (
                  <div className="px-3 py-2 text-[10px] font-mono text-white/35">
                    {t('gaia.search_empty', undefined, 'No devices match.')}
                  </div>
                )}
                {gaiaDevices.map((d) => {
                  const faulted = !!d.fault && d.fault !== 'none';
                  const statusBg = faulted ? '#ff333322' : d.online ? '#43e65a22' : '#88888822';
                  const statusFg = faulted ? '#ff6666' : d.online ? '#43e65a' : '#aaaaaa';
                  const accent = d.live ? '#43e65a' : '#8a8a8a';
                  return (
                    <div
                      key={d.id}
                      className="px-3 py-2 rounded"
                      style={{ backgroundColor: themeColor + '0d', border: `1px solid ${themeColor}22`, borderLeft: `3px solid ${accent}` }}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-mono font-semibold" style={{ color: themeColor }}>{d.id}</span>
                        <span className="flex items-center gap-1 whitespace-nowrap">
                          <span
                            className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded"
                            style={d.live
                              ? { backgroundColor: '#43e65a26', color: '#43e65a', border: '1px solid #43e65a66' }
                              : { backgroundColor: '#8a8a8a22', color: '#b4b4b4', border: '1px solid #8a8a8a44' }}
                          >
                            {d.live ? t('gaia.kind_live', undefined, '🌍 LIVE') : t('gaia.kind_sim', undefined, '⚙ SIM')}
                          </span>
                          <span
                            className="text-[9px] font-mono px-1.5 py-0.5 rounded"
                            style={{ backgroundColor: statusBg, color: statusFg }}
                          >
                            {faulted
                              ? d.fault
                              : d.online
                                ? t('gaia.online', undefined, 'online')
                                : t('gaia.offline', undefined, 'offline')}
                          </span>
                        </span>
                      </div>
                      {d.model && <div className="text-[10px] font-mono text-white/45 mt-0.5">{d.model}</div>}
                      <div className="text-[10px] font-mono text-white/35 mt-1">
                        {d.site ? `${d.site} · ` : ''}{t('gaia.transmits', undefined, 'transmits')}:
                      </div>
                      {Array.isArray(d.fields) && d.fields.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {d.fields.map((f) => (
                            <span
                              key={f.name}
                              className="text-[9px] font-mono px-1.5 py-0.5 rounded"
                              style={{ backgroundColor: themeColor + '14', color: themeColor }}
                            >
                              {f.name}{f.unit ? ` (${f.unit})` : ''}
                            </span>
                          ))}
                        </div>
                      )}
                      {d.live && d.source && (
                        <div className="text-[9px] font-mono mt-1" style={{ color: '#43e65a', opacity: 0.75 }}>
                          {t('gaia.live_source', undefined, 'live source')} → {d.source}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}
          {node.links && Object.keys(node.links).length > 0 && (
            <div className="mt-3 space-y-1.5">
              {node.links.landing && (
                <a
                  href={node.links.landing}
                  target="_blank"
                  rel="noreferrer"
                  className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
                  style={{ backgroundColor: themeColor + '1e', border: `1px solid ${themeColor}55`, color: themeColor }}
                >
                  {t('gaia.landing', undefined, '🌍 Open GAIA gateway')} ↗
                </a>
              )}
              {node.links.github && (
                <a
                  href={node.links.github}
                  target="_blank"
                  rel="noreferrer"
                  className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
                  style={{ backgroundColor: themeColor + '12', border: `1px solid ${themeColor}33`, color: themeColor }}
                >
                  {t('nodeDetail.community.github')} ↗
                </a>
              )}
            </div>
          )}
        </div>
  );
}

