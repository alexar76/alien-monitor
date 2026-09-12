import type { EcoNode } from '../../App';

interface Props {
  node: EcoNode;
  themeColor: string;
  mobile?: boolean;
  t: (key: string, vars?: Record<string, string | number>, defaultValue?: string) => string;
}

const CRIMSON = '#e5484d';

/**
 * The DOLOS panel: what the LAST scan found, never a standing claim.
 *
 * DOLOS is a harness, not a daemon — it has no live verdict to poll. The monitor reads the
 * artifact the last run wrote, so this card shows that run's facts (which chain was forked, how
 * many invariants held vs broke) and says plainly when nothing has run yet. A red-team node that
 * implied a result it never produced would be worse than one that admits "not run".
 */
export default function DolosCard({ node, themeColor, t }: Props) {
  const scan = (node as unknown as { dolos_last_scan?: Record<string, unknown> }).dolos_last_scan;
  const ran = !!scan && !!scan.ran;
  const metrics = (node.metrics || {}) as Record<string, number>;
  const attacks = Number(metrics.attacks ?? 3);

  const chip = (label: string, value: string | number, color: string) => (
    <div
      className="px-2 py-1 rounded text-[10px] font-mono flex flex-col items-center min-w-[3.2rem]"
      style={{ background: color + '14', border: `1px solid ${color}44`, color }}
    >
      <span className="text-[13px] font-bold tabular-nums">{value}</span>
      <span className="text-white/50 uppercase tracking-wide">{label}</span>
    </div>
  );

  const real = Number((scan?.real_exploits as number) ?? 0);
  const verdictColor = !ran ? '#ffcc33' : real > 0 ? CRIMSON : '#00ff88';
  const verdictText = !ran
    ? t('dolos.notRun', undefined, 'No scan has run yet — showing DOLOS identity only.')
    : real > 0
      ? t('dolos.exploits', { n: real }, `${real} real exploit(s) found — the contracts did not hold.`)
      : t('dolos.allHeld', undefined, 'Every invariant held — the contracts refused the attacks.');

  return (
    <div className="mb-4" onClick={(e) => e.stopPropagation()}>
      {/* Verdict banner */}
      <div
        className="mb-3 px-3 py-2 rounded text-[11px] font-mono leading-relaxed"
        style={{ background: verdictColor + '12', border: `1px solid ${verdictColor}44`, color: verdictColor }}
      >
        {verdictText}
      </div>

      {/* Scan facts */}
      {ran && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {chip(t('dolos.attacks', undefined, 'attacks'), attacks, themeColor)}
          {chip(t('dolos.held', undefined, 'held'), Number(scan?.held ?? 0), '#00ff88')}
          {chip(t('dolos.exploited', undefined, 'exploited'), Number(scan?.exploited ?? 0), CRIMSON)}
          {chip(t('dolos.inconclusive', undefined, 'inconc.'), Number(scan?.inconclusive ?? 0), '#8899aa')}
        </div>
      )}

      {ran && (
        <div className="mb-3 px-3 py-2 rounded text-[10px] font-mono text-white/60"
             style={{ background: '#ffffff08', border: '1px solid #ffffff14' }}>
          <div>{t('dolos.chain', undefined, 'forked chain')}: <span className="text-white/80">{String(scan?.chain_id ?? '—')}</span>
            {' · '}{t('dolos.block', undefined, 'block')} #{String(scan?.fork_block ?? '—')}</div>
          <div>{t('dolos.sandbox', undefined, 'sandbox')}: <span style={{ color: scan?.sandbox ? '#00ff88' : '#ffcc33' }}>
            {scan?.sandbox ? t('dolos.yes', undefined, 'yes — auto-fix allowed') : t('dolos.no', undefined, 'no — advisory only')}</span></div>
          {typeof scan?.scanned_at === 'string' && scan.scanned_at && (
            <div className="text-white/40">{t('dolos.scannedAt', undefined, 'scanned')}: {scan.scanned_at}</div>
          )}
        </div>
      )}

      {/* Safety boundary — always shown; it is the whole reason this is safe */}
      <div className="mb-3 px-3 py-2 rounded text-[10px] font-mono leading-relaxed text-white/55"
           style={{ background: CRIMSON + '0c', border: `1px solid ${CRIMSON}33` }}>
        {t('dolos.safety', undefined,
          'Attacks run on a throwaway fork of the bubble’s Anvil — never the live chain, never a real one. Auto-fix-and-redeploy is allowed on the sandbox chain only; a mainnet finding is advisory only and stops at the report.')}
      </div>

      {/* Links */}
      <div className="flex flex-wrap gap-2 text-[10px] font-mono">
        {node.links?.github && (
          <a href={node.links.github} target="_blank" rel="noreferrer"
             className="px-2 py-1 rounded hover:underline"
             style={{ color: themeColor, border: `1px solid ${themeColor}44` }}>GitHub</a>
        )}
        {node.links?.pages && (
          <a href={node.links.pages} target="_blank" rel="noreferrer"
             className="px-2 py-1 rounded hover:underline"
             style={{ color: themeColor, border: `1px solid ${themeColor}44` }}>{t('dolos.landing', undefined, 'Landing')}</a>
        )}
      </div>
    </div>
  );
}
