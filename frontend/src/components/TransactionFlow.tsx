import { useEffect, useRef, useState } from 'react';
import type { Transaction, TxEvent } from '../App';
import { useIsMobile } from '../hooks/useIsMobile';

interface Props {
  transactions: Transaction[];
  events: TxEvent[];
  themeColor: string;
}

export default function TransactionFlow({ transactions, events, themeColor }: Props) {
  const isMobile = useIsMobile();
  const [visible, setVisible] = useState(!isMobile);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = 0;
    }
  }, [transactions.length, events.length]);

  const allItems = [
    ...transactions.map((tx) => ({ ...tx, _type: 'tx' as const })),
    ...events.map((ev) => ({ ...ev, _type: 'event' as const })),
  ]
    .sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime())
    .slice(0, 15);

  if (!visible) {
    return (
      <button
        onClick={() => setVisible(true)}
        className="
          absolute z-20 glass-panel px-3 py-2 text-xs font-mono
          left-1/2 -translate-x-1/2 bottom-[calc(4.5rem+var(--safe-bottom))] sm:left-auto sm:translate-x-0 sm:right-4 sm:bottom-4
        "
        style={{ color: themeColor, borderColor: themeColor + '44' }}
      >
        Show Activity ({allItems.length})
      </button>
    );
  }

  return (
    <div
      className="
        absolute z-20 glass-panel overflow-hidden
        left-2 right-2 bottom-[calc(4.75rem+var(--safe-bottom))]
        max-h-[28dvh] sm:max-h-none
        sm:left-auto sm:right-4 sm:bottom-4 sm:w-80
      "
      style={{ borderColor: themeColor + '44' }}
    >
      <div
        className="flex items-center justify-between px-3 py-2 border-b shrink-0"
        style={{ borderColor: themeColor + '22' }}
      >
        <div className="flex items-center gap-2 min-w-0">
          <div
            className="w-1.5 h-1.5 rounded-full animate-pulse shrink-0"
            style={{ backgroundColor: '#00ff88', boxShadow: '0 0 6px #00ff88' }}
          />
          <span
            className="text-[10px] font-mono uppercase tracking-wider truncate"
            style={{ color: themeColor }}
          >
            Activity Stream
          </span>
          <span className="text-[10px] font-mono text-white/30 shrink-0">{allItems.length}</span>
        </div>
        <button
          onClick={() => setVisible(false)}
          className="text-white/30 hover:text-white/60 text-sm leading-none w-8 h-8 flex items-center justify-center"
          aria-label="Collapse activity"
        >
          _
        </button>
      </div>

      <div
        ref={listRef}
        className="overflow-y-auto"
        style={{ maxHeight: isMobile ? 'calc(28dvh - 2.5rem)' : '180px' }}
      >
        {allItems.map((item, i) => {
          const isTx = item._type === 'tx';
          const tx = isTx ? (item as Transaction & { _type: string }) : null;
          const ev = !isTx ? (item as TxEvent & { _type: string }) : null;

          return (
            <div
              key={item.id}
              className="tx-enter px-3 py-2 sm:py-1.5 flex items-center gap-2 text-[10px] font-mono border-b"
              style={{
                borderColor: '#ffffff06',
                animationDelay: `${i * 30}ms`,
              }}
            >
              <span style={{ color: isTx ? '#ffdd00' : themeColor }}>{isTx ? '↓' : '●'}</span>

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
                    <span className="text-white/50 truncate">{ev.target}</span>
                  </>
                ) : null}
              </div>

              {item.amount > 0 && (
                <span
                  className="tabular-nums shrink-0"
                  style={{ color: item.amount > 5 ? '#00ff88' : '#ffffff50' }}
                >
                  ${item.amount.toFixed(2)}
                </span>
              )}

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
