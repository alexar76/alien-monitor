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

/* ATLAS — sensor map: stations + mini embed + full map CTA. */
export default function AtlasCard({ node, themeColor, mobile, t, sensorQ, setSensorQ }: Props) {
  const atlasStations = useMemo(() => {
    const stations = node.atlas_live?.stations;
    if (!Array.isArray(stations)) return [];
    return [...stations]
      .filter((s) =>
        sensorMatchesQuery(
          sensorSearchHaystack(
            s.id,
            s.layer,
            s.label,
            s.place,
            s.headline,
            s.source,
            s.mode,
            s.live ? 'live' : 'sim',
            s.online ? 'online' : 'offline',
          ),
          sensorQ,
        ),
      )
      .sort((a, b) => Number(!!b.live) - Number(!!a.live));
  }, [node.atlas_live?.stations, sensorQ]);

  return (
        <div className="mb-4" onClick={(e) => e.stopPropagation()}>
          {node.atlas_live && (() => {
            const live = node.atlas_live!.live ?? 0;
            const sim = node.atlas_live!.sim ?? 0;
            return (
            <div
              className="mb-3 px-3 py-2 rounded text-[11px] font-mono flex flex-wrap items-center gap-x-3 gap-y-1"
              style={{ backgroundColor: themeColor + '10', border: `1px solid ${themeColor}30`, color: themeColor }}
            >
              <span style={{ color: '#3dd6c6' }}>
                {(node.atlas_live.online ?? 0)}/{(node.atlas_live.station_count ?? 0)}{' '}
                {t('atlas.stations', undefined, 'stations')}
              </span>
              {live > 0 && (
                <span style={{ color: '#3dd6c6' }}>🌍 {live} {t('atlas.n_live', undefined, 'LIVE')}</span>
              )}
              {sim > 0 && (
                <span style={{ color: '#e8b86d' }}>⚙ {sim} {t('atlas.n_sim', undefined, 'SIM')}</span>
              )}
              <span style={{ color: '#ff6b4a' }}>
                {node.atlas_live.quake_count ?? 0} {t('atlas.quakes', undefined, 'quakes')}
              </span>
              {node.atlas_live.stale && (
                <span className="text-amber-300/80">{t('atlas.stale', undefined, 'stale')}</span>
              )}
            </div>
            );
          })()}
          {/* The mini map moved to the slot under the title — see cards/NodeVisual.tsx. */}
          {Array.isArray(node.atlas_live?.stations) && node.atlas_live!.stations!.length > 0 && (
            <>
              <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-2">
                {t('atlas.sensors', undefined, 'Sensors')}{' '}
                ({sensorQ.trim() ? `${atlasStations.length}/${node.atlas_live!.stations!.length}` : node.atlas_live!.stations!.length})
              </div>
              <input
                type="search"
                value={sensorQ}
                onChange={(e) => setSensorQ(e.target.value)}
                placeholder={t('atlas.search', undefined, 'Search id, layer, place…')}
                aria-label={t('atlas.search', undefined, 'Search id, layer, place…')}
                className="w-full mb-2 rounded-lg px-2.5 py-1.5 text-[11px] font-mono bg-black/40 text-white/85 outline-none"
                style={{ border: `1px solid ${themeColor}33` }}
              />
              <div className="space-y-1.5 max-h-48 overflow-auto pr-1">
                {atlasStations.length === 0 && (
                  <div className="px-2.5 py-2 text-[10px] font-mono text-white/35">
                    {t('atlas.search_empty', undefined, 'No sensors match.')}
                  </div>
                )}
                {atlasStations.map((s) => {
                  const isLive = !!s.live;
                  return (
                  <div
                    key={s.id}
                    className="px-2.5 py-1.5 rounded flex items-center justify-between gap-2"
                    style={{ backgroundColor: themeColor + '0d', border: `1px solid ${themeColor}22` }}
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span
                          className="shrink-0 text-[9px] font-mono px-1 py-0.5 rounded"
                          style={isLive
                            ? { backgroundColor: '#3dd6c626', color: '#3dd6c6', border: '1px solid #3dd6c666' }
                            : { backgroundColor: '#e8b86d22', color: '#e8b86d', border: '1px solid #e8b86d44' }}
                        >
                          {isLive
                            ? t('atlas.kind_live', undefined, '🌍 LIVE')
                            : t('atlas.kind_sim', undefined, '⚙ SIM')}
                        </span>
                        <div className="text-[11px] font-mono font-semibold truncate" style={{ color: themeColor }}>
                          {s.id}
                        </div>
                      </div>
                      <div className="text-[9px] font-mono text-white/40 truncate">
                        {s.layer || ''}{s.place ? ` · ${s.place}` : ''}
                      </div>
                    </div>
                    <div className="text-[11px] font-mono whitespace-nowrap" style={{ color: s.online ? '#3dd6c6' : '#888' }}>
                      {s.headline || '—'}
                    </div>
                  </div>
                  );
                })}
              </div>
            </>
          )}
          <div className="mt-3 space-y-1.5">
            {(node.atlas_live?.map_url || node.links?.landing) && (
              <a
                href={node.atlas_live?.map_url || node.links?.landing}
                target="_blank"
                rel="noreferrer"
                className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
                style={{ backgroundColor: '#3dd6c61e', border: '1px solid #3dd6c655', color: '#3dd6c6' }}
              >
                {t('atlas.full_map', undefined, '🗺 Open full ATLAS map')} ↗
              </a>
            )}
            {node.links?.github && (
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
        </div>
  );
}

