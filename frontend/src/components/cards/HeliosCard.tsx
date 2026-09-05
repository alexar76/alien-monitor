import type { EcoNode } from '../../App';

interface Props {
  node: EcoNode;
  themeColor: string;
  mobile?: boolean;
  t: (key: string, vars?: Record<string, string | number>, defaultValue?: string) => string;
}

/* HELIOS YouTube channel link */
export default function HeliosCard({ node, themeColor, t }: Props) {
  return (
        <div className="mb-4" onClick={(e) => e.stopPropagation()}>
          <a
            href={node.youtube_url}
            target="_blank"
            rel="noreferrer"
            className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
            style={{ backgroundColor: themeColor + '12', border: `1px solid ${themeColor}33`, color: themeColor }}
          >
            YouTube channel ↗
          </a>
          {node.helios_live?.cached_at && (
            <div className="text-[9px] font-mono text-white/30 mt-1">
              stats cached {node.helios_live.cached_at}
              {node.helios_live.stale ? ' (stale)' : ''}
            </div>
          )}
        </div>
  );
}

