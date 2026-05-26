import { useEffect, useRef } from 'react';
import type { EcoNode } from '../App';
import { useIsMobile } from '../hooks/useIsMobile';

interface Props {
  node: EcoNode;
  onClose: () => void;
  themeColor: string;
}

export default function NodeDetail({ node, onClose, themeColor }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);
  const isMobile = useIsMobile();

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [onClose]);

  useEffect(() => {
    if (isMobile) {
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = '';
      };
    }
    return undefined;
  }, [isMobile]);

  const statusColor =
    node.status === 'active' ? '#00ff88' :
    node.status === 'error' ? '#ff3355' :
    node.status === 'idle' ? '#ffdd00' : '#666666';

  return (
    <>
      {isMobile && (
        <button
          type="button"
          className="mobile-backdrop"
          aria-label="Close node details"
          onClick={onClose}
        />
      )}
      <div
        ref={panelRef}
        className={`
          z-30 glass-panel p-4 sm:p-5
          ${isMobile
            ? 'fixed inset-x-0 bottom-0 mobile-sheet animate-slide-up max-h-[72dvh] overflow-y-auto'
            : 'absolute left-4 top-24 w-80 max-h-[calc(100vh-8rem)] overflow-y-auto'}
        `}
        style={{
          borderColor: themeColor + '44',
          boxShadow: `0 0 30px rgba(0,0,0,0.5), 0 0 15px ${themeColor}22`,
        }}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2 min-w-0">
            <div
              className="w-3 h-3 rounded-full shrink-0"
              style={{ backgroundColor: statusColor, boxShadow: `0 0 6px ${statusColor}` }}
            />
            <h3 className="text-sm font-semibold truncate" style={{ color: themeColor }}>
              {node.label}
            </h3>
          </div>
          <button
            onClick={onClose}
            className="text-white/40 hover:text-white/80 transition-colors text-2xl leading-none w-10 h-10 flex items-center justify-center shrink-0"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <p className="text-xs text-white/60 mb-4 leading-relaxed">{node.description}</p>

        <div className="mb-4 flex flex-wrap gap-2">
          <span
            className="inline-block px-2 py-0.5 rounded text-[10px] font-mono uppercase"
            style={{
              backgroundColor: themeColor + '18',
              color: themeColor,
              border: `1px solid ${themeColor}44`,
            }}
          >
            {node.group}
          </span>
          <span
            className="inline-block px-2 py-0.5 rounded text-[10px] font-mono uppercase"
            style={{
              backgroundColor: statusColor + '18',
              color: statusColor,
              border: `1px solid ${statusColor}44`,
            }}
          >
            {node.status}
          </span>
        </div>

        {Object.keys(node.metrics).length > 0 && (
          <div className="mb-4">
            <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-2">
              Metrics
            </div>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(node.metrics).map(([key, value]) => (
                <div
                  key={key}
                  className="px-3 py-2 rounded"
                  style={{ backgroundColor: themeColor + '0a', border: `1px solid ${themeColor}18` }}
                >
                  <div className="text-sm font-mono font-bold" style={{ color: themeColor }}>
                    {typeof value === 'number' ? value.toLocaleString() : String(value)}
                  </div>
                  <div className="text-[10px] font-mono text-white/40 capitalize">
                    {key.replace(/_/g, ' ')}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {node.children && node.children.length > 0 && (
          <div>
            <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-2">
              Sub-components ({node.children.length})
            </div>
            <div className="space-y-1 max-h-40 sm:max-h-48 overflow-y-auto">
              {node.children.map((child) => (
                <div
                  key={child.id}
                  className="px-3 py-2 rounded text-xs flex items-center gap-2"
                  style={{ backgroundColor: themeColor + '08' }}
                >
                  <div
                    className="w-1.5 h-1.5 rounded-full shrink-0"
                    style={{ backgroundColor: themeColor, opacity: 0.6 }}
                  />
                  <span className="text-white/70">{child.label}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {node.url && (
          <div className="mt-4 pt-3 border-t" style={{ borderColor: themeColor + '22' }}>
            <div className="text-[10px] font-mono text-white/30 break-all">{node.url}</div>
          </div>
        )}
      </div>
    </>
  );
}
