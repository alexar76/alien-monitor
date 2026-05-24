import { useEffect, useRef, useState } from 'react';
import type { Transaction, TxEvent } from '../App';

interface Props {
  transactions: Transaction[];
  events: TxEvent[];
  themeColor: string;
}

export default function TransactionFlow({ transactions, events, themeColor }: Props) {
  const [visible, setVisible] = useState(true);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = 0;
    }
  }, [transactions.length, events.length]);

  // Merge and sort by time (newest first)
  const allItems = [
    ...transactions.map((tx) => ({ ...tx, _type: 'tx' as const })),
    ...events.map((ev) => ({ ...ev, _type: 'event' as const })),
  ].sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime()).slice(0, 15);

  if (!visible) {
    return (
      <button
        onClick={() => setVisible(true)}
        className="absolute bottom-4 right-4 z-20 glass-panel px-3 py-1.5 text-xs font-mono"
        style={{ color: themeColor, borderColor: themeColor + '44' }}
      >
        Show Activity
      </button>
    );
  }

  return (
    <div className="absolute bottom-4 right-4 z-20 w-80 glass-panel" style={{ borderColor: themeColor + '44' }}>
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 py-2 border-b"
        style={{ borderColor: themeColor + '22' }}
      >
        <div className="flex items-center gap-2">
          <div
            className="w-1.5 h-1.5 rounded-full animate-pulse"
            style={{ backgroundColor: '#00ff88', boxShadow: '0 0 6px #00ff88' }}
          />
          <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: themeColor }}>
            Activity Stream
          </span>
          <span className="text-[10px] font-mono text-white/30">
            {allItems.length}
          </span>
        </div>
        <button
          onClick={() => setVisible(false)}
          className="text-white/30 hover:text-white/60 text-sm leading-none"
        >
          _
        </button>
      </div>

      {/* Items */}
      <div ref={listRef} className="overflow-y-auto" style={{ maxHeight: '180px' }}>
        {allItems.map((item, i) => {
          const isTx = item._type === 'tx';
          const tx = isTx ? (item as Transaction & { _type: string }) : null;
          const ev = !isTx ? (item as TxEvent & { _type: string }) : null;

          return (
            <div
              key={item.id}
              className="tx-enter px-3 py-1.5 flex items-center gap-2 text-[10px] font-mono border-b"
              style={{
                borderColor: '#ffffff06',
                animationDelay: `${i * 30}ms`,
              }}
            >
              {/* Icon */}
              <span style={{ color: isTx ? '#ffdd00' : themeColor }}>
                {isTx ? '↓' : '●'}
              </span>

              {/* Content */}
              <div className="flex-1 min-w-0">
                {isTx && tx ? (
                  <>
                    <span className="text-white/70">{tx.from}</span>
                    <span className="text-white/30 mx-1">→</span>
                    <span className="text-white/70">{tx.to}</span>
                  </>
                ) : ev ? (
                  <>
                    <span className="text-white/70">{ev.agent}</span>
                    <span className="text-white/40 mx-1">{ev.action}</span>
                    <span className="text-white/50">{ev.target}</span>
                  </>
                ) : null}
              </div>

              {/* Amount */}
              {item.amount > 0 && (
                <span
                  className="tabular-nums shrink-0"
                  style={{ color: item.amount > 5 ? '#00ff88' : '#ffffff50' }}
                >
                  ${item.amount.toFixed(2)}
                </span>
              )}

              {/* Token badge */}
              {item.token && (
                <span
                  className="text-[8px] px-1 rounded shrink-0"
                  style={{
                    backgroundColor: themeColor + '18',
                    color: themeColor,
                    border: `1px solid ${themeColor}33`,
                  }}
                >
                  {item.token}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
