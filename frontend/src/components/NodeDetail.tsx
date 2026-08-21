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
import MomusCard from './cards/MomusCard';
import NodeVisual, { hasNodeVisual } from './cards/NodeVisual';
import TreasuryCard from './cards/TreasuryCard';
import MetisCard from './cards/MetisCard';
import BridgesCard from './cards/BridgesCard';
import FactoryAgentsCard from './cards/FactoryAgentsCard';
import GaiaCard from './cards/GaiaCard';
import AtlasCard from './cards/AtlasCard';
import DioscuriCard from './cards/DioscuriCard';
import SkoposCard from './cards/SkoposCard';
import HeliosCard from './cards/HeliosCard';
import LogosCard from './cards/LogosCard';
import UseCasesCard from './cards/UseCasesCard';
import SignalHuntCard from './cards/SignalHuntCard';
import ThemisCard from './cards/ThemisCard';
import NodeSceneSlot from '../nodeScenes/NodeSceneSlot';
import { resolveNodeScene } from '../nodeScenes/resolve';

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
  const [expandedChild, setExpandedChild] = useState<string | null>(null);
  const [sensorQ, setSensorQ] = useState('');

  const metricLabel = (key: string) =>
    t(`nodeDetail.metricKeys.${key}`, undefined, key.replace(/_/g, ' '));

  useEffect(() => {
    setSensorQ('');
  }, [node.id]);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (expandedChild) setExpandedChild(null);
        else if (expandedMetric) setExpandedMetric(null);
        else onClose();
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [onClose, expandedMetric, expandedChild]);

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

  // --- Unified 3D / visual preview (oracles + momus/metis/atlas + competing galaxy) ---
  const isOracle = node.group === 'oracle' && node.id.startsWith('oracle-');
  const oracleSlug = isOracle ? slugFromNodeId(node.id) : '';
  const nodeScene = useMemo(() => resolveNodeScene(node), [node]);

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
      onClick={() => {
        if (expandedMetric) setExpandedMetric(null);
        if (expandedChild) setExpandedChild(null);
      }}
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

      {/* Unified scene slot — oracles, Momus/Metis/Atlas, use_cases, signal_hunt, … */}
      {nodeScene && (
        <NodeSceneSlot
          scene={nodeScene}
          node={node}
          themeColor={themeColor}
          mobile={mobile}
          t={t}
        />
      )}
      {/* Legacy shim path unused when nodeScene resolves; keep hasNodeVisual for tests. */}
      {!nodeScene && hasNodeVisual(node) && (
        <NodeVisual node={node} themeColor={themeColor} mobile={mobile} t={t} />
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

      {/* Hub affiliation — every node belongs to a federation Hub */}
      {node.hub && (
        <div className="mb-4" onClick={(e) => e.stopPropagation()}>
          <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-1.5">
            {t('nodeDetail.hub')}
          </div>
          <div
            className="px-3 py-2 rounded"
            style={{
              backgroundColor: themeColor + '0a',
              border: `1px solid ${themeColor}28`,
            }}
          >
            {node.hub.url ? (
              <a
                href={node.hub.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs font-semibold hover:underline"
                style={{ color: themeColor }}
              >
                {node.hub.label}
              </a>
            ) : (
              <span className="text-xs font-semibold" style={{ color: themeColor }}>
                {node.hub.label}
              </span>
            )}
            {node.hub.id === node.id && (
              <div className="text-[10px] font-mono text-white/35 mt-1">
                {t('nodeDetail.hubSelf')}
              </div>
            )}
            {node.hub.url && node.hub.id !== node.id && (
              <div className="text-[10px] font-mono text-white/35 mt-1 truncate" title={node.hub.url}>
                {node.hub.url.replace(/^https?:\/\//, '')}
              </div>
            )}
          </div>
        </div>
      )}

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

      {/* Sub-components — generic nodes, or DIOSCURI twins + collaboration split.
          DIOSCURI renders its own card (twins/collaboration + community links). */}
      {node.id === 'dioscuri' ? (
        <DioscuriCard
          node={node}
          themeColor={themeColor}
          mobile={mobile}
          t={t}
          expandedChild={expandedChild}
          setExpandedChild={setExpandedChild}
        />
      ) : node.children && node.children.length > 0 ? (
        <div onClick={(e) => e.stopPropagation()}>
          <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-2">
            {t('nodeDetail.subcomponents', { count: node.children.length })}
          </div>
          <div className="space-y-1 max-h-56 overflow-y-auto">
            {node.children.map((child) => {
              const childBody = (
                <>
                  <div
                    className="w-1.5 h-1.5 rounded-full shrink-0"
                    style={{ backgroundColor: themeColor, opacity: 0.6 }}
                  />
                  <span className="text-white/70">{child.label}</span>
                  {child.url && <span className="ml-auto text-white/30">↗</span>}
                </>
              );
              return child.url ? (
                <a
                  key={child.id}
                  href={child.url}
                  target="_blank"
                  rel="noreferrer"
                  className="px-3 py-1.5 rounded text-xs flex items-center gap-2 transition-colors hover:brightness-110"
                  style={{ backgroundColor: themeColor + '08', color: themeColor }}
                >
                  {childBody}
                </a>
              ) : (
                <div
                  key={child.id}
                  className="px-3 py-1.5 rounded text-xs flex items-center gap-2"
                  style={{ backgroundColor: themeColor + '08' }}
                >
                  {childBody}
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {/* HELIOS YouTube channel link */}
      {node.id === 'helios' && node.youtube_url && (
        <HeliosCard node={node} themeColor={themeColor} mobile={mobile} t={t} />
      )}

      {/* SKOPOS — dashboard + docs links (public status in metrics). */}
      {node.id === 'skopos' && node.links && Object.keys(node.links).length > 0 && (
        <SkoposCard node={node} themeColor={themeColor} mobile={mobile} t={t} />
      )}
      {node.id === 'gaia' && (
        <GaiaCard
          node={node}
          themeColor={themeColor}
          mobile={mobile}
          sensorQ={sensorQ}
          setSensorQ={setSensorQ}
          t={t}
        />
      )}
      {node.id === 'atlas' && (
        <AtlasCard
          node={node}
          themeColor={themeColor}
          mobile={mobile}
          sensorQ={sensorQ}
          setSensorQ={setSensorQ}
          t={t}
        />
      )}
      {node.id === 'metis' && (
        <MetisCard node={node} themeColor={themeColor} mobile={mobile} t={t} />
      )}
      {node.id === 'momus' && (
        <MomusCard node={node} themeColor={themeColor} mobile={mobile} t={t} />
      )}
      {node.id === 'use_cases' && (
        <UseCasesCard node={node} themeColor={themeColor} mobile={mobile} t={t} />
      )}
      {node.id === 'signal_hunt' && (
        <SignalHuntCard node={node} themeColor={themeColor} mobile={mobile} t={t} />
      )}
      {/* TREASURY — the separate payer. Ledger tail + the separation, from the other side. */}
      {node.id === 'treasury' && node.treasury_live && (
        <TreasuryCard node={node} themeColor={themeColor} mobile={mobile} t={t} />
      )}

      {/* BRIDGES — the third paid invoke channel, and the only one nothing counts. */}
      {node.id === 'logos' && (
        <LogosCard node={node} themeColor={themeColor} mobile={mobile} t={t} />
      )}
      {node.id === 'bridges' && node.bridges_live && (
        <BridgesCard node={node} themeColor={themeColor} mobile={mobile} t={t} />
      )}
      {node.id === 'themis' && (
        <ThemisCard node={node} themeColor={themeColor} mobile={mobile} t={t} />
      )}

      {/* Agents the factory shipped — who is running, on which SDK, and what they spend. */}
      {node.id === 'factory_agents' && (
        <FactoryAgentsCard node={node} themeColor={themeColor} mobile={mobile} t={t} />
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
