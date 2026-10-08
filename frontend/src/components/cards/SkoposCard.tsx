import type { EcoNode } from '../../App';

interface Props {
  node: EcoNode;
  themeColor: string;
  mobile?: boolean;
  t: (key: string, vars?: Record<string, string | number>, defaultValue?: string) => string;
}

/* SKOPOS — dashboard + docs links (public status in metrics). */
export default function SkoposCard({ node, themeColor, t }: Props) {
  const links = node.links;
  if (!links || !Object.keys(links).length) return null;
  return (
        <div className="mb-4" onClick={(e) => e.stopPropagation()}>
          <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-2">
            {t('nodeDetail.links', undefined, 'Links')}
          </div>
          <div className="space-y-1.5">
            {links.dashboard && (
              <a
                href={links.dashboard}
                target="_blank"
                rel="noreferrer"
                className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
                style={{ backgroundColor: themeColor + '1e', border: `1px solid ${themeColor}55`, color: themeColor }}
              >
                {t('skopos.dashboard', undefined, '🛰️ Open SKOPOS dashboard')} ↗
              </a>
            )}
            {links.github && (
              <a
                href={links.github}
                target="_blank"
                rel="noreferrer"
                className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
                style={{ backgroundColor: themeColor + '12', border: `1px solid ${themeColor}33`, color: themeColor }}
              >
                {t('nodeDetail.community.github')} ↗
              </a>
            )}
            {links.docs && (
              <a
                href={links.docs}
                target="_blank"
                rel="noreferrer"
                className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
                style={{ backgroundColor: themeColor + '12', border: `1px solid ${themeColor}33`, color: themeColor }}
              >
                {t('skopos.docs', undefined, 'Documentation')} ↗
              </a>
            )}
            {links.integration && (
              <a
                href={links.integration}
                target="_blank"
                rel="noreferrer"
                className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
                style={{ backgroundColor: themeColor + '12', border: `1px solid ${themeColor}33`, color: themeColor }}
              >
                {t('skopos.integration', undefined, 'Ecosystem integration')} ↗
              </a>
            )}
          </div>
          {node.skopos_live && (
            <div className="mt-3 text-[11px] font-mono text-white/45 space-y-1">
              {node.skopos_live.database && (
                <div>{t('skopos.db', undefined, 'Database')}: {String(node.skopos_live.database)}</div>
              )}
              {Array.isArray(node.skopos_live.log_parsers) && node.skopos_live.log_parsers.length > 0 && (
                <div>{t('skopos.parsers', undefined, 'Log parsers')}: {node.skopos_live.log_parsers.join(', ')}</div>
              )}
            </div>
          )}
        </div>
  );
}

