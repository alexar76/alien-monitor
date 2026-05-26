import { useCallback, useEffect, useRef, useState } from 'react';
import { useI18n } from './i18n';
import EcosystemGraph from './components/EcosystemGraph';
import MetricsPanel from './components/MetricsPanel';
import NodeDetail from './components/NodeDetail';
import AIAssistant from './components/AIAssistant';
import TransactionFlow from './components/TransactionFlow';
import ControlBar from './components/ControlBar';
import MobileDock, { type MobileSheet } from './components/MobileDock';
import { useIsMobile } from './hooks/useIsMobile';
import { apiUrl } from './api';
import { useWebSocket } from './hooks/useWebSocket';

export interface EcoNode {
  id: string;
  label: string;
  group: string;
  icon: string;
  description: string;
  metrics: Record<string, number>;
  status: 'active' | 'idle' | 'error' | 'unknown';
  position: { x: number; y: number; z: number };
  children?: { id: string; label: string }[];
  url?: string;
}

export interface EcoLink {
  source: string;
  target: string;
  label: string;
}

export interface TxEvent {
  id: string;
  ts: string;
  agent: string;
  action: string;
  target: string;
  amount: number;
  token: string;
}

export interface Transaction {
  id: string;
  from: string;
  to: string;
  amount: number;
  token: string;
  ts: string;
}

export interface EcosystemState {
  tick: number;
  ts: string;
  nodes: EcoNode[];
  links: EcoLink[];
  events: TxEvent[];
  transactions: Transaction[];
  channels: { id: string; agent: string; amount: number; token: string; status: string; ts: string }[];
  summary: {
    total_invocations_24h: number;
    total_volume_usd: number;
    active_channels: number;
    tvl_usd: number;
    agents_online: number;
    apps_online: number;
    tps_solana: number;
    gas_gwei: number;
    block_number?: number;
    onchain_tx_count?: number;
    mode: string;
    tick: number;
    blockchain_ready?: boolean;
    products_created?: number;
    entities_total?: number;
    evm_rpc?: string;
    usdt_contract?: string;
    scenario_phase?: string;
  };
  scenario?: {
    phase: string;
    phase_progress: number;
    phase_color: string;
    tick_count: number;
    funding_total: number;
    hub_count: number;
    buyer_rounds: number;
  };
  funding_events?: Array<{
    id: string;
    amount: number;
    token: string;
    source: string;
    tx_hash: string;
    ts: string;
    total_funding: number;
    round: number;
  }>;
}

type MonitorMode = 'test' | 'real' | 'universe';

function isMonitorMode(v: string): v is MonitorMode {
  return v === 'test' || v === 'real' || v === 'universe';
}

export default function App() {
  const { t } = useI18n();
  const isMobile = useIsMobile();
  const [mode, setMode] = useState<MonitorMode>('test');
  const [state, setState] = useState<EcosystemState | null>(null);
  const [selectedNode, setSelectedNode] = useState<EcoNode | null>(null);
  const [showAI, setShowAI] = useState(false);
  const [showTx, setShowTx] = useState(true);
  const [mobileSheet, setMobileSheet] = useState<MobileSheet>('none');
  const [theme, setTheme] = useState<'cyan' | 'magenta' | 'green'>('cyan');
  const [pulseIntensity, setPulseIntensity] = useState(1.0);

  const handleStateUpdate = useCallback((newState: EcosystemState) => {
    setState(newState);
  }, []);

  useWebSocket(mode, handleStateUpdate);

  // Sync UI mode with backend ALIEN_MODE (prod docker defaults to real / LIVE).
  useEffect(() => {
    fetch(apiUrl('/api/health'))
      .then((r) => r.json())
      .then((d) => {
        if (d?.mode && isMonitorMode(d.mode)) {
          setMode(d.mode);
        }
      })
      .catch(() => {});
  }, []);

  const handleNodeClick = useCallback(
    (node: EcoNode) => {
      setSelectedNode(node);
      if (isMobile) {
        setMobileSheet('node');
        setShowAI(false);
      }
    },
    [isMobile],
  );

  const handleCloseNode = useCallback(() => {
    setSelectedNode(null);
    setMobileSheet((s) => (s === 'node' ? 'none' : s));
  }, []);

  const handleToggleAI = useCallback(() => {
    setShowAI((prev) => {
      const next = !prev;
      if (isMobile && next) {
        setMobileSheet('ai');
        setShowTx(false);
      }
      return next;
    });
  }, [isMobile]);

  const handleToggleTx = useCallback(() => {
    setShowTx((prev) => {
      const next = !prev;
      if (isMobile && next) {
        setMobileSheet('tx');
        setShowAI(false);
      }
      return next;
    });
  }, [isMobile]);

  const handleMobileSheet = useCallback(
    (sheet: MobileSheet) => {
      setMobileSheet(sheet);
      if (sheet === 'none') {
        setShowAI(false);
        setShowTx(false);
        return;
      }
      if (sheet === 'ai') {
        setShowAI(true);
        setShowTx(false);
        return;
      }
      if (sheet === 'tx') {
        setShowTx(true);
        setShowAI(false);
        return;
      }
      if (sheet === 'node' && !selectedNode) {
        setMobileSheet('none');
      }
      if (sheet === 'controls') {
        setShowAI(false);
        setShowTx(false);
      }
    },
    [selectedNode],
  );

  const handleModeChange = useCallback((newMode: MonitorMode) => {
    setMode(newMode);
  }, []);

  const themeColor = {
    cyan: '#00f0ff',
    magenta: '#ff00ff',
    green: '#00ff88',
  }[theme];

  return (
    <div className="relative w-full min-h-[100dvh] h-[100dvh] bg-[#0a0a0f] overflow-hidden">
      {/* Grid background */}
      <div className="absolute inset-0 grid-bg opacity-40 pointer-events-none" />

      {/* Scan line effect */}
      <div className="scan-line" />

      {/* Main 3D Graph — full screen background */}
      <EcosystemGraph
        state={state}
        onNodeClick={handleNodeClick}
        focusNodeId={selectedNode?.id ?? null}
        themeColor={themeColor}
        pulseIntensity={pulseIntensity}
        fundingEvents={state?.funding_events ?? null}
        scenario={state?.scenario ?? null}
      />

      {/* Top metrics bar */}
      <MetricsPanel
        summary={state?.summary ?? null}
        scenario={state?.scenario ?? null}
        mode={mode}
        themeColor={themeColor}
      />

      {/* Mobile backdrop for sheets */}
      {isMobile && mobileSheet !== 'none' && (
        <button
          type="button"
          className="md:hidden fixed inset-0 z-30 bg-black/55 backdrop-blur-[2px]"
          aria-label={t('mobile.closeSheet')}
          onClick={() => handleMobileSheet('none')}
        />
      )}

      {/* Control bar — desktop top-right; mobile settings sheet */}
      <ControlBar
        mode={mode}
        onModeChange={handleModeChange}
        theme={theme}
        onThemeChange={setTheme}
        showAI={showAI}
        onToggleAI={handleToggleAI}
        showTx={showTx}
        onToggleTx={handleToggleTx}
        pulseIntensity={pulseIntensity}
        onPulseChange={setPulseIntensity}
        themeColor={themeColor}
        mobileOpen={isMobile && mobileSheet === 'controls'}
        onMobileClose={() => handleMobileSheet('none')}
      />

      {/* Node detail panel */}
      {selectedNode && (!isMobile || mobileSheet === 'node') && (
        <NodeDetail
          node={selectedNode}
          onClose={handleCloseNode}
          themeColor={themeColor}
          mobile={isMobile}
        />
      )}

      {/* AI Assistant */}
      {showAI && (!isMobile || mobileSheet === 'ai') && (
        <AIAssistant
          themeColor={themeColor}
          onClose={() => {
            setShowAI(false);
            setMobileSheet((s) => (s === 'ai' ? 'none' : s));
          }}
          monitorState={state}
          selectedNodeId={selectedNode?.id ?? null}
          mobile={isMobile}
        />
      )}

      {/* Transaction flow */}
      {showTx && state && (!isMobile || mobileSheet === 'tx') && (
        <TransactionFlow
          transactions={state.transactions}
          events={state.events}
          themeColor={themeColor}
          mobile={isMobile}
        />
      )}

      {isMobile && (
        <MobileDock
          sheet={mobileSheet}
          onSheetChange={handleMobileSheet}
          hasNode={!!selectedNode}
          showAI={showAI}
          showTx={showTx}
          themeColor={themeColor}
        />
      )}

      {/* Holographic corner decorations — desktop only */}
      <CornerDecorations themeColor={themeColor} />

      {/* Mode indicator */}
      <div className="absolute bottom-[4.75rem] left-2 z-10 flex items-center gap-2 md:bottom-4 md:left-4 max-w-[55vw]">
        <div
          className="w-2 h-2 rounded-full animate-pulse"
          style={{
            backgroundColor: mode === 'test' ? '#ffdd00' : mode === 'universe' ? state?.scenario?.phase_color ?? '#8844ff' : '#00ff88',
            boxShadow: `0 0 8px ${mode === 'test' ? '#ffdd00' : mode === 'universe' ? state?.scenario?.phase_color ?? '#8844ff' : '#00ff88'}`,
          }}
        />
        <span className="text-xs font-mono opacity-60">
          {mode === 'test'
            ? t('mode.footerSimulation')
            : mode === 'universe'
              ? t('mode.footerUniverse', {
                  phase: t(
                    `scenario.${state?.scenario?.phase ?? 'BOOTSTRAP'}`,
                    undefined,
                    state?.scenario?.phase ?? 'BOOTSTRAP',
                  ),
                })
              : t('mode.footerLive')}
        </span>
        {state && (
          <span className="text-xs font-mono opacity-40 ml-2">
            {t('tick', { n: state.tick })}
          </span>
        )}
      </div>
    </div>
  );
}

function CornerDecorations({ themeColor }: { themeColor: string }) {
  return (
    <>
      {/* Top-left corner */}
      <svg
        className="absolute top-0 left-0 w-32 h-32 pointer-events-none z-10 opacity-30 hidden md:block"
        viewBox="0 0 100 100"
      >
        <line x1="0" y1="2" x2="60" y2="2" stroke={themeColor} strokeWidth="1" />
        <line x1="2" y1="0" x2="2" y2="60" stroke={themeColor} strokeWidth="1" />
        <circle cx="8" cy="8" r="3" fill="none" stroke={themeColor} strokeWidth="0.5" opacity="0.5" />
      </svg>
      {/* Top-right corner */}
      <svg
        className="absolute top-0 right-0 w-32 h-32 pointer-events-none z-10 opacity-30 hidden md:block"
        viewBox="0 0 100 100"
      >
        <line x1="40" y1="2" x2="100" y2="2" stroke={themeColor} strokeWidth="1" />
        <line x1="98" y1="0" x2="98" y2="60" stroke={themeColor} strokeWidth="1" />
        <circle cx="92" cy="8" r="3" fill="none" stroke={themeColor} strokeWidth="0.5" opacity="0.5" />
      </svg>
      {/* Bottom-right corner */}
      <svg
        className="absolute bottom-0 right-0 w-32 h-32 pointer-events-none z-10 opacity-30 hidden md:block"
        viewBox="0 0 100 100"
      >
        <line x1="40" y1="98" x2="100" y2="98" stroke={themeColor} strokeWidth="1" />
        <line x1="98" y1="40" x2="98" y2="100" stroke={themeColor} strokeWidth="1" />
        <circle cx="92" cy="92" r="3" fill="none" stroke={themeColor} strokeWidth="0.5" opacity="0.5" />
      </svg>
    </>
  );
}
