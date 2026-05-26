import { useCallback, useEffect, useRef, useState } from 'react';
import EcosystemGraph from './components/EcosystemGraph';
import MetricsPanel from './components/MetricsPanel';
import NodeDetail from './components/NodeDetail';
import AIAssistant from './components/AIAssistant';
import TransactionFlow from './components/TransactionFlow';
import ControlBar from './components/ControlBar';
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
  };
}

type MonitorMode = 'test' | 'real' | 'universe';

function isMonitorMode(v: string): v is MonitorMode {
  return v === 'test' || v === 'real' || v === 'universe';
}

export default function App() {
  const [mode, setMode] = useState<MonitorMode>('test');
  const [state, setState] = useState<EcosystemState | null>(null);
  const [selectedNode, setSelectedNode] = useState<EcoNode | null>(null);
  const [showAI, setShowAI] = useState(false);
  const [showTx, setShowTx] = useState(true);
  const [theme, setTheme] = useState<'cyan' | 'magenta' | 'green'>('cyan');
  const [pulseIntensity, setPulseIntensity] = useState(1.0);
  const nodePositionsRef = useRef<Map<string, { x: number; y: number; z: number }>>(new Map());

  const handleStateUpdate = useCallback((newState: EcosystemState) => {
    setState(newState);
    // Track node positions from the data
    newState.nodes.forEach((n: EcoNode) => {
      nodePositionsRef.current.set(n.id, n.position);
    });
  }, []);

  useWebSocket(mode, handleStateUpdate);

  // Match UI to backend ALIEN_MODE (docker prod defaults to real / LIVE).
  useEffect(() => {
    fetch('api/health')
      .then((r) => r.json())
      .then((d) => {
        if (d?.mode && isMonitorMode(d.mode)) {
          setMode(d.mode);
        }
      })
      .catch(() => {});
  }, []);

  const handleNodeClick = useCallback((node: EcoNode) => {
    setSelectedNode(node);
  }, []);

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
        themeColor={themeColor}
        pulseIntensity={pulseIntensity}
      />

      {/* Top metrics bar */}
      <MetricsPanel
        summary={state?.summary ?? null}
        mode={mode}
        themeColor={themeColor}
      />

      {/* Control bar — top right */}
      <ControlBar
        mode={mode}
        onModeChange={handleModeChange}
        theme={theme}
        onThemeChange={setTheme}
        showAI={showAI}
        onToggleAI={() => setShowAI(!showAI)}
        showTx={showTx}
        onToggleTx={() => setShowTx(!showTx)}
        pulseIntensity={pulseIntensity}
        onPulseChange={setPulseIntensity}
        themeColor={themeColor}
      />

      {/* Node detail panel — left side */}
      {selectedNode && (
        <NodeDetail
          node={selectedNode}
          onClose={() => setSelectedNode(null)}
          themeColor={themeColor}
        />
      )}

      {/* AI Assistant — right side */}
      {showAI && (
        <AIAssistant
          themeColor={themeColor}
          onClose={() => setShowAI(false)}
        />
      )}

      {/* Transaction flow — bottom */}
      {showTx && state && (
        <TransactionFlow
          transactions={state.transactions}
          events={state.events}
          themeColor={themeColor}
        />
      )}

      {/* Holographic corner decorations — desktop only */}
      <div className="hidden md:block">
        <CornerDecorations themeColor={themeColor} />
      </div>

      {/* Mode indicator — above mobile control dock */}
      <div
        className="
          absolute z-10 flex items-center gap-2 pointer-events-none
          left-3 bottom-[calc(4.25rem+var(--safe-bottom))] sm:left-4 sm:bottom-4
        "
      >
        <div
          className="w-2 h-2 rounded-full animate-pulse"
          style={{
            backgroundColor: mode === 'universe' ? '#7b2fff' : mode === 'test' ? '#ffdd00' : '#00ff88',
            boxShadow: `0 0 8px ${mode === 'universe' ? '#7b2fff' : mode === 'test' ? '#ffdd00' : '#00ff88'}`,
          }}
        />
        <span className="text-xs font-mono opacity-60">
          {mode === 'universe' ? 'VIRTUAL UNIVERSE' : mode === 'test' ? 'SIMULATION' : 'LIVE NETWORK'}
        </span>
        {state && (
          <span className="text-xs font-mono opacity-40 ml-2">
            TICK #{state.tick}
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
        className="absolute top-0 left-0 w-32 h-32 pointer-events-none z-10 opacity-30"
        viewBox="0 0 100 100"
      >
        <line x1="0" y1="2" x2="60" y2="2" stroke={themeColor} strokeWidth="1" />
        <line x1="2" y1="0" x2="2" y2="60" stroke={themeColor} strokeWidth="1" />
        <circle cx="8" cy="8" r="3" fill="none" stroke={themeColor} strokeWidth="0.5" opacity="0.5" />
      </svg>
      {/* Top-right corner */}
      <svg
        className="absolute top-0 right-0 w-32 h-32 pointer-events-none z-10 opacity-30"
        viewBox="0 0 100 100"
      >
        <line x1="40" y1="2" x2="100" y2="2" stroke={themeColor} strokeWidth="1" />
        <line x1="98" y1="0" x2="98" y2="60" stroke={themeColor} strokeWidth="1" />
        <circle cx="92" cy="8" r="3" fill="none" stroke={themeColor} strokeWidth="0.5" opacity="0.5" />
      </svg>
      {/* Bottom-right corner */}
      <svg
        className="absolute bottom-0 right-0 w-32 h-32 pointer-events-none z-10 opacity-30"
        viewBox="0 0 100 100"
      >
        <line x1="40" y1="98" x2="100" y2="98" stroke={themeColor} strokeWidth="1" />
        <line x1="98" y1="40" x2="98" y2="100" stroke={themeColor} strokeWidth="1" />
        <circle cx="92" cy="92" r="3" fill="none" stroke={themeColor} strokeWidth="0.5" opacity="0.5" />
      </svg>
    </>
  );
}
