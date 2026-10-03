import { useCallback, useEffect, useRef, useState } from 'react';
import { apiUrl } from '../api';
import { monitorAuthHeaders } from '../monitorAuth';
import { useI18n } from '../i18n';

interface Props {
  themeColor: string;
  realm: 'test' | 'real' | 'universe';
  onClose: () => void;
  mobile?: boolean;
  /** Open straight onto one address, for "view transactions" on a node's declared
   *  escrow or wallet. Without it the scanner opens on the recent-blocks list. */
  initialAddress?: string;
}

interface TxRow {
  hash: string;
  block: number;
  timestamp: number;
  from: string;
  from_label: string;
  to: string | null;
  to_label: string;
  value_wei: string;
  method: string;
  input_bytes: number;
  direction?: 'in' | 'out';
}

/** WHICH chain these rows come from — the backend's chain-source policy, verbatim. */
interface NetworkInfo {
  source: 'uni-bubble' | 'settings-network';
  realm: string;
  mode: string;
  crypto_enabled: boolean;
  chain: string;
  name: string;
  chain_id: number | null;
}

interface ScanList {
  chain_id: number | null;
  head: number | null;
  network?: NetworkInfo | null;
  txs: TxRow[];
  scanned_blocks: number;
  note: string;
  /** Set when the RPC answers as a different chain than this monitor advertises. */
  chain_mismatch: { declared_chain: string; declared_chain_id: number;
                    observed_chain_id: number; message: string } | null;
}

interface TxDetail extends TxRow {
  found: boolean;
  network?: NetworkInfo | null;
  nonce: number;
  status: number | null;
  gas_used: number;
  gas_limit: number;
  effective_gas_price_wei: string;
  contract_deployed: string | null;
  logs: { address: string; address_label: string; event: string; topics: number; data_bytes: number }[];
  input: string;
  note: string;
}

interface AddressView {
  found: boolean;
  address: string;
  network?: NetworkInfo | null;
  label: string;
  balance_wei: string;
  nonce: number;
  is_contract: boolean;
  code_size: number;
  txs: TxRow[];
  note: string;
}

/** wei (as a decimal string) -> a short human ETH figure, without floating-point drift. */
function weiToEth(wei: string): string {
  let v: bigint;
  try {
    v = BigInt(wei || '0');
  } catch {
    return '0';
  }
  if (v === 0n) return '0';
  const whole = v / 10n ** 18n;
  const frac = (v % 10n ** 18n).toString().padStart(18, '0').slice(0, 6).replace(/0+$/, '');
  return frac ? `${whole}.${frac}` : `${whole}`;
}

function shortHex(h: string | null | undefined, head = 6, tail = 4): string {
  if (!h) return '—';
  return h.length > head + tail + 2 ? `${h.slice(0, head)}…${h.slice(-tail)}` : h;
}

/** A named party shows its name; an unnamed one shows a short hex. Never a guessed name. */
function party(addr: string | null, label: string): string {
  if (label) return label;
  return shortHex(addr);
}

async function getJson<T>(path: string): Promise<T | null> {
  try {
    const r = await fetch(apiUrl(path), {
      credentials: 'same-origin',
      headers: monitorAuthHeaders(),
    });
    if (!r.ok) return null;
    return (await r.json()) as T;
  } catch {
    return null;
  }
}

type View = { kind: 'list' } | { kind: 'tx'; hash: string } | { kind: 'address'; address: string };

export default function ChainScanner({ themeColor, realm, onClose, mobile = false, initialAddress }: Props) {
  const { t } = useI18n();
  const [view, setView] = useState<View>(
    initialAddress && /^0x[0-9a-fA-F]{40}$/.test(initialAddress)
      ? { kind: 'address', address: initialAddress }
      : { kind: 'list' },
  );
  const [list, setList] = useState<ScanList | null>(null);
  const [tx, setTx] = useState<TxDetail | null>(null);
  const [addr, setAddr] = useState<AddressView | null>(null);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState('');
  const pollRef = useRef<number | null>(null);

  const realmLabel = realm === 'universe' ? 'UNI' : realm === 'test' ? 'TEST' : 'LIVE';
  // Every payload carries the same provenance block, so the badge survives the detail views.
  const net: NetworkInfo | null = list?.network || tx?.network || addr?.network || null;
  // A private bubble chain and a real network must not look alike at a glance.
  const netColor = net?.source === 'settings-network' ? '#00ff88' : '#a78bfa';

  const loadList = useCallback(async () => {
    const data = await getJson<ScanList>('/api/chain/scan?limit=40');
    if (data) setList(data);
  }, []);

  // List view polls; detail views are a snapshot the reader chose to inspect, so they don't.
  useEffect(() => {
    if (view.kind !== 'list') return;
    let alive = true;
    (async () => {
      setLoading(true);
      await loadList();
      if (alive) setLoading(false);
    })();
    pollRef.current = window.setInterval(loadList, 5000);
    return () => {
      alive = false;
      if (pollRef.current) window.clearInterval(pollRef.current);
    };
  }, [view.kind, loadList]);

  useEffect(() => {
    if (view.kind !== 'tx') return;
    let alive = true;
    (async () => {
      setLoading(true);
      setTx(null);
      const data = await getJson<TxDetail>(`/api/chain/tx/${view.hash}`);
      if (alive) {
        setTx(data);
        setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [view]);

  useEffect(() => {
    if (view.kind !== 'address') return;
    let alive = true;
    (async () => {
      setLoading(true);
      setAddr(null);
      const data = await getJson<AddressView>(`/api/chain/address/${view.address}?limit=40`);
      if (alive) {
        setAddr(data);
        setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [view]);

  const submitSearch = useCallback(() => {
    const q = query.trim();
    if (/^0x[0-9a-fA-F]{64}$/.test(q)) setView({ kind: 'tx', hash: q });
    else if (/^0x[0-9a-fA-F]{40}$/.test(q)) setView({ kind: 'address', address: q });
  }, [query]);

  const methodColor = (m: string): string => {
    if (/^0x/.test(m) || m === 'send') return '#ffffff55';
    if (m === 'deploy') return '#ffdd00';
    if (/debit|settle|refund|transfer|mint|burn/.test(m)) return '#00ff88';
    return themeColor;
  };

  const wrapClass = mobile
    ? 'fixed inset-x-0 bottom-0 w-full mobile-sheet overflow-hidden z-40'
    : 'absolute right-4 top-20 bottom-4 w-[420px] z-40 flex flex-col';

  const clickableAddr = (address: string | null, label: string) =>
    address ? (
      <button
        type="button"
        onClick={() => setView({ kind: 'address', address })}
        className="font-mono hover:underline"
        style={{ color: label ? themeColor : '#ffffffaa' }}
        title={address}
      >
        {party(address, label)}
      </button>
    ) : (
      <span className="text-white/40">—</span>
    );

  return (
    <div className={`glass-panel animate-slide-up ${wrapClass}`} style={{ borderColor: themeColor + '44' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b shrink-0" style={{ borderColor: themeColor + '22' }}>
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm" style={{ color: themeColor }} aria-hidden>◈</span>
          <span className="text-xs font-semibold tracking-wider" style={{ color: themeColor }}>
            {t('scanner.title', undefined, 'CHAIN SCANNER')}
          </span>
          <span
            className="text-[9px] font-mono px-1.5 py-0.5 rounded uppercase tracking-wider shrink-0"
            style={{ color: themeColor, border: `1px solid ${themeColor}44` }}
          >
            {realmLabel}
          </span>
        </div>
        <button
          onClick={onClose}
          className="text-white/40 hover:text-white/80 transition-colors text-2xl leading-none w-10 h-10 flex items-center justify-center shrink-0"
          aria-label="close"
        >
          ×
        </button>
      </div>

      {/* Chain status strip — the network badge first: whose transactions these are is the
          one thing a reader must not have to infer from a bare chain id. */}
      <div className="px-4 py-1.5 text-[9px] font-mono text-white/40 border-b flex items-center gap-3 shrink-0 flex-wrap" style={{ borderColor: themeColor + '12' }}>
        {net && (
          <span className="flex items-center gap-1.5">
            <span className="text-white/30">{t('scanner.showing', undefined, 'SHOWING')}</span>
            <span
              className="px-1.5 py-0.5 rounded uppercase tracking-wider font-semibold"
              style={{ color: netColor, border: `1px solid ${netColor}55`, background: netColor + '14' }}
            >
              {net.name}{net.chain_id ? ` · ${net.chain_id}` : ''}
            </span>
          </span>
        )}
        <span>{t('scanner.chain', undefined, 'CHAIN')} <span className="text-white/70">{list?.chain_id ?? '—'}</span></span>
        <span>{t('scanner.head', undefined, 'HEAD')} <span className="text-white/70">#{list?.head ?? '—'}</span></span>
        {loading && <span className="ml-auto inline-block w-2.5 h-2.5 rounded-full border-2 animate-spin" style={{ borderColor: themeColor, borderTopColor: 'transparent' }} />}
      </div>

      {/* Crypto is off in settings, so a LIVE monitor deliberately shows the bubble's chain
          rather than an empty explorer. Deliberate ⇒ stated, not dressed up as an error. */}
      {net?.source === 'uni-bubble' && realm !== 'universe' && (
        <div
          className="px-4 py-1.5 text-[9px] font-mono border-b shrink-0"
          style={{ borderColor: themeColor + '22', background: themeColor + '0d', color: themeColor }}
          role="note"
        >
          ◇ {t('scanner.uniFallback', undefined,
            'crypto is off in settings — showing the UNI bubble chain, not the live network')}
        </div>
      )}

      {/* The chain the RPC answers as is not the one this monitor advertises. Both numbers
          were always in the payload; showing only the friendly name is how a "Base" header
          ended up over a local Anvil. */}
      {list?.chain_mismatch && (
        <div
          className="px-4 py-1.5 text-[9px] font-mono text-amber-300/90 border-b shrink-0"
          style={{ borderColor: '#ffbf0033', background: '#ffbf000f' }}
          role="status"
        >
          ⚠ {t('scanner.mismatch', {
            observed: String(list.chain_mismatch.observed_chain_id),
            declared: String(list.chain_mismatch.declared_chain_id),
            chain: list.chain_mismatch.declared_chain.toUpperCase(),
          }, `chain ${list.chain_mismatch.observed_chain_id} is not ${list.chain_mismatch.declared_chain.toUpperCase()} (${list.chain_mismatch.declared_chain_id}) — this panel is not showing that network`)}
        </div>
      )}

      {/* Search */}
      <div className="px-3 py-2 border-b shrink-0" style={{ borderColor: themeColor + '12' }}>
        <div className="flex items-center gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submitSearch()}
            placeholder={t('scanner.search', undefined, 'tx hash / address')}
            className="flex-1 min-w-0 bg-black/30 rounded px-2 py-1.5 text-[10px] font-mono text-white/80 outline-none border"
            style={{ borderColor: themeColor + '22' }}
          />
          <button
            type="button"
            onClick={submitSearch}
            className="text-[10px] font-mono px-2 py-1.5 rounded shrink-0"
            style={{ color: themeColor, border: `1px solid ${themeColor}44` }}
          >
            {t('scanner.go', undefined, 'GO')}
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="overflow-y-auto flex-1" style={{ maxHeight: mobile ? 'min(52vh, 360px)' : undefined }}>
        {/* Back control for detail views */}
        {view.kind !== 'list' && (
          <button
            type="button"
            onClick={() => setView({ kind: 'list' })}
            className="w-full text-left px-4 py-2 text-[10px] font-mono text-white/50 hover:text-white/80 border-b"
            style={{ borderColor: themeColor + '12' }}
          >
            ← {t('scanner.back', undefined, 'all transactions')}
          </button>
        )}

        {/* LIST VIEW */}
        {view.kind === 'list' && (
          <>
            {list && list.note && (
              <div className="px-4 py-3 text-[10px] font-mono text-amber-200/80">{list.note}</div>
            )}
            {list && !list.note && list.txs.length === 0 && (
              <div className="px-4 py-6 text-[10px] font-mono text-white/40 text-center">
                {t('scanner.empty', undefined, 'no transactions in the recent blocks')}
              </div>
            )}
            {list?.txs.map((row) => (
              <button
                key={row.hash}
                type="button"
                onClick={() => setView({ kind: 'tx', hash: row.hash })}
                className="w-full text-left px-3 py-2 flex items-center gap-2 text-[10px] font-mono border-b hover:bg-white/5"
                style={{ borderColor: '#ffffff08' }}
              >
                <span className="text-white/30 shrink-0 w-12">#{row.block}</span>
                <span
                  className="shrink-0 px-1 rounded uppercase text-[8px]"
                  style={{ color: methodColor(row.method), border: `1px solid ${methodColor(row.method)}33` }}
                >
                  {row.method}
                </span>
                <span className="flex-1 min-w-0 truncate text-white/60">
                  {party(row.from, row.from_label)} <span className="text-white/25">→</span> {party(row.to, row.to_label)}
                </span>
                {row.value_wei !== '0' && (
                  <span className="shrink-0 text-[#00ff88]">{weiToEth(row.value_wei)}</span>
                )}
              </button>
            ))}
          </>
        )}

        {/* TX DETAIL VIEW */}
        {view.kind === 'tx' && (
          <div className="px-4 py-3 space-y-2 text-[10px] font-mono">
            {tx && tx.found ? (
              <>
                <Row label={t('scanner.hash', undefined, 'HASH')}>
                  <span className="text-white/70 break-all" title={tx.hash}>{tx.hash}</span>
                </Row>
                <Row label={t('scanner.status', undefined, 'STATUS')}>
                  {tx.status === 1 ? (
                    <span className="text-[#00ff88]">✔ {t('scanner.success', undefined, 'SUCCESS')}</span>
                  ) : tx.status === 0 ? (
                    <span className="text-[#ff4d5e]">✖ {t('scanner.reverted', undefined, 'REVERTED')}</span>
                  ) : (
                    <span className="text-amber-300/80">• {t('scanner.pending', undefined, 'PENDING')}</span>
                  )}
                </Row>
                <Row label={t('scanner.block', undefined, 'BLOCK')}><span className="text-white/70">#{tx.block}</span></Row>
                <Row label={t('scanner.method', undefined, 'METHOD')}>
                  <span style={{ color: methodColor(tx.method) }}>{tx.method}</span>
                </Row>
                <Row label={t('scanner.from', undefined, 'FROM')}>{clickableAddr(tx.from, tx.from_label)}</Row>
                <Row label={t('scanner.to', undefined, 'TO')}>
                  {tx.contract_deployed
                    ? clickableAddr(tx.contract_deployed, 'DEPLOYED')
                    : clickableAddr(tx.to, tx.to_label)}
                </Row>
                <Row label={t('scanner.value', undefined, 'VALUE')}>
                  <span className="text-white/70">{weiToEth(tx.value_wei)}</span>
                </Row>
                <Row label={t('scanner.gas', undefined, 'GAS USED')}>
                  <span className="text-white/70">{tx.gas_used.toLocaleString()} / {tx.gas_limit.toLocaleString()}</span>
                </Row>
                <Row label={t('scanner.nonce', undefined, 'NONCE')}><span className="text-white/70">{tx.nonce}</span></Row>
                {tx.input && tx.input !== '0x' && (
                  <Row label={t('scanner.input', undefined, 'INPUT')}>
                    <span className="text-white/40 break-all">{tx.input}{tx.input_bytes > (tx.input.length - 2) / 2 ? '…' : ''}</span>
                  </Row>
                )}
                <div className="pt-1 text-white/40 uppercase tracking-wider">
                  {t('scanner.logs', undefined, 'LOGS')} ({tx.logs.length})
                </div>
                {tx.logs.map((lg, i) => (
                  <div key={i} className="pl-2 border-l" style={{ borderColor: themeColor + '33' }}>
                    <span style={{ color: themeColor }}>{lg.event}</span>
                    <span className="text-white/30"> @ </span>
                    {clickableAddr(lg.address, lg.address_label)}
                    <span className="text-white/25"> · {lg.topics} topics · {lg.data_bytes}B</span>
                  </div>
                ))}
              </>
            ) : (
              !loading && (
                <div className="text-white/40 py-4">
                  {tx?.note || t('scanner.notFound', undefined, 'not found on this chain')}
                </div>
              )
            )}
          </div>
        )}

        {/* ADDRESS VIEW */}
        {view.kind === 'address' && (
          <div className="text-[10px] font-mono">
            {addr && addr.found ? (
              <>
                <div className="px-4 py-3 space-y-2 border-b" style={{ borderColor: themeColor + '12' }}>
                  <Row label={t('scanner.address', undefined, 'ADDRESS')}>
                    <span className="text-white/70 break-all" title={addr.address}>{addr.address}</span>
                  </Row>
                  {addr.label && (
                    <Row label={t('scanner.name', undefined, 'NAME')}><span style={{ color: themeColor }}>{addr.label}</span></Row>
                  )}
                  <Row label={t('scanner.kind', undefined, 'KIND')}>
                    <span className="text-white/70">
                      {addr.is_contract
                        ? `${t('scanner.contract', undefined, 'CONTRACT')} · ${addr.code_size.toLocaleString()}B`
                        : t('scanner.wallet', undefined, 'WALLET')}
                    </span>
                  </Row>
                  <Row label={t('scanner.balance', undefined, 'BALANCE')}><span className="text-[#00ff88]">{weiToEth(addr.balance_wei)}</span></Row>
                  <Row label={t('scanner.nonce', undefined, 'NONCE')}><span className="text-white/70">{addr.nonce}</span></Row>
                </div>
                <div className="px-4 py-1.5 text-white/40 uppercase tracking-wider">
                  {t('scanner.recentTxs', undefined, 'recent transactions')} ({addr.txs.length})
                </div>
                {addr.txs.map((row) => (
                  <button
                    key={row.hash}
                    type="button"
                    onClick={() => setView({ kind: 'tx', hash: row.hash })}
                    className="w-full text-left px-3 py-2 flex items-center gap-2 border-b hover:bg-white/5"
                    style={{ borderColor: '#ffffff08' }}
                  >
                    <span
                      className="shrink-0 px-1 rounded uppercase text-[8px]"
                      style={{
                        color: row.direction === 'out' ? '#ff9d4d' : '#00ff88',
                        border: `1px solid ${row.direction === 'out' ? '#ff9d4d' : '#00ff88'}33`,
                      }}
                    >
                      {row.direction === 'out' ? t('scanner.out', undefined, 'OUT') : t('scanner.in', undefined, 'IN')}
                    </span>
                    <span className="text-white/30 shrink-0 w-10">#{row.block}</span>
                    <span style={{ color: methodColor(row.method) }} className="shrink-0">{row.method}</span>
                    <span className="flex-1 min-w-0 truncate text-white/50 text-right">
                      {party(row.to, row.to_label)}
                    </span>
                  </button>
                ))}
              </>
            ) : (
              !loading && (
                <div className="text-white/40 px-4 py-4">
                  {addr?.note || t('scanner.notFound', undefined, 'not found on this chain')}
                </div>
              )
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-2">
      <span className="text-white/35 uppercase tracking-wider shrink-0 w-20">{label}</span>
      <span className="flex-1 min-w-0">{children}</span>
    </div>
  );
}
