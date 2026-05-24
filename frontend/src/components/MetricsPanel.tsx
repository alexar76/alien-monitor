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

    // Animate toward targets
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
      <div className="absolute top-0 left-0 right-0 z-20 p-4">
        <div className="glass-panel px-6 py-3 flex items-center justify-center">
          <span className="text-sm font-mono opacity-60">Connecting to ecosystem...</span>
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

  return (
    <div className="absolute top-0 left-0 right-0 z-20 p-4 flex justify-center">
      <div className="glass-panel px-6 py-3 flex items-center gap-8">
        {/* Title */}
        <div className="flex items-center gap-3 mr-4">
          <div
            className="text-xl"
            style={{ color: themeColor, textShadow: `0 0 10px ${themeColor}` }}
          >
            &#x25C9;
          </div>
          <div>
            <div className="text-sm font-semibold tracking-wider" style={{ color: themeColor }}>
              ALIEN MONITOR
            </div>
            <div className="text-[10px] font-mono opacity-50">
              {mode === 'universe' ? 'VIRTUAL UNIVERSE' : mode === 'test' ? 'SIMULATION' : 'LIVE'}
            </div>
          </div>
        </div>

        {/* Metrics */}
        <div className="flex items-center gap-6">
          {metrics.map((m) => (
            <div key={m.key} className="flex flex-col items-center min-w-[70px]">
              <div
                className="text-lg font-mono font-bold tabular-nums"
                style={{ color: themeColor }}
              >
                {m.value}
              </div>
              <div className="text-[10px] font-mono opacity-50 uppercase tracking-wider">
                {m.label}
              </div>
            </div>
          ))}
        </div>

        {/* Divider + TPS / Gas / Blockchain analytics */}
        <div className="flex items-center gap-4 pl-4 border-l border-[#1a2332]">
          {summary.mode === 'universe' && summary.blockchain_ready ? (
            <>
              <div className="flex flex-col items-center">
                <div className="text-sm font-mono text-[#7b2fff]">
                  #{summary.block_number?.toLocaleString() ?? '--'}
                </div>
                <div className="text-[10px] font-mono opacity-50">BLOCK</div>
              </div>
              <div className="flex flex-col items-center">
                <div className="text-sm font-mono text-[#00ff88]">
                  {summary.onchain_tx_count ?? 0}
                </div>
                <div className="text-[10px] font-mono opacity-50">ON-CHAIN TX</div>
              </div>
              <div className="flex flex-col items-center">
                <div className="text-sm font-mono text-[#ffdd00]">
                  {summary.gas_gwei?.toLocaleString() ?? '--'}
                </div>
                <div className="text-[10px] font-mono opacity-50">GAS USED</div>
              </div>
            </>
          ) : (
            <>
              <div className="flex flex-col items-center">
                <div className="text-sm font-mono text-[#ff6633]">
                  {summary.tps_solana?.toLocaleString() ?? '--'}
                </div>
                <div className="text-[10px] font-mono opacity-50">Solana TPS</div>
              </div>
              <div className="flex flex-col items-center">
                <div className="text-sm font-mono text-[#ffdd00]">
                  {summary.gas_gwei ?? '--'} GWEI
                </div>
                <div className="text-[10px] font-mono opacity-50">ETH Gas</div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
