import { useEffect, useState } from 'react';

interface Summary {
  total_invocations_24h: number;
  total_volume_usd: number;
  active_channels: number;
  tvl_usd: number;
  agents_online: number;
  apps_online: number;
  tps_solana: number;
  gas_gwei: number;
  mode: string;
  tick: number;
  blockchain_ready?: boolean;
  block_number?: number;
  onchain_tx_count?: number;
}

interface Props {
  summary: Summary | null;
  mode: string;
  themeColor: string;
}

export default function MetricsPanel({ summary, mode, themeColor }: Props) {
  const [animatedValues, setAnimatedValues] = useState<Record<string, number>>({});

  useEffect(() => {
    if (!summary) return;
    const targets: Record<string, number> = {
      invocations: summary.total_invocations_24h,
      volume: summary.total_volume_usd,
      channels: summary.active_channels,
      tvl: summary.tvl_usd,
      agents: summary.agents_online,
      apps: summary.apps_online,
    };

    const interval = setInterval(() => {
      setAnimatedValues((prev) => {
        const next: Record<string, number> = {};
        for (const [key, target] of Object.entries(targets)) {
          const current = prev[key] ?? target * 0.7;
          next[key] = current + (target - current) * 0.15;
        }
        return next;
      });
    }, 50);

    return () => clearInterval(interval);
  }, [summary]);

  if (!summary) {
    return (
      <div
        className="absolute top-0 left-0 right-0 z-20 px-2 pt-[max(0.5rem,var(--safe-top))] sm:p-4"
      >
        <div className="glass-panel px-4 py-2.5 sm:px-6 sm:py-3 flex items-center justify-center">
          <span className="text-xs sm:text-sm font-mono opacity-60">Connecting to ecosystem...</span>
        </div>
      </div>
    );
  }

  const fmt = (v: number | undefined) => {
    if (v === undefined) return '--';
    if (v >= 1000000) return `${(v / 1000000).toFixed(1)}M`;
    if (v >= 1000) return `${(v / 1000).toFixed(1)}K`;
    return v.toFixed(0);
  };

  const fmtUSD = (v: number | undefined) => {
    if (v === undefined) return '$--';
    if (v >= 1000000) return `$${(v / 1000000).toFixed(2)}M`;
    if (v >= 1000) return `$${(v / 1000).toFixed(1)}K`;
    return `$${v.toFixed(0)}`;
  };

  const metrics = [
    { label: 'Invocations', value: fmt(animatedValues.invocations), key: 'invocations' },
    { label: 'Volume 24h', value: fmtUSD(animatedValues.volume), key: 'volume' },
    { label: 'Channels', value: fmt(animatedValues.channels), key: 'channels' },
    { label: 'TVL', value: fmtUSD(animatedValues.tvl), key: 'tvl' },
    { label: 'Agents', value: fmt(animatedValues.agents), key: 'agents' },
    { label: 'Apps', value: fmt(animatedValues.apps), key: 'apps' },
  ];

  const modeLabel =
    mode === 'universe' ? 'VIRTUAL UNIVERSE' : mode === 'test' ? 'SIMULATION' : 'LIVE';

  return (
    <div
      className="absolute top-0 left-0 right-0 z-20 px-2 pt-[max(0.5rem,var(--safe-top))] sm:px-4 sm:pt-4 pointer-events-none"
    >
      <div className="glass-panel pointer-events-auto max-w-[100vw] mx-auto overflow-hidden">
        {/* Title row — always visible */}
        <div className="flex items-center justify-between gap-2 px-3 py-2 sm:px-6 sm:py-3 border-b border-[#1a2332]/80 sm:border-0">
          <div className="flex items-center gap-2 sm:gap-3 min-w-0">
            <div
              className="text-lg sm:text-xl shrink-0"
              style={{ color: themeColor, textShadow: `0 0 10px ${themeColor}` }}
            >
              &#x25C9;
            </div>
            <div className="min-w-0">
              <div
                className="text-xs sm:text-sm font-semibold tracking-wider truncate"
                style={{ color: themeColor }}
              >
                ALIEN MONITOR
              </div>
              <div className="text-[9px] sm:text-[10px] font-mono opacity-50 truncate">
                {modeLabel}
              </div>
            </div>
          </div>
          {/* Compact chain stats on mobile */}
          <div className="flex items-center gap-2 sm:hidden shrink-0">
            {summary.mode === 'universe' && summary.blockchain_ready ? (
              <>
                <MiniStat label="BLK" value={`#${summary.block_number ?? '--'}`} color="#7b2fff" />
                <MiniStat label="TX" value={String(summary.onchain_tx_count ?? 0)} color="#00ff88" />
              </>
            ) : (
              <>
                <MiniStat
                  label="SOL"
                  value={summary.tps_solana ? `${(summary.tps_solana / 1000).toFixed(1)}k` : '--'}
                  color="#ff6633"
                />
                <MiniStat label="GAS" value={String(summary.gas_gwei ?? '--')} color="#ffdd00" />
              </>
            )}
          </div>
        </div>

        {/* Metrics — horizontal scroll on mobile, row on desktop */}
        <div className="metrics-scroll overflow-x-auto sm:overflow-visible">
          <div className="flex items-stretch gap-0 sm:gap-6 px-1 py-2 sm:px-6 sm:pb-3 min-w-min sm:justify-center">
            {metrics.map((m) => (
              <div
                key={m.key}
                className="flex flex-col items-center justify-center min-w-[4.5rem] sm:min-w-[70px] px-2 sm:px-0 shrink-0"
              >
                <div
                  className="text-base sm:text-lg font-mono font-bold tabular-nums"
                  style={{ color: themeColor }}
                >
                  {m.value}
                </div>
                <div className="text-[9px] sm:text-[10px] font-mono opacity-50 uppercase tracking-wider whitespace-nowrap">
                  {m.label}
                </div>
              </div>
            ))}

            {/* Desktop-only chain stats */}
            <div className="hidden sm:flex items-center gap-4 pl-4 border-l border-[#1a2332] shrink-0">
              {summary.mode === 'universe' && summary.blockchain_ready ? (
                <>
                  <ChainStat label="BLOCK" value={`#${summary.block_number?.toLocaleString() ?? '--'}`} color="#7b2fff" />
                  <ChainStat label="ON-CHAIN TX" value={String(summary.onchain_tx_count ?? 0)} color="#00ff88" />
                  <ChainStat label="GAS USED" value={summary.gas_gwei?.toLocaleString() ?? '--'} color="#ffdd00" />
                </>
              ) : (
                <>
                  <ChainStat
                    label="Solana TPS"
                    value={summary.tps_solana?.toLocaleString() ?? '--'}
                    color="#ff6633"
                  />
                  <ChainStat label="ETH Gas" value={`${summary.gas_gwei ?? '--'} GWEI`} color="#ffdd00" />
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function MiniStat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="flex flex-col items-end">
      <div className="text-[11px] font-mono font-bold" style={{ color }}>
        {value}
      </div>
      <div className="text-[8px] font-mono opacity-40">{label}</div>
    </div>
  );
}

function ChainStat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="flex flex-col items-center">
      <div className="text-sm font-mono" style={{ color }}>
        {value}
      </div>
      <div className="text-[10px] font-mono opacity-50">{label}</div>
    </div>
  );
}
