import { LOCALES, LOCALE_LABELS, useI18n, type Locale } from '../i18n';
import {
  otherRealmMapUrl,
  paintedMonitorMode,
  type MonitorMode,
  type RealmLinks,
} from '../lib/realmModeNav';

interface Props {
  mode: MonitorMode;
  onModeChange: (mode: MonitorMode) => void;
  realmLinks?: RealmLinks | null;
  theme: 'cyan' | 'magenta' | 'green';
  onThemeChange: (t: 'cyan' | 'magenta' | 'green') => void;
  showAI: boolean;
  onToggleAI: () => void;
  showReputation: boolean;
  onToggleReputation: () => void;
  showTx: boolean;
  onToggleTx: () => void;
  showKnocking: boolean;
  onToggleKnocking: () => void;
  knockingCount: number;
  pulseIntensity: number;
  onPulseChange: (v: number) => void;
  themeColor: string;
  mobileOpen?: boolean;
  onMobileClose?: () => void;
}

export default function ControlBar({
  mode,
  onModeChange,
  realmLinks = null,
  theme,
  onThemeChange,
  showAI,
  onToggleAI,
  showReputation,
  onToggleReputation,
  showTx,
  onToggleTx,
  showKnocking,
  onToggleKnocking,
  knockingCount,
  pulseIntensity,
  onPulseChange,
  themeColor,
  mobileOpen = false,
  onMobileClose,
}: Props) {
  const { t, locale, setLocale } = useI18n();
  const painted = paintedMonitorMode(mode, realmLinks);
  const liveHref = otherRealmMapUrl('real', realmLinks);
  const uniHref = otherRealmMapUrl('universe', realmLinks);

  const modeBtnClass = (active: boolean) =>
    `px-3 py-1.5 text-[10px] font-mono uppercase rounded-md transition-all ${
      active ? 'text-black font-bold' : 'text-white/40 hover:text-white/70'
    }`;

  const themes = [
    { id: 'cyan' as const, color: '#00f0ff', label: 'CY' },
    { id: 'magenta' as const, color: '#ff00ff', label: 'MG' },
    { id: 'green' as const, color: '#00ff88', label: 'GR' },
  ];

  const controls = (
    <>
      {/* Locale */}
      <div
        className="glass-panel flex items-center justify-center p-0.5 rounded-lg w-full md:w-auto"
        title={t('controls.language')}
      >
        {LOCALES.map((code) => (
          <button
            key={code}
            onClick={() => setLocale(code as Locale)}
            className={`px-2 py-1.5 text-[10px] font-mono uppercase rounded-md transition-all ${
              locale === code ? 'text-black font-bold' : 'text-white/40 hover:text-white/70'
            }`}
            style={{
              backgroundColor: locale === code ? themeColor : 'transparent',
            }}
          >
            {LOCALE_LABELS[code]}
          </button>
        ))}
      </div>

      {/* Mode switch — LIVE/UNI on the other realm are links to that map, not a paint job. */}
      <div className="glass-panel flex items-center justify-center flex-wrap p-0.5 rounded-lg w-full md:w-auto">
        <button
          type="button"
          onClick={() => onModeChange('test')}
          className={modeBtnClass(painted === 'test')}
          style={{
            backgroundColor: painted === 'test' ? '#ffdd00' : 'transparent',
          }}
        >
          {t('controls.test')}
        </button>
        {liveHref ? (
          <a
            href={liveHref}
            className={modeBtnClass(painted === 'real')}
            style={{
              backgroundColor: painted === 'real' ? '#00ff88' : 'transparent',
            }}
          >
            {t('controls.live')}
          </a>
        ) : (
          <button
            type="button"
            onClick={() => onModeChange('real')}
            className={modeBtnClass(painted === 'real')}
            style={{
              backgroundColor: painted === 'real' ? '#00ff88' : 'transparent',
            }}
          >
            {t('controls.live')}
          </button>
        )}
        {uniHref ? (
          <a
            href={uniHref}
            className={modeBtnClass(painted === 'universe')}
            style={{
              backgroundColor: painted === 'universe' ? '#00ff88' : 'transparent',
            }}
          >
            {t('controls.uni')}
          </a>
        ) : (
          <button
            type="button"
            onClick={() => onModeChange('universe')}
            className={modeBtnClass(painted === 'universe')}
            style={{
              backgroundColor: painted === 'universe' ? '#00ff88' : 'transparent',
            }}
          >
            {t('controls.uni')}
          </button>
        )}
      </div>

      {/* Theme picker */}
      <div className="glass-panel flex items-center justify-center gap-0.5 p-1 rounded-lg w-full md:w-auto">
        {themes.map((th) => (
          <button
            key={th.id}
            onClick={() => onThemeChange(th.id)}
            className="w-6 h-6 rounded flex items-center justify-center text-[10px] font-bold transition-all"
            style={{
              backgroundColor: theme === th.id ? th.color + '22' : 'transparent',
              color: th.color,
              border: theme === th.id ? `1px solid ${th.color}44` : '1px solid transparent',
            }}
            title={th.id}
          >
            {th.label}
          </button>
        ))}
      </div>

      <button
        type="button"
        onClick={onToggleAI}
        className={`ai-beacon-btn w-full md:w-auto px-4 py-2 text-[11px] font-mono font-bold uppercase rounded-lg tracking-widest ${
          showAI ? 'ai-beacon-btn--active' : ''
        }`}
        title={t('controls.aiHint')}
        aria-pressed={showAI}
      >
        <span className="ai-beacon-btn__glyph" aria-hidden>
          ✦
        </span>
        {t('controls.ai')}
      </button>

      <button
        type="button"
        onClick={onToggleReputation}
        className={`rep-beacon-btn w-full md:w-auto px-4 py-2 text-[11px] font-mono font-bold uppercase rounded-lg tracking-widest ${
          showReputation ? 'rep-beacon-btn--active' : ''
        }`}
        title={t('controls.reputationHint')}
        aria-pressed={showReputation}
      >
        <span className="rep-beacon-btn__glyph" aria-hidden>
          ⬡
        </span>
        {t('controls.reputation')}
      </button>

      <button
        onClick={onToggleTx}
        className="glass-panel w-full md:w-auto px-3 py-2 text-[10px] font-mono uppercase rounded-lg transition-all"
        style={{
          color: showTx ? themeColor : '#ffffff50',
          borderColor: showTx ? themeColor + '44' : '#ffffff15',
        }}
      >
        {t('controls.log')}
      </button>

      <button
        type="button"
        onClick={onToggleKnocking}
        className={`knock-beacon-btn w-full md:w-auto px-4 py-2 text-[11px] font-mono font-bold uppercase rounded-lg tracking-widest ${
          showKnocking ? 'knock-beacon-btn--active' : ''
        } ${knockingCount > 0 && !showKnocking ? 'knock-beacon-btn--hot' : ''}`}
        title={t('controls.knockingHint')}
        aria-pressed={showKnocking}
      >
        <span className="knock-beacon-btn__glyph" aria-hidden>
          ⌁
        </span>
        {t('controls.knocking')}
        {knockingCount > 0 && (
          <span className="knock-beacon-btn__count">{knockingCount}</span>
        )}
      </button>

      <div className="glass-panel flex items-center gap-2 px-3 py-2 rounded-lg w-full md:w-auto">
        <span className="text-[10px] font-mono text-white/30">{t('controls.pulse')}</span>
        <input
          type="range"
          min="0"
          max="100"
          value={Math.round(pulseIntensity * 100)}
          onChange={(e) => onPulseChange(Number(e.target.value) / 100)}
          className="w-16 h-1 appearance-none rounded-full cursor-pointer"
          style={{
            background: `linear-gradient(90deg, ${themeColor}44, ${themeColor})`,
            accentColor: themeColor,
          }}
        />
      </div>
    </>
  );

  return (
    <>
      <div className="hidden md:flex absolute top-20 right-4 z-20 items-center gap-2">
        {controls}
      </div>
      {mobileOpen && (
        <div
          className="md:hidden fixed inset-x-0 z-40 max-h-[min(72vh,560px)] overflow-y-auto rounded-t-2xl glass-panel p-4 pb-3 animate-slide-up bottom-[var(--mobile-dock-clearance)]"
          style={{ borderColor: themeColor + '44' }}
        >
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-mono uppercase tracking-wider opacity-60">
              {t('mobile.settingsTitle')}
            </span>
            <button
              type="button"
              onClick={onMobileClose}
              className="text-white/50 hover:text-white text-lg leading-none px-2"
              aria-label={t('mobile.closeSheet')}
            >
              ×
            </button>
          </div>
          <div className="flex flex-col gap-3">{controls}</div>
        </div>
      )}
    </>
  );
}
