import { useCallback, useEffect, useRef, useState } from 'react';
import { apiUrl } from '../api';
import { monitorAuthHeaders } from '../monitorAuth';
import { useI18n } from '../i18n';

export type RosterSort = 'last_seen' | 'name' | 'version' | 'spend' | 'economy';
export type RosterStatus = '' | 'active' | 'idle' | 'offline';

export interface ArgusInstance {
  instance_id: string;
  display_name: string;
  wallet: string;
  wallet_short: string;
  wallets?: { address: string; chain: string; short: string }[];
  version: string;
  mode: string;
  modes?: string[];
  economy: string;
  host: string;
  status: 'active' | 'idle' | 'offline' | string;
  last_seen: string;
  last_seen_age_s: number;
  spend_usd: number;
  runs: number;
  last_run_id: string;
  has_run: boolean;
  last_run?: {
    id: string;
    goal: string;
    beats: unknown[];
    spendUsd: number;
    receiptHash: string;
    signer: string;
    verifyUrl?: string;
  };
}

interface RosterPage {
  instances: ArgusInstance[];
  total: number;
  active: number;
  economy_on: number;
  next_cursor: string;
  has_more: boolean;
}

const SORTS: { id: RosterSort; labelKey: string; fallback: string }[] = [
  { id: 'last_seen', labelKey: 'argus.roster.sortSeen', fallback: 'Last seen' },
  { id: 'name', labelKey: 'argus.roster.sortName', fallback: 'Name' },
  { id: 'spend', labelKey: 'argus.roster.sortSpend', fallback: 'Spend' },
  { id: 'economy', labelKey: 'argus.roster.sortEconomy', fallback: 'Economy' },
  { id: 'version', labelKey: 'argus.roster.sortVersion', fallback: 'Version' },
];

function statusColor(s: string): string {
  if (s === 'active') return '#00ff88';
  if (s === 'idle') return '#ffaa00';
  return '#667788';
}

function fmtAge(s: number, t: (k: string, p?: Record<string, string | number>, f?: string) => string): string {
  if (s < 60) return t('argus.roster.ageSec', { n: s }, `${s}s ago`);
  if (s < 3600) return t('argus.roster.ageMin', { n: Math.floor(s / 60) }, `${Math.floor(s / 60)}m ago`);
  if (s < 86400) return t('argus.roster.ageHr', { n: Math.floor(s / 3600) }, `${Math.floor(s / 3600)}h ago`);
  return t('argus.roster.ageDay', { n: Math.floor(s / 86400) }, `${Math.floor(s / 86400)}d ago`);
}

function fmtUsd(v: number): string {
  if (!v) return '$0';
  if (v < 0.01) return `$${v.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')}`;
  if (v < 1) return `$${v.toFixed(2)}`;
  return `$${v.toFixed(2)}`;
}

interface Props {
  themeColor: string;
  onSelect: (inst: ArgusInstance) => void;
  selectedId?: string | null;
}

export default function ArgusRoster({ themeColor, onSelect, selectedId }: Props) {
  const { t } = useI18n();
  const [q, setQ] = useState('');
  const [qDebounced, setQDebounced] = useState('');
  const [sort, setSort] = useState<RosterSort>('last_seen');
  const [status, setStatus] = useState<RosterStatus>('');
  const [items, setItems] = useState<ArgusInstance[]>([]);
  const [meta, setMeta] = useState({ total: 0, active: 0, economy_on: 0 });
  const [cursor, setCursor] = useState('');
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const abortRef = useRef<AbortController | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const id = setTimeout(() => setQDebounced(q.trim()), 280);
    return () => clearTimeout(id);
  }, [q]);

  const load = useCallback(
    async (opts: { append: boolean; cursor?: string }) => {
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;
      setLoading(true);
      setErr('');
      try {
        const params = new URLSearchParams({
          limit: '40',
          sort,
        });
        if (qDebounced) params.set('q', qDebounced);
        if (status) params.set('status', status);
        if (opts.cursor) params.set('cursor', opts.cursor);
        const res = await fetch(apiUrl(`/api/argus/instances?${params}`), {
          headers: monitorAuthHeaders(),
          signal: ac.signal,
          cache: 'no-store',
        });
        if (!res.ok) throw new Error(`${res.status}`);
        const data = (await res.json()) as RosterPage;
        setMeta({
          total: data.total ?? 0,
          active: data.active ?? 0,
          economy_on: data.economy_on ?? 0,
        });
        setHasMore(!!data.has_more);
        setCursor(data.next_cursor || '');
        setItems((prev) => (opts.append ? [...prev, ...(data.instances || [])] : data.instances || []));
      } catch (e) {
        if ((e as Error).name === 'AbortError') return;
        setErr(String((e as Error).message || e));
        if (!opts.append) setItems([]);
      } finally {
        setLoading(false);
      }
    },
    [qDebounced, sort, status],
  );

  useEffect(() => {
    void load({ append: false });
    return () => abortRef.current?.abort();
  }, [load]);

  const onScroll = () => {
    const el = listRef.current;
    if (!el || loading || !hasMore) return;
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 48) {
      void load({ append: true, cursor });
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="text-[10px] font-mono text-white/45 uppercase tracking-wider">
          {t('argus.roster.title', undefined, 'Connected agents')}
        </div>
        <div className="flex items-center gap-1.5 text-[9px] font-mono">
          <span style={{ color: '#00ff88' }}>
            {meta.active} {t('argus.roster.active', undefined, 'active')}
          </span>
          <span className="text-white/25">·</span>
          <span className="text-white/50">
            {meta.total} {t('argus.roster.total', undefined, 'total')}
          </span>
          {meta.economy_on > 0 && (
            <>
              <span className="text-white/25">·</span>
              <span style={{ color: '#00ff88' }}>
                {meta.economy_on} {t('argus.roster.economyOn', undefined, 'economy')}
              </span>
            </>
          )}
        </div>
      </div>

      <div className="flex gap-1.5">
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t('argus.roster.search', undefined, 'Search name, wallet, id…')}
          className="flex-1 min-w-0 rounded-lg px-2.5 py-1.5 text-[11px] font-mono bg-black/40 text-white/85 outline-none"
          style={{ border: `1px solid ${themeColor}33` }}
        />
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as RosterSort)}
          className="rounded-lg px-2 py-1.5 text-[10px] font-mono bg-black/40 text-white/70 outline-none max-w-[7.5rem]"
          style={{ border: `1px solid ${themeColor}33` }}
          aria-label={t('argus.roster.sort', undefined, 'Sort')}
        >
          {SORTS.map((s) => (
            <option key={s.id} value={s.id}>
              {t(s.labelKey, undefined, s.fallback)}
            </option>
          ))}
        </select>
      </div>

      <div className="flex gap-1 flex-wrap">
        {(['', 'active', 'idle', 'offline'] as RosterStatus[]).map((s) => {
          const on = status === s;
          const label =
            s === ''
              ? t('argus.roster.filterAll', undefined, 'All')
              : s === 'active'
                ? t('argus.roster.filterActive', undefined, 'Active')
                : s === 'idle'
                  ? t('argus.roster.filterIdle', undefined, 'Idle')
                  : t('argus.roster.filterOffline', undefined, 'Offline');
          return (
            <button
              key={s || 'all'}
              type="button"
              onClick={() => setStatus(s)}
              className="text-[9px] font-mono uppercase px-2 py-0.5 rounded tracking-wider"
              style={{
                color: on ? themeColor : '#8899aa',
                backgroundColor: on ? themeColor + '22' : 'transparent',
                border: `1px solid ${on ? themeColor + '55' : '#ffffff18'}`,
              }}
            >
              {label}
            </button>
          );
        })}
      </div>

      <div
        ref={listRef}
        onScroll={onScroll}
        className="max-h-[min(42vh,280px)] overflow-y-auto rounded-xl space-y-1 pr-0.5"
        style={{ border: `1px solid ${themeColor}18` }}
      >
        {err && (
          <div className="p-3 text-[10px] font-mono text-rose-400">
            {t('argus.roster.error', undefined, 'Failed to load roster')}: {err}
          </div>
        )}
        {!err && !loading && items.length === 0 && (
          <div className="p-4 text-center text-[10px] font-mono text-white/35">
            {t(
              'argus.roster.empty',
              undefined,
              'No agents yet — heartbeats appear here when ARGUS connects.',
            )}
          </div>
        )}
        {items.map((inst) => {
          const selected = selectedId === inst.instance_id;
          const sc = statusColor(inst.status);
          const modes = (inst.modes && inst.modes.length ? inst.modes : inst.mode ? [inst.mode] : []) as string[];
          const wallets = inst.wallets?.length
            ? inst.wallets
            : inst.wallet_short
              ? [{ address: inst.wallet, chain: modes[0] || 'live', short: inst.wallet_short }]
              : [];
          return (
            <button
              key={inst.instance_id}
              type="button"
              onClick={() => onSelect(inst)}
              className="w-full text-left px-2.5 py-2 rounded-lg transition-colors"
              style={{
                backgroundColor: selected ? themeColor + '18' : 'transparent',
                borderLeft: `2px solid ${selected ? themeColor : 'transparent'}`,
              }}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 min-w-0 flex-wrap">
                    <span
                      className="w-1.5 h-1.5 rounded-full shrink-0"
                      style={{ backgroundColor: sc, boxShadow: `0 0 6px ${sc}` }}
                      aria-hidden
                    />
                    <span className="text-[11px] font-semibold text-white/90 truncate">
                      {inst.display_name}
                    </span>
                    {modes.map((m) => (
                      <span
                        key={m}
                        className="text-[8px] font-mono uppercase px-1 rounded shrink-0"
                        style={{
                          color: m === 'uni' ? '#c4a0ff' : m === 'live' || m === 'real' ? '#00f0ff' : '#8899aa',
                          border: `1px solid ${m === 'uni' ? '#c4a0ff44' : m === 'live' || m === 'real' ? '#00f0ff44' : '#ffffff22'}`,
                        }}
                      >
                        {m === 'real' ? 'live' : m}
                      </span>
                    ))}
                    {inst.economy === 'on' && (
                      <span
                        className="text-[8px] font-mono uppercase px-1 rounded shrink-0"
                        style={{ color: '#00ff88', border: '1px solid #00ff8844' }}
                      >
                        $
                      </span>
                    )}
                  </div>
                  <div className="text-[9px] font-mono text-white/35 truncate mt-0.5">
                    {wallets.length > 1
                      ? wallets.map((w) => `${(w.chain || 'live').toUpperCase()} ${w.short}`).join(' · ')
                      : wallets[0]?.short || inst.wallet_short || inst.instance_id}
                    {inst.version ? ` · v${inst.version}` : ''}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div className="text-[9px] font-mono text-white/55">{fmtUsd(inst.spend_usd)}</div>
                  <div className="text-[8px] font-mono text-white/30">
                    {fmtAge(inst.last_seen_age_s, t)}
                  </div>
                </div>
              </div>
            </button>
          );
        })}
        {loading && (
          <div className="p-2 text-center text-[9px] font-mono text-white/30">
            {t('argus.roster.loading', undefined, 'Loading…')}
          </div>
        )}
        {!loading && hasMore && (
          <button
            type="button"
            onClick={() => void load({ append: true, cursor })}
            className="w-full py-2 text-[9px] font-mono uppercase tracking-wider text-white/40 hover:text-white/70"
          >
            {t('argus.roster.more', undefined, 'Load more')}
          </button>
        )}
      </div>
    </div>
  );
}
