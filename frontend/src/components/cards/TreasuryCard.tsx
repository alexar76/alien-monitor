import type { EcoNode, TreasuryTier } from '../../App';

interface Props {
  node: EcoNode;
  themeColor: string;
  mobile?: boolean;
  t: (key: string, vars?: Record<string, string | number>, defaultValue?: string) => string;
}

/* TREASURY — the separate payer. Ledger tail + the separation, from the other side. */
export default function TreasuryCard({ node, themeColor, t }: Props) {
        const tr = node.treasury_live!;
        const c = tr.counts || {};
        const tiers = tr.tiers || [];
        const healthOffline = tr.health_online === false;

        // Colour by STATE, never by value. A measured 0 is green like any other measurement;
        // orange means we could not reach the source; grey means nobody deployed the thing.
        const stateColor: Record<string, string> = {
          ok: '#43e65a', unreachable: '#ff6b3d', not_connected: '#7a8699',
        };
        const trim = (v: number, dp: number) => String(Number(v.toFixed(dp)));
        const clock = (iso?: string) => (iso && iso.length >= 19 ? `${iso.slice(11, 19)}Z` : '');

        // Figures for a tier — produced ONLY from values something actually measured. An
        // unreachable source and an undeployed chain both yield [], so their rows carry a reason
        // and no numbers: no stale value, no placeholder, no zero standing in for "never asked".
        const figures = (ti: TreasuryTier): [string, string][] => {
          if (ti.state !== 'ok') return [];
          const out: [string, string][] = [];
          const num = (v: unknown): v is number => typeof v === 'number';
          if (ti.tier === 'uni') {
            if (num(ti.balance_usd)) out.push([t('treasury.balance', undefined, 'balance'), `$${ti.balance_usd.toFixed(2)}`]);
            if (num(ti.reserved_usd)) out.push([t('treasury.reserved', undefined, 'reserved'), `$${ti.reserved_usd.toFixed(2)}`]);
            if (num(ti.available_usd)) out.push([t('treasury.available', undefined, 'available'), `$${ti.available_usd.toFixed(2)}`]);
            if (num(ti.transactions)) out.push([t('treasury.txs', undefined, 'transactions'), String(ti.transactions)]);
          } else if (ti.tier === 'base') {
            if (num(ti.eth)) out.push(['ETH', trim(ti.eth, 9)]);
            if (num(ti.usdc)) out.push(['USDC', trim(ti.usdc, 6)]);
          } else if (num(ti.sol)) {
            out.push(['SOL', trim(ti.sol, 9)]);
          }
          return out;
        };

        // The one-line provenance note under each row: where the figure came from, or why there
        // is none. Never silent — a row without a note is a number without a witness.
        const provenance = (ti: TreasuryTier): string => {
          if (ti.synthetic) return t('treasury.synthetic_note', undefined, 'TEST mode simulator — these figures are invented, nothing was measured');
          if (ti.state === 'unreachable') {
            const why = ti.detail || (ti.errors || [])[0] || '';
            return why ? `${t('treasury.src_unreachable', undefined, 'source not reached')} · ${why}` : t('treasury.src_unreachable', undefined, 'source not reached');
          }
          if (ti.state === 'not_connected') return t('treasury.solana_note', undefined, 'optional tier · no account deployed, so it was never queried — this is not a zero balance');
          if (ti.tier === 'uni') return t('treasury.uni_note', undefined, 'simulated settlement — no value moves · Treasury /vault over loopback');
          if (ti.tier === 'base') return `${t('treasury.base_note', undefined, 'Base mainnet · eth_getBalance + ERC-20 balanceOf on the BountySplitter')}${ti.deployed === true ? ` · ${t('treasury.deployed', undefined, 'contract deployed')}` : ''}`;
          return ti.source || '';
        };

        return (
          <div className="mb-4" onClick={(e) => e.stopPropagation()}>
            <div className="mb-3 px-3 py-2 rounded text-[11px] font-mono"
                 style={{ background: '#00000030', border: `1px solid ${themeColor}33` }}>
              <div className="text-white/70 mb-1">🏦 {t('treasury.role', undefined, 'The only key that can pay a bounty')}</div>
              {healthOffline ? (
                /* The public audit surface is down. It knows the pubkey and the counters, so we
                   show neither — a 0 here would claim the Treasury refused everything. */
                <div style={{ color: '#ff6b3d' }}>
                  {t('treasury.health_offline', undefined, 'audit surface offline — key and decision counters unavailable (the balance tiers below are read from their own sources)')}
                </div>
              ) : (
                <>
                  <div className="text-white/45 break-all">treasury {tr.treasury_pubkey || '—'}…</div>
                  <div className="text-white/50">{t('treasury.external', undefined, 'external verifiers')}: {tr.external_verifiers ?? 0} · {tr.crypto_enabled ? t('momus.crypto_on', undefined, 'crypto on') : t('momus.crypto_off', undefined, 'crypto off')}</div>
                </>
              )}
            </div>
            {tr.synthetic && (
              /* TEST mode says so in the panel itself, not only in a tooltip. */
              <div className="mb-2 px-2 py-1 rounded text-[10px] font-mono"
                   style={{ background: '#c07cff1e', border: '1px solid #c07cff55', color: '#c07cff' }}>
                {t('treasury.synthetic_card', undefined, '⚗ TEST mode — every figure below is synthetic, nothing was measured')}
              </div>
            )}
            {!healthOffline && (
              <div className="flex flex-wrap gap-1.5 mb-3">
                <span className="px-2 py-0.5 rounded text-[10px] font-mono" style={{ background: '#43e65a22', color: '#43e65a' }}>paid {c.paid || 0}</span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono" style={{ background: '#ffcc3322', color: '#ffcc33' }}>held {c.held || 0}</span>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono" style={{ background: '#ff6b3d22', color: '#ff6b3d' }}>refused {c.refused || 0}</span>
              </div>
            )}

            {/* BALANCE BY SETTLEMENT TIER — three sources, three truths, each degrading alone. */}
            {tiers.length > 0 && (
              <>
                <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-2">
                  {t('treasury.tiers_title', undefined, 'Balance by settlement tier')}
                </div>
                <div className="mb-3">
                  {tiers.map((ti) => {
                    const col = stateColor[ti.state] || '#7a8699';
                    const figs = figures(ti);
                    const stateText = ti.state === 'ok'
                      ? t('treasury.measured', undefined, 'measured')
                      : ti.state === 'not_connected'
                        ? t('treasury.not_connected', undefined, 'not connected')
                        : t('treasury.unreachable', undefined, 'unreachable');
                    // Every figure measured, and every one of them zero → say WHY that zero is the
                    // correct state, right next to it, or a reader files it as "broken". If any
                    // figure failed to read, the tier is NOT "zero" — it is partly unknown, and
                    // the partial-read line below carries that instead.
                    const zeroExplained = ti.tier === 'base' && ti.state === 'ok'
                      && ti.payout_optin_required === true && (ti.errors || []).length === 0
                      && figs.length > 0 && figs.every(([, v]) => Number(v) === 0);
                    return (
                      <div key={ti.tier} className="px-2 py-1.5 rounded bg-white/5 mb-1.5">
                        <div className="flex items-center gap-1.5 flex-wrap text-[10px] font-mono">
                          <span className="font-bold" style={{ color: col }}>{ti.label || ti.tier.toUpperCase()}</span>
                          <span className="px-1 rounded" style={{ background: col + '22', color: col }}>{stateText}</span>
                          {ti.simulated && (
                            <span className="px-1 rounded" style={{ background: '#ffcc3322', color: '#ffcc33' }}>
                              {t('treasury.simulated_tag', undefined, 'simulated')}
                            </span>
                          )}
                          {ti.synthetic && (
                            <span className="px-1 rounded" style={{ background: '#c07cff22', color: '#c07cff' }}>
                              {t('treasury.synthetic_tag', undefined, 'synthetic')}
                            </span>
                          )}
                          {/* A timestamp only where something happened at it: "read" when we got
                              figures, "tried" when we reached out and failed. A tier nobody
                              deployed gets none — "read 10:11:12Z" would claim we asked. */}
                          {ti.read_at && clock(ti.read_at) && ti.state !== 'not_connected' && (
                            <span className="text-white/30 ml-auto">
                              {ti.state === 'ok'
                                ? t('treasury.read_at', undefined, 'read')
                                : t('treasury.tried_at', undefined, 'tried')} {clock(ti.read_at)}
                            </span>
                          )}
                        </div>
                        {figs.length > 0 ? (
                          <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 text-[11px] font-mono">
                            {figs.map(([k, v]) => (
                              <span key={k} className="text-white/40">{k} <span className="text-white/85">{v}</span></span>
                            ))}
                          </div>
                        ) : (
                          <div className="mt-1 text-[11px] font-mono" style={{ color: col }}>
                            {ti.state === 'not_connected'
                              ? t('treasury.no_figures_never_asked', undefined, 'no figure — nothing deployed to query')
                              : t('treasury.no_figures', undefined, 'no figure — the source could not be reached')}
                          </div>
                        )}
                        {zeroExplained && (
                          <div className="mt-1 text-[10px] font-mono" style={{ color: '#ffcc33' }}>
                            {t('treasury.base_zero', undefined, 'zero is the correct state: on-chain payout needs a second opt-in (MOMUS_BOUNTY_ONCHAIN=1 plus a splitter address) — settlement runs on UNI today')}
                          </div>
                        )}
                        {ti.state === 'ok' && (ti.errors || []).length > 0 && (
                          <div className="mt-1 text-[10px] font-mono" style={{ color: '#ff6b3d' }}>
                            {t('treasury.partial', undefined, 'partial read')}: {(ti.errors || [])[0]}
                          </div>
                        )}
                        <div className="mt-1 text-[10px] font-mono text-white/35 break-words">{provenance(ti)}</div>
                        {/* Offered even when our own read failed: the contract address is known
                            statically, so the reader can go and check what we could not. */}
                        {ti.explorer && ti.state !== 'not_connected' && (
                          <a href={ti.explorer} target="_blank" rel="noreferrer"
                             className="mt-0.5 inline-block text-[10px] font-mono underline decoration-dotted underline-offset-2"
                             style={{ color: themeColor }}>
                            {t('treasury.explorer', undefined, 'verify on the block explorer')} ↗
                          </a>
                        )}
                      </div>
                    );
                  })}
                </div>
              </>
            )}
            {node.links?.github && (
              <a href={node.links.github} target="_blank" rel="noreferrer"
                 className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
                 style={{ backgroundColor: themeColor + '12', border: `1px solid ${themeColor}33`, color: themeColor }}>
                {t('nodeDetail.community.github')} ↗
              </a>
            )}
          </div>
        );
}

