import type { EcoNode } from '../../App';
import MetisChat from '../MetisChat';

interface Props {
  node: EcoNode;
  themeColor: string;
  mobile?: boolean;
  t: (key: string, vars?: Record<string, string | number>, defaultValue?: string) => string;
}

/* METIS — live chat with the cognitive layer + repo/docs links.
   The 3D star sits in the visual slot under the title (cards/NodeVisual.tsx). */
export default function MetisCard({ node, themeColor, mobile, t }: Props) {
  return (
        <>
          {/* The star moved to the slot under the title — see cards/NodeVisual.tsx. */}
          <MetisChat themeColor={themeColor} status={node.status} />
          {node.links && Object.keys(node.links).length > 0 && (
            <div className="mb-4" onClick={(e) => e.stopPropagation()}>
              <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-2">
                {t('nodeDetail.links', undefined, 'Links')}
              </div>
              <div className="space-y-1.5">
                {node.links.landing && (
                  <a
                    href={node.links.landing}
                    target="_blank"
                    rel="noreferrer"
                    className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
                    style={{ backgroundColor: themeColor + '1e', border: `1px solid ${themeColor}55`, color: themeColor }}
                  >
                    {t('metis.landing', undefined, '🌌 Interactive 3D + live cognition')} ↗
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
                {node.links.docs && (
                  <a
                    href={node.links.docs}
                    target="_blank"
                    rel="noreferrer"
                    className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
                    style={{ backgroundColor: themeColor + '12', border: `1px solid ${themeColor}33`, color: themeColor }}
                  >
                    {t('metis.docs', undefined, 'Documentation')} ↗
                  </a>
                )}
              </div>
            </div>
          )}
        </>
  );
}

