import type { EcoNode } from '../../App';

interface Props {
  node: EcoNode;
  themeColor: string;
  mobile?: boolean;
  t: (key: string, vars?: Record<string, string | number>, defaultValue?: string) => string;
}

const STONE = '#e8c36a';

/** Highest advisory scores first — that is the order the detectors will run in. */
function topCategories(scores: Record<string, number> | undefined): [string, number][] {
  if (!scores) return [];
  return Object.entries(scores)
    .filter(([, v]) => typeof v === 'number' && Number.isFinite(v))
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6);
}

/**
 * The touchstone panel: what the agent KNOWS, never what it decided.
 *
 * A verdict belongs to one signed pack from one paid scan, and the monitor runs none —
 * so this card shows identity, the memo store and the allowlisted advisory cards, and
 * says plainly where a verdict actually comes from.
 */
export default function BasanosCard({ node, themeColor, t }: Props) {
  const live = node.basanos_live;
  if (!live) {
    return (
      <div className="mb-4" onClick={(e) => e.stopPropagation()}>
        <div
          className="px-3 py-2 rounded text-[11px] font-mono leading-relaxed"
          style={{ background: '#ffcc3312', border: '1px solid #ffcc3344', color: '#ffcc33' }}
        >
          {t(
            'touchstone.unreachable',
            undefined,
            'The touchstone is not answering. No cards, memos or scores are shown — nothing here is carried over from an earlier poll.',
          )}
        </div>
      </div>
    );
  }

  const memos = live.memos || {};
  const intel = live.intel || {};
  const categories = topCategories(intel.category_scores);
  // The store's scores are unbounded (live values run past 1.5), so bars are drawn
  // relative to the leader rather than to an assumed 0–1 scale.
  const topScore = categories.length > 0 ? categories[0][1] : 0;
  const lessons = Array.isArray(memos.lessons) ? memos.lessons.slice(0, 6) : [];
  const cards = Array.isArray(intel.recent_cards) ? intel.recent_cards.slice(0, 6) : [];
  const notList = Array.isArray(live.not) ? live.not : [];

  return (
    <div className="mb-4" onClick={(e) => e.stopPropagation()}>
      <div
        className="mb-3 px-3 py-2 rounded text-[11px] font-mono"
        style={{ background: '#00000030', border: `1px solid ${themeColor}33` }}
      >
        <div className="text-white/70 mb-1">
          🪨{' '}
          {t(
            'touchstone.role',
            undefined,
            'Solidity touchstone · signed assurance pack pinned to a commit',
          )}
        </div>
        <div className="text-white/45">
          {t(
            'touchstone.no_verdict',
            undefined,
            'A verdict (PASS / REVIEW / FAIL) exists only inside a signed pack from one scan. The monitor observes and never pays for a scan, so no verdict is shown here.',
          )}
        </div>
        {notList.length > 0 ? (
          <div className="text-white/35 mt-1">
            {t('touchstone.split', undefined, 'Not')}: {notList.join(' · ')}
          </div>
        ) : null}
      </div>

      <div className="grid grid-cols-2 gap-1.5 mb-3">
        <div className="px-2 py-1.5 rounded bg-white/5 text-[11px] font-mono">
          <span className="text-white/40">{t('touchstone.version', undefined, 'Version')}:</span>{' '}
          <span style={{ color: themeColor }}>{live.version || '—'}</span>
        </div>
        <div className="px-2 py-1.5 rounded bg-white/5 text-[11px] font-mono">
          <span className="text-white/40">{t('touchstone.intel', undefined, 'Intel')}:</span>{' '}
          <span style={{ color: live.intel_enabled ? '#43e65a' : '#7a8699' }}>
            {live.intel_enabled
              ? t('touchstone.intel_on', undefined, 'allowlisted OSV/GHSA')
              : t('touchstone.intel_off', undefined, 'ingestion off')}
          </span>
        </div>
      </div>

      {live.capability_id ? (
        <div className="mb-3 px-2 py-1.5 rounded bg-white/5 text-[11px] font-mono">
          <span className="text-white/40">{t('touchstone.capability', undefined, 'Capability')}:</span>{' '}
          <span className="text-white/70 break-all">{live.capability_id}</span>
        </div>
      ) : null}

      <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-2">
        {t('touchstone.learned', undefined, 'What it has learned')}
      </div>
      <div className="grid grid-cols-3 gap-1.5 mb-3">
        <div className="px-2 py-1.5 rounded bg-white/5 text-[11px] font-mono">
          <div className="text-white/40 text-[9px] uppercase">
            {t('touchstone.memos', undefined, 'Memos')}
          </div>
          <span style={{ color: themeColor }}>{memos.total ?? 0}</span>
          <span className="text-white/35">
            {' '}
            / {memos.hits ?? 0} {t('touchstone.hits', undefined, 'hits')}
          </span>
        </div>
        <div className="px-2 py-1.5 rounded bg-white/5 text-[11px] font-mono">
          <div className="text-white/40 text-[9px] uppercase">
            {t('touchstone.cards', undefined, 'Cards')}
          </div>
          <span style={{ color: themeColor }}>{intel.cards ?? 0}</span>
        </div>
        <div className="px-2 py-1.5 rounded bg-white/5 text-[11px] font-mono">
          <div className="text-white/40 text-[9px] uppercase">
            {t('touchstone.pairs', undefined, 'Pairs')}
          </div>
          <span style={{ color: themeColor }}>{intel.learned_pairs ?? 0}</span>
        </div>
      </div>

      {typeof memos.exploration === 'number' ? (
        <div className="mb-3 text-[10px] font-mono text-white/40">
          {t('touchstone.exploration', undefined, 'Exploration weight')}: {memos.exploration}
        </div>
      ) : null}

      {categories.length > 0 ? (
        <>
          <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-2">
            {t('touchstone.categories', undefined, 'Detector order · advisory only')}
          </div>
          <div className="space-y-1 mb-3">
            {categories.map(([name, score]) => (
              <div key={name} className="flex items-center gap-2 text-[10px] font-mono">
                <span className="text-white/55 w-28 truncate">{name}</span>
                <span className="flex-1 h-1.5 rounded bg-white/8 overflow-hidden">
                  <span
                    className="block h-full rounded"
                    style={{
                      width: `${Math.max(2, Math.min(100, topScore > 0 ? (score / topScore) * 100 : 0))}%`,
                      background: `linear-gradient(90deg, ${STONE}66, ${STONE})`,
                    }}
                  />
                </span>
                <span className="text-white/35 w-10 text-right">{score.toFixed(2)}</span>
              </div>
            ))}
          </div>
        </>
      ) : null}

      <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-2">
        {t('touchstone.lessons', undefined, 'Distilled lessons')}
      </div>
      <div className="space-y-1 mb-3">
        {lessons.length > 0 ? (
          lessons.map((lesson, i) => (
            <div key={i} className="px-2 py-1.5 rounded bg-white/5 text-[11px] font-mono text-white/60">
              {lesson}
            </div>
          ))
        ) : (
          <div className="text-white/40 text-[11px] font-mono">
            {t('touchstone.no_lessons', undefined, 'No lessons distilled yet.')}
          </div>
        )}
      </div>

      <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-2">
        {t('touchstone.recent_cards', undefined, 'Recent advisory cards')}
      </div>
      <div className="space-y-1 mb-3 max-h-40 overflow-y-auto">
        {cards.length > 0 ? (
          cards.map((card, i) => (
            <div key={card.id || i} className="px-2 py-1.5 rounded bg-white/5 text-[11px] font-mono">
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-white/60 truncate">{card.id || '—'}</span>
                {card.severity ? (
                  <span className="text-white/35 ml-auto">{String(card.severity)}</span>
                ) : null}
              </div>
              <div className="mt-0.5 flex items-center gap-2 text-[10px] text-white/40">
                <span className="truncate">{card.category || '—'}</span>
                <span className="truncate">{card.source || '—'}</span>
              </div>
            </div>
          ))
        ) : (
          <div className="text-white/40 text-[11px] font-mono">
            {t('touchstone.no_cards', undefined, 'No advisory cards ingested yet.')}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        {node.links?.console ? (
          <a
            href={node.links.console}
            target="_blank"
            rel="noreferrer"
            className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
            style={{
              backgroundColor: themeColor + '1e',
              border: `1px solid ${themeColor}55`,
              color: themeColor,
            }}
          >
            {t('touchstone.open_console', undefined, 'Open BASANOS console')} ↗
          </a>
        ) : null}
        {node.links?.landing || node.url ? (
          <a
            href={node.links?.landing || node.url}
            target="_blank"
            rel="noreferrer"
            className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
            style={{ backgroundColor: STONE + '18', border: `1px solid ${STONE}44`, color: STONE }}
          >
            {t('touchstone.open_landing', undefined, 'Open BASANOS landing')} ↗
          </a>
        ) : null}
        {node.links?.github ? (
          <a
            href={node.links.github}
            target="_blank"
            rel="noreferrer"
            className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
            style={{ backgroundColor: '#a855f718', border: '1px solid #a855f744', color: '#c4b5fd' }}
          >
            {t('touchstone.open_repo', undefined, 'Open BASANOS repo')} ↗
          </a>
        ) : null}
      </div>
    </div>
  );
}
