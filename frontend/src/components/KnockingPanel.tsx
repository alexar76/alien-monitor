import type { EcoNode } from '../App';
import { useI18n } from '../i18n';
import { pendingHubsFrom } from '../lib/pendingHubs';

interface Props {
  nodes: EcoNode[] | undefined;
  live: boolean;
  themeColor: string;
  onClose: () => void;
  onFocus: (node: EcoNode) => void;
  mobile?: boolean;
}

function claimed(node: EcoNode): number {
  return Number(node.metrics?.preview_capabilities ?? node.metrics?.capabilities ?? 0) || 0;
}

export default function KnockingPanel({
  nodes,
  live,
  themeColor,
  onClose,
  onFocus,
  mobile = false,
}: Props) {
  const { t } = useI18n();
  const pending = pendingHubsFrom(nodes);
  const amber = '#ffcc4d';

  return (
    <>
      {mobile && (
        <button type="button" className="mobile-backdrop" aria-label={t('mobile.closeSheet')} onClick={onClose} />
      )}
      <div
        className={`z-40 glass-panel flex flex-col animate-slide-up min-h-0 ${
          mobile
            ? 'fixed inset-x-2 top-[max(0.5rem,var(--safe-top))] bottom-[var(--mobile-dock-clearance)] rounded-2xl'
            : 'absolute right-4 top-32 w-96 max-h-[calc(100vh-220px)]'
        }`}
        style={{
          borderColor: amber + '66',
          backgroundColor: 'rgba(8, 10, 18, 0.97)',
          boxShadow: `0 0 30px rgba(0,0,0,0.6), 0 0 15px ${amber}22`,
        }}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: amber + '33' }}>
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-sm" style={{ color: amber }} aria-hidden>
              ⌁
            </span>
            <span className="text-xs font-semibold tracking-wider truncate" style={{ color: amber }}>
              {t('knocking.title')}
            </span>
            {live && pending.length > 0 && (
              <span
                className="text-[9px] font-mono px-1.5 py-0.5 rounded uppercase tracking-wider"
                style={{ color: amber, backgroundColor: amber + '1a', border: `1px solid ${amber}40` }}
              >
                {t('knocking.badge', { n: pending.length })}
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-white/40 hover:text-white/80 transition-colors text-2xl leading-none w-10 h-10 flex items-center justify-center shrink-0"
            aria-label={t('mobile.closeSheet')}
          >
            ×
          </button>
        </div>

        <p className="px-4 py-2 text-[10px] font-mono text-white/40 border-b" style={{ borderColor: amber + '18' }}>
          {live ? t('knocking.note') : t('knocking.uni')}
        </p>

        <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2 min-h-0">
          {!live ? (
            <div className="px-2 py-8 text-center text-[11px] font-mono text-white/40">{t('knocking.uni')}</div>
          ) : pending.length === 0 ? (
            <div className="px-2 py-8 text-center text-[11px] font-mono text-white/40">{t('knocking.empty')}</div>
          ) : (
            pending.map((node) => (
              <article
                key={node.id}
                className="rounded-lg border px-3 py-2.5"
                style={{ borderColor: amber + '44', background: 'rgba(245,165,36,0.05)' }}
              >
                <h3 className="text-[12px] font-semibold truncate" style={{ color: amber }} title={node.label}>
                  {node.label}
                </h3>
                {node.url && (
                  <div className="mt-0.5 break-all font-mono text-[10px] text-cyan-200/80">{node.url}</div>
                )}
                <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[9px] text-white/45">
                  {node.detail?.first_seen && (
                    <span>{t('knocking.firstSeen', { when: node.detail.first_seen.replace('T', ' ').replace(/Z$/, ' UTC') })}</span>
                  )}
                  {node.detail?.discoverer && <span>{t('knocking.via', { who: node.detail.discoverer })}</span>}
                  <span>{t('knocking.claimed', { n: claimed(node) })}</span>
                </div>
                {node.detail?.note && (
                  <p className="mt-1.5 text-[10px] leading-snug text-white/50">{node.detail.note}</p>
                )}
                <button
                  type="button"
                  className="mt-2 rounded-md border px-2 py-1 text-[10px] font-mono uppercase tracking-wider"
                  style={{ borderColor: amber + '66', color: amber }}
                  onClick={() => onFocus(node)}
                >
                  {t('knocking.focus')}
                </button>
              </article>
            ))
          )}
        </div>

        <div className="px-4 py-2 text-[9px] font-mono text-white/30 border-t" style={{ borderColor: themeColor + '18' }}>
          {t('knocking.hint')}
        </div>
      </div>
    </>
  );
}
