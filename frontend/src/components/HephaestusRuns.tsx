import { useEffect } from 'react';
import { motion } from 'framer-motion';
import type { EcoNode } from '../App';
import { useI18n } from '../i18n';

/**
 * HEPHAESTUS panel — what actually ran, and what could run at all.
 *
 * Deliberately an observation panel, not the editor. The monitor's job is to show the
 * ecosystem as it is; the forge itself is a page of its own. So this shows real signed
 * runs — cost, hops, and the named at-fault hop when one failed — plus how much of the
 * catalogue is composable, which a list of rows hides and a count does not.
 *
 * Nothing here is scripted. With no runs it says so, because a fabricated feed on an
 * observation surface is worse than an empty one.
 */

interface BlameView {
  policy?: string;
  at_fault?: { id?: string; product_id?: string; capability_id?: string; status_code?: number };
  not_at_fault?: string[];
  not_executed?: string[];
}

interface StepView {
  id?: string;
  product_id?: string;
  capability_id?: string;
  status_code?: number;
  success?: boolean;
  price_usd?: number | null;
}

interface TraceView {
  trace_id: string;
  completed_at?: number | null;
  duration_ms?: number | null;
  total_usd?: number | null;
  hops?: number;
  failed?: boolean;
  signed?: boolean;
  trace_path?: string;
  steps?: StepView[];
  blame?: BlameView | null;
}

export interface HephaestusLive {
  studio_url?: string;
  traces?: TraceView[];
  totals?: { runs?: number; spend_usd?: number; hops?: number; failed?: number };
  catalogue?: {
    capabilities?: number;
    priced?: number;
    composable?: number;
    measured?: number;
    hubs?: number;
    generated_at?: string;
    signed?: boolean;
  };
}

interface Props {
  node: EcoNode;
  themeColor: string;
  onClose: () => void;
  mobile?: boolean;
}

const money = (usd: number | null | undefined): string => {
  if (typeof usd !== 'number' || !Number.isFinite(usd)) return '—';
  return `$${usd.toFixed(usd < 0.01 ? 4 : 2)}`;
};

const ago = (completedAt: number | null | undefined): string => {
  if (typeof completedAt !== 'number' || !Number.isFinite(completedAt)) return '';
  const seconds = Math.max(0, Math.round(Date.now() / 1000 - completedAt));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
};

export default function HephaestusRuns({ node, themeColor, onClose, mobile = false }: Props) {
  const { t } = useI18n();
  const live = (node as unknown as { hephaestus_live?: HephaestusLive }).hephaestus_live;
  const traces = live?.traces ?? [];
  const totals = live?.totals ?? {};
  const catalogue = live?.catalogue ?? {};
  const studioUrl = live?.studio_url || node.url;
  const offline = node.status === 'offline' || node.status === 'error';

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [onClose]);

  const capabilities = catalogue.capabilities ?? 0;
  const composable = catalogue.composable ?? 0;
  const measured = catalogue.measured ?? 0;

  return (
    <>
      {mobile && (
        <button type="button" className="mobile-backdrop" aria-label={t('mobile.closeSheet')} onClick={onClose} />
      )}
      <div
        className={`z-40 glass-panel p-4 md:p-5 animate-slide-in ${
          mobile
            ? 'fixed inset-x-0 mobile-sheet flex flex-col overflow-hidden'
            : 'absolute left-4 top-24 w-[24rem] max-w-[calc(100vw-2rem)] max-h-[calc(100vh-8rem)] overflow-y-auto'
        }`}
        style={{
          borderColor: themeColor + '55',
          boxShadow: `0 0 30px rgba(0,0,0,0.5), 0 0 18px ${themeColor}22`,
        }}
      >
        <div className={mobile ? 'min-h-0 flex-1 overflow-y-auto overscroll-contain' : undefined}>
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-xl leading-none shrink-0" aria-hidden>{'\u{1F528}'}</span>
            <div className="min-w-0">
              <h3 className="text-sm font-bold truncate" style={{ color: themeColor }}>
                {t('hephaestus.title', undefined, 'HEPHAESTUS · the forge')}
              </h3>
              <div className="text-[10px] font-mono text-white/40">
                {t('hephaestus.tagline', undefined, 'Price the graph before you spend it.')}
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 text-white/40 hover:text-white/80 text-lg leading-none px-1"
            aria-label={t('common.close', undefined, 'Close')}
          >
            ×
          </button>
        </div>

        {/* Catalogue readiness — the diagnostic. A count exposes what a list hides. */}
        <div className="mb-3 rounded-xl p-3" style={{ background: `${themeColor}0d`, border: `1px solid ${themeColor}33` }}>
          <div className="text-[10px] font-mono uppercase tracking-wide text-white/40 mb-2">
            {t('hephaestus.catalogue', undefined, 'Catalogue')}
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            <div>
              <div className="text-lg font-mono font-bold" style={{ color: themeColor }}>{capabilities}</div>
              <div className="text-[9px] font-mono text-white/40">
                {t('hephaestus.capabilities', undefined, 'capabilities')}
              </div>
            </div>
            <div>
              <div
                className="text-lg font-mono font-bold"
                style={{ color: composable === capabilities && capabilities > 0 ? '#00ff88' : '#ffcc33' }}
              >
                {composable}
              </div>
              <div className="text-[9px] font-mono text-white/40">
                {t('hephaestus.composable', undefined, 'composable')}
              </div>
            </div>
            <div>
              <div
                className="text-lg font-mono font-bold"
                style={{ color: measured > 0 ? '#00ff88' : '#ff9f43' }}
              >
                {measured}
              </div>
              <div className="text-[9px] font-mono text-white/40">
                {t('hephaestus.measured', undefined, 'measured')}
              </div>
            </div>
          </div>
          {capabilities > 0 && composable < capabilities && (
            <div className="text-[10px] text-white/50 mt-2 leading-snug">
              {t(
                'hephaestus.notComposable',
                undefined,
                `${capabilities - composable} of ${capabilities} rows cannot be wired: they declare no input fields or no output schema.`,
              )}
            </div>
          )}
          {capabilities > 0 && measured === 0 && (
            <div className="text-[10px] text-white/50 mt-1 leading-snug">
              {t(
                'hephaestus.noneMeasured',
                undefined,
                'No capability has an observed success rate yet — the published rates are placeholders, not scores.',
              )}
            </div>
          )}
        </div>

        {/* Totals over the runs actually on record */}
        <div className="grid grid-cols-3 gap-2 mb-3">
          {[
            { label: t('hephaestus.runs', undefined, 'runs'), value: String(totals.runs ?? 0) },
            { label: t('hephaestus.spend', undefined, 'spend'), value: money(totals.spend_usd) },
            { label: t('hephaestus.failed', undefined, 'failed'), value: String(totals.failed ?? 0) },
          ].map((cell) => (
            <div key={cell.label} className="rounded-lg p-2 text-center" style={{ background: '#ffffff08' }}>
              <div className="text-sm font-mono font-bold text-white/85">{cell.value}</div>
              <div className="text-[9px] font-mono text-white/40">{cell.label}</div>
            </div>
          ))}
        </div>

        {/* Run feed */}
        <div className="text-[10px] font-mono uppercase tracking-wide text-white/40 mb-2">
          {t('hephaestus.recentRuns', undefined, 'Recent runs')}
        </div>

        {offline && (
          <div className="text-[11px] text-white/50 leading-snug">
            {t('hephaestus.offline', undefined, 'The studio and the executor are not reachable from here.')}
          </div>
        )}

        {!offline && traces.length === 0 && (
          <div className="text-[11px] text-white/50 leading-snug">
            {t(
              'hephaestus.noRuns',
              undefined,
              'Nothing has run yet. When a graph runs, its signed bill of materials shows up here — cost per hop and, if it fails, which hop is to blame.',
            )}
          </div>
        )}

        <div className="space-y-2">
          {traces.map((trace) => {
            const color = trace.failed ? '#ff3b6b' : '#00ff88';
            return (
              <motion.div
                key={trace.trace_id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ type: 'spring', stiffness: 300, damping: 24 }}
                className="rounded-xl p-2.5"
                style={{
                  background: `linear-gradient(90deg, ${color}14, transparent)`,
                  border: `1px solid ${color}33`,
                }}
              >
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <span className="text-[11px] font-mono font-bold" style={{ color }}>
                    {trace.trace_id}
                  </span>
                  <span className="text-[9px] font-mono text-white/40">{ago(trace.completed_at)}</span>
                </div>
                <div className="text-[10px] font-mono text-white/60 mt-1">
                  {money(trace.total_usd)} · {trace.hops ?? trace.steps?.length ?? 0}{' '}
                  {t('hephaestus.hops', undefined, 'hops')}
                  {typeof trace.duration_ms === 'number' ? ` · ${trace.duration_ms} ms` : ''}
                  {trace.signed ? ' · signed' : ''}
                </div>

                <div className="mt-1.5 space-y-0.5">
                  {(trace.steps ?? []).map((step, index) => (
                    <div key={`${trace.trace_id}-${step.id ?? index}`} className="flex items-center gap-1.5">
                      <span
                        className="shrink-0 w-1.5 h-1.5 rounded-full"
                        style={{ backgroundColor: step.success ? '#00ff88' : '#ff3b6b' }}
                        aria-hidden
                      />
                      <span className="text-[10px] font-mono text-white/70 truncate">
                        {step.capability_id ?? step.id}
                      </span>
                      <span className="text-[9px] font-mono text-white/35 ml-auto shrink-0">
                        {money(step.price_usd)}
                      </span>
                    </div>
                  ))}
                </div>

                {trace.blame?.at_fault?.capability_id && (
                  <div className="mt-1.5 text-[10px] leading-snug" style={{ color: '#ff8fa3' }}>
                    {t('hephaestus.atFault', undefined, 'at fault')}:{' '}
                    <span className="font-mono">{trace.blame.at_fault.capability_id}</span>
                    {typeof trace.blame.at_fault.status_code === 'number'
                      ? ` (HTTP ${trace.blame.at_fault.status_code})`
                      : ''}
                    {(trace.blame.not_at_fault?.length ?? 0) > 0 && (
                      <span className="text-white/45">
                        {' · '}
                        {t('hephaestus.cleared', undefined, 'cleared')}:{' '}
                        {trace.blame.not_at_fault!.join(', ')}
                      </span>
                    )}
                  </div>
                )}
              </motion.div>
            );
          })}
        </div>
        </div>

        {studioUrl && (
          <a
            href={studioUrl}
            target="_blank"
            rel="noreferrer noopener"
            className="mt-3 shrink-0 block text-center text-[11px] font-mono font-bold rounded-lg py-2.5"
            style={{ backgroundColor: themeColor + '1f', border: `1px solid ${themeColor}55`, color: themeColor }}
          >
            {t('hephaestus.openStudio', undefined, 'Open the forge →')}
          </a>
        )}
      </div>
    </>
  );
}
