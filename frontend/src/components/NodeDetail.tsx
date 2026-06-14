import { useEffect, useRef, useState } from 'react';
import type { EcoNode } from '../App';
import { useI18n } from '../i18n';

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

      {/* Description */}
      <p className="text-xs text-white/60 mb-4 leading-relaxed">
        {node.description}
      </p>

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

      {/* URL if present */}
      {node.url && (
        <div className="mt-4 pt-3 border-t" style={{ borderColor: themeColor + '22' }}>
          <div className="text-[10px] font-mono text-white/30 break-all">
            {node.url}
          </div>
        </div>
      )}
    </div>
    </>
  );
}
