import { useEffect, useMemo, useRef, useState } from 'react';
import type { EcoNode } from '../App';
import { useI18n } from '../i18n';
import {
  descriptionWithoutCaps,
  fetchOracleTools,
  parseCapsFromDescription,
  slugFromNodeId,
  type OracleManifest,
} from '../lib/oracleManifest';
import OraclePrimitive3D from './OraclePrimitive3D';
import { oracleSceneMeta } from '../oracleScenes/meta';

interface Props {
  node: EcoNode;
  onClose: () => void;
  themeColor: string;
  mobile?: boolean;
}

function isExpandableMetric(value: unknown): boolean {
  const s = String(value);
  return s.length > 16 || /^0x[a-fA-F0-9]{10,}$/.test(s);
}

function truncateMetric(value: unknown): string {
  const s = String(value);
  if (s.length <= 18) return s;
  if (/^0x[a-fA-F0-9]+$/.test(s) && s.length > 14) {
    return `${s.slice(0, 8)}…${s.slice(-6)}`;
  }
  return `${s.slice(0, 14)}…`;
}

function MetricCell({
  metricKey,
  metricLabel,
  value,
  themeColor,
  expanded,
  onToggle,
}: {
  metricKey: string;
  metricLabel: string;
  value: unknown;
  themeColor: string;
  expanded: boolean;
  onToggle: () => void;
}) {
  const full = typeof value === 'number' ? value.toLocaleString() : String(value);
  const expandable = isExpandableMetric(value);
  const display = expanded || !expandable ? full : truncateMetric(value);

  return (
    <div
      role={expandable ? 'button' : undefined}
      tabIndex={expandable ? 0 : undefined}
      onClick={expandable ? onToggle : undefined}
      onKeyDown={
        expandable
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onToggle();
              }
            }
          : undefined
      }
      className={`relative px-3 py-2 rounded transition-all duration-300 ease-out ${
        expandable ? 'cursor-pointer hover:brightness-110' : ''
      } ${expanded ? 'col-span-2 z-40' : 'min-w-0'}`}
      style={{
        backgroundColor: themeColor + (expanded ? '18' : '0a'),
        border: `1px solid ${themeColor}${expanded ? '66' : '18'}`,
        transform: expanded
          ? 'perspective(720px) translateZ(28px) scale(1.06) rotateX(6deg)'
          : undefined,
        transformStyle: 'preserve-3d',
        boxShadow: expanded ? `0 12px 32px rgba(0,0,0,0.55), 0 0 20px ${themeColor}33` : undefined,
      }}
    >
      <div
        className={`font-mono font-bold ${expanded ? 'text-base break-all leading-snug' : 'text-sm truncate'}`}
        style={{ color: themeColor }}
        title={expandable && !expanded ? full : undefined}
      >
        {display}
      </div>
      <div className="text-[10px] font-mono text-white/40 mt-0.5">
        {metricLabel}
      </div>
    </div>
  );
}

export default function NodeDetail({ node, onClose, themeColor, mobile = false }: Props) {
  const { t } = useI18n();
  const panelRef = useRef<HTMLDivElement>(null);
  const [expandedMetric, setExpandedMetric] = useState<string | null>(null);

  const metricLabel = (key: string) =>
    t(`nodeDetail.metricKeys.${key}`, undefined, key.replace(/_/g, ' '));

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (expandedMetric) setExpandedMetric(null);
        else onClose();
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [onClose, expandedMetric]);

  const toggleMetric = (key: string) => {
    setExpandedMetric((prev) => (prev === key ? null : key));
  };

  const statusColor =
    node.status === 'active' ? '#00ff88' :
    node.status === 'error' ? '#ff3355' :
    node.status === 'idle' ? '#ffdd00' : '#666666';

  useEffect(() => {
    if (!mobile) return undefined;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = '';
    };
  }, [mobile]);

  // --- Oracle preview + products/services ---
  const isOracle = node.group === 'oracle' && node.id.startsWith('oracle-');
  const oracleSlug = isOracle ? slugFromNodeId(node.id) : '';
  // We can render a local math-primitive preview only for slugs we know a scene
  // (or bundled ambient visual) for. Unknown oracle nodes (e.g. the UMBRAL cave)
  // simply skip the preview block.
  const previewMeta = isOracle ? oracleSceneMeta(oracleSlug) : undefined;
  const embedUrl = useMemo(() => {
    if (!isOracle || !node.url) return undefined;
    return node.url + (node.url.includes('?') ? '&' : '?') + 'embed=1';
  }, [isOracle, node.url]);

  // Capability ids parsed off the node — the always-available fallback.
  const fallbackCaps = useMemo(
    () => (isOracle ? parseCapsFromDescription(node.description) : []),
    [isOracle, node.description],
  );
  const oracleBlurb = useMemo(
    () => (isOracle ? descriptionWithoutCaps(node.description) : ''),
    [isOracle, node.description],
  );

  // Live products & services from the oracle's AI-Market manifest (best-effort, cached).
  const [manifest, setManifest] = useState<OracleManifest | null>(null);
  useEffect(() => {
    if (!isOracle) {
      setManifest(null);
      return undefined;
    }
    let alive = true;
    setManifest(null);
    fetchOracleTools(node.url, oracleSlug)
      .then((m) => {
        if (alive) setManifest(m);
      })
      .catch(() => {
        if (alive) setManifest(null);
      });
    return () => {
      alive = false;
    };
  }, [isOracle, node.url, oracleSlug]);
  const manifestTools = manifest?.tools ?? null;

  return (
    <>
      {mobile && (
        <button
          type="button"
          className="mobile-backdrop"
          aria-label={t('mobile.closeSheet')}
          onClick={onClose}
        />
      )}
      <div
      ref={panelRef}
      className={`z-40 glass-panel p-4 md:p-5 animate-slide-in overflow-visible ${
        mobile
          ? 'fixed inset-x-0 bottom-0 mobile-sheet max-h-[min(72dvh,520px)] overflow-y-auto'
          : 'absolute left-4 top-24 w-80 max-h-[calc(100vh-8rem)] overflow-y-auto'
      }`}
      style={{
        borderColor: themeColor + '44',
        boxShadow: `0 0 30px rgba(0,0,0,0.5), 0 0 15px ${themeColor}22`,
        perspective: '900px',
      }}
      onClick={() => expandedMetric && setExpandedMetric(null)}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2">
          <div
            className="w-3 h-3 rounded-full"
            style={{ backgroundColor: statusColor, boxShadow: `0 0 6px ${statusColor}` }}
          />
          <h3 className="text-sm font-semibold truncate" style={{ color: themeColor }}>
            {node.label}
          </h3>
        </div>
        <button
          onClick={onClose}
          className="text-white/40 hover:text-white/80 transition-colors text-2xl leading-none w-10 h-10 flex items-center justify-center shrink-0"
          aria-label={t('mobile.closeSheet')}
        >
          ×
        </button>
      </div>

      {/* Description — localized per node id, with the backend English text as fallback. */}
      <p className="text-xs text-white/60 mb-4 leading-relaxed">
        {t(`nodeDetail.desc.${node.id}`, undefined, isOracle ? oracleBlurb : node.description)}
      </p>

      {/* Oracle math-primitive preview — a real, locally-rendered 3D scene of the
          oracle's mathematics (or a bundled ambient canvas), with a clickable
          link to the full live scene. No dependency on the remote site. */}
      {previewMeta && (
        <div className="mb-4" onClick={(e) => e.stopPropagation()}>
          <OraclePrimitive3D
            slug={oracleSlug}
            accent={themeColor}
            mobile={mobile}
            liveSceneUrl={node.url}
            embedUrl={embedUrl}
            openLabel={t('nodeDetail.oracle.openScene')}
            primitiveLabel={previewMeta.primitive}
          />
        </div>
      )}

      {/* Group badge */}
      <div className="mb-4">
        <span
          className="inline-block px-2 py-0.5 rounded text-[10px] font-mono uppercase"
          style={{
            backgroundColor: themeColor + '18',
            color: themeColor,
            border: `1px solid ${themeColor}44`,
          }}
        >
          {t(`group.${node.group}`, undefined, node.group)}
        </span>
        <span
          className="inline-block ml-2 px-2 py-0.5 rounded text-[10px] font-mono uppercase"
          style={{
            backgroundColor: statusColor + '18',
            color: statusColor,
            border: `1px solid ${statusColor}44`,
          }}
        >
          {t(`status.${node.status}`)}
        </span>
      </div>

      {/* Oracle products & services — capabilities (id · what · price) + math one-liner.
          Prefers the live AI-Market manifest; falls back to capability ids on the node. */}
      {isOracle && (manifestTools?.length || fallbackCaps.length > 0) && (
        <div className="mb-4" onClick={(e) => e.stopPropagation()}>
          <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-2">
            {t('nodeDetail.oracle.products')}
          </div>
          <div className="space-y-1.5">
            {manifestTools && manifestTools.length > 0
              ? manifestTools.map((tool) => (
                  <div
                    key={tool.capability_id}
                    className="px-3 py-2 rounded"
                    style={{
                      backgroundColor: themeColor + '0a',
                      border: `1px solid ${themeColor}18`,
                    }}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span
                        className="font-mono text-xs font-semibold truncate"
                        style={{ color: themeColor }}
                        title={tool.capability_id}
                      >
                        {tool.capability_id}
                      </span>
                      {typeof tool.price_per_call_usd === 'number' && (
                        <span className="font-mono text-[10px] text-white/50 shrink-0">
                          ${tool.price_per_call_usd}
                        </span>
                      )}
                    </div>
                    {tool.description && (
                      <div className="text-[11px] text-white/50 mt-0.5 leading-snug">
                        {tool.description}
                      </div>
                    )}
                  </div>
                ))
              : fallbackCaps.map((cap) => (
                  <div
                    key={cap}
                    className="px-3 py-1.5 rounded font-mono text-xs"
                    style={{
                      backgroundColor: themeColor + '0a',
                      border: `1px solid ${themeColor}18`,
                      color: themeColor,
                    }}
                  >
                    {cap}
                  </div>
                ))}
          </div>
          {/* Math one-liner — oracle-level description from the manifest when available. */}
          {manifest?.description && (
            <p className="mt-2 text-[11px] text-white/45 leading-snug">
              <span className="font-mono uppercase tracking-wider text-white/30">
                {t('nodeDetail.oracle.math')}:
              </span>{' '}
              {manifest.description}
            </p>
          )}
        </div>
      )}

      {/* Metrics */}
      {Object.keys(node.metrics).length > 0 && (
        <div className="mb-4" onClick={(e) => e.stopPropagation()}>
          <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-2">
            {t('nodeDetail.metrics')}
          </div>
          <div className="grid grid-cols-2 gap-2 min-w-0">
            {Object.entries(node.metrics).map(([key, value]) => (
              <MetricCell
                key={key}
                metricKey={key}
                metricLabel={metricLabel(key)}
                value={value}
                themeColor={themeColor}
                expanded={expandedMetric === key}
                onToggle={() => toggleMetric(key)}
              />
            ))}
          </div>
        </div>
      )}

      {/* Children nodes */}
      {node.children && node.children.length > 0 && (
        <div>
          <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-2">
            {t('nodeDetail.subcomponents', { count: node.children.length })}
          </div>
          <div className="space-y-1 max-h-48 overflow-y-auto">
            {node.children.map((child) => (
              <div
                key={child.id}
                className="px-3 py-1.5 rounded text-xs flex items-center gap-2"
                style={{ backgroundColor: themeColor + '08' }}
              >
                <div
                  className="w-1.5 h-1.5 rounded-full"
                  style={{ backgroundColor: themeColor, opacity: 0.6 }}
                />
                <span className="text-white/70">{child.label}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* URL if present — clickable, opens in a new tab. */}
      {node.url && (
        <div className="mt-4 pt-3 border-t" style={{ borderColor: themeColor + '22' }}>
          <a
            href={node.url}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="text-[10px] font-mono break-all transition-colors underline decoration-dotted underline-offset-2"
            style={{ color: themeColor }}
          >
            {node.url} ↗
          </a>
        </div>
      )}
    </div>
    </>
  );
}
