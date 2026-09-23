import type { EcoNode } from '../../App';

/** Rich body for Signal Hunt — federation hunt under the 3D field slot. */
export default function SignalHuntCard({
  node,
  themeColor,
  t,
}: {
  node: EcoNode;
  themeColor: string;
  mobile?: boolean;
  t: (key: string, vars?: Record<string, string | number>, defaultValue?: string) => string;
}) {
  const m = node.metrics || {};
  const caps = m.capabilities;
  const peers = m.peers;
  const trust = m.trust_score;

  return (
    <div className="mb-4 space-y-3" onClick={(e) => e.stopPropagation()}>
      <div className="text-[10px] font-mono uppercase tracking-wider text-white/40">
        {t('nodeDetail.signalHunt.tagline', undefined, 'Federation emitted a signal')}
      </div>
      <p className="text-[11px] text-white/55 leading-relaxed">
        {t(
          'nodeDetail.signalHunt.blurb',
          undefined,
          'UNI capability-hunt game. Its Hub is Signal Hunt Hub (peer in the federation); this ball is the app.',
        )}
      </p>
      <div className="grid grid-cols-3 gap-2">
        {[
          { k: 'capabilities', v: caps, label: t('nodeDetail.metricKeys.capabilities', undefined, 'capabilities') },
          { k: 'peers', v: peers, label: t('nodeDetail.metricKeys.peers', undefined, 'peers') },
          {
            k: 'trust',
            v: trust != null ? Number(trust).toFixed(3) : '—',
            label: t('nodeDetail.metricKeys.trust_score', undefined, 'trust score'),
          },
        ].map((cell) => (
          <div
            key={cell.k}
            className="px-2 py-2 rounded"
            style={{
              backgroundColor: `${themeColor}0a`,
              border: `1px solid ${themeColor}28`,
            }}
          >
            <div className="font-mono font-bold text-sm" style={{ color: themeColor }}>
              {cell.v == null || cell.v === '' ? '—' : String(cell.v)}
            </div>
            <div className="text-[9px] font-mono text-white/40 mt-0.5">{cell.label}</div>
          </div>
        ))}
      </div>
      {node.url && (
        <a
          href={node.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs font-semibold"
          style={{ color: themeColor }}
        >
          {t('nodeDetail.signalHunt.open', undefined, 'Open Signal Hunt')} →
        </a>
      )}
    </div>
  );
}
