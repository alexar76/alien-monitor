interface Props {
  mode: 'test' | 'real' | 'universe';
  onModeChange: (mode: 'test' | 'real' | 'universe') => void;
  theme: 'cyan' | 'magenta' | 'green';
  onThemeChange: (t: 'cyan' | 'magenta' | 'green') => void;
  showAI: boolean;
  onToggleAI: () => void;
  showTx: boolean;
  onToggleTx: () => void;
  pulseIntensity: number;
  onPulseChange: (v: number) => void;
  themeColor: string;
}

export default function ControlBar({
  mode,
  onModeChange,
  theme,
  onThemeChange,
  showAI,
  onToggleAI,
  showTx,
  onToggleTx,
  pulseIntensity,
  onPulseChange,
  themeColor,
}: Props) {
  const themes = [
    { id: 'cyan' as const, color: '#00f0ff', label: 'CY' },
    { id: 'magenta' as const, color: '#ff00ff', label: 'MG' },
    { id: 'green' as const, color: '#00ff88', label: 'GR' },
  ];

  return (
    <div
      className="
        absolute z-30 pointer-events-none
        left-0 right-0 bottom-0
        px-2 pb-[max(0.5rem,var(--safe-bottom))]
        sm:left-auto sm:right-4 sm:top-20 sm:bottom-auto sm:px-0 sm:pb-0
      "
    >
      <div
        className="
          controls-scroll pointer-events-auto
          flex items-center gap-1.5 sm:gap-2
          overflow-x-auto sm:overflow-visible sm:flex-wrap sm:justify-end
          max-w-full mx-auto sm:mx-0
          glass-panel p-1.5 sm:p-0 sm:bg-transparent sm:border-0 sm:shadow-none sm:backdrop-blur-0
        "
      >
        {/* Mode switch */}
        <div className="glass-panel flex items-center p-0.5 rounded-lg shrink-0 sm:shadow-md">
          <button
            onClick={() => onModeChange('test')}
            className={`px-2.5 sm:px-3 py-2 sm:py-1.5 text-[10px] font-mono uppercase rounded-md transition-all min-h-[36px] sm:min-h-0 ${
              mode === 'test' ? 'text-black font-bold' : 'text-white/40 hover:text-white/70'
            }`}
            style={{ backgroundColor: mode === 'test' ? '#ffdd00' : 'transparent' }}
          >
            TEST
          </button>
          <button
            onClick={() => onModeChange('real')}
            className={`px-2.5 sm:px-3 py-2 sm:py-1.5 text-[10px] font-mono uppercase rounded-md transition-all min-h-[36px] sm:min-h-0 ${
              mode === 'real' ? 'text-black font-bold' : 'text-white/40 hover:text-white/70'
            }`}
            style={{ backgroundColor: mode === 'real' ? '#00ff88' : 'transparent' }}
          >
            LIVE
          </button>
          <button
            onClick={() => onModeChange('universe')}
            className={`px-2.5 sm:px-3 py-2 sm:py-1.5 text-[10px] font-mono uppercase rounded-md transition-all min-h-[36px] sm:min-h-0 ${
              mode === 'universe' ? 'text-white font-bold' : 'text-white/40 hover:text-white/70'
            }`}
            style={{
              backgroundColor: mode === 'universe' ? '#7b2fff' : 'transparent',
              boxShadow: mode === 'universe' ? '0 0 10px rgba(123,47,255,0.5)' : 'none',
            }}
          >
            UNI
          </button>
        </div>

        <div className="glass-panel flex items-center gap-0.5 p-1 rounded-lg shrink-0">
          {themes.map((t) => (
            <button
              key={t.id}
              onClick={() => onThemeChange(t.id)}
              className="w-9 h-9 sm:w-6 sm:h-6 rounded flex items-center justify-center text-[10px] font-bold transition-all"
              style={{
                backgroundColor: theme === t.id ? t.color + '22' : 'transparent',
                color: t.color,
                border: theme === t.id ? `1px solid ${t.color}44` : '1px solid transparent',
              }}
              title={t.id}
            >
              {t.label}
            </button>
          ))}
        </div>

        <button
          onClick={onToggleAI}
          className="glass-panel px-3 py-2.5 sm:py-2 text-[10px] font-mono uppercase rounded-lg transition-all shrink-0 min-h-[36px] sm:min-h-0"
          style={{
            color: showAI ? themeColor : '#ffffff50',
            borderColor: showAI ? themeColor + '44' : '#ffffff15',
            boxShadow: showAI ? `0 0 10px ${themeColor}33` : 'none',
          }}
        >
          AI
        </button>

        <button
          onClick={onToggleTx}
          className="glass-panel px-3 py-2.5 sm:py-2 text-[10px] font-mono uppercase rounded-lg transition-all shrink-0 min-h-[36px] sm:min-h-0"
          style={{
            color: showTx ? themeColor : '#ffffff50',
            borderColor: showTx ? themeColor + '44' : '#ffffff15',
          }}
        >
          LOG
        </button>

        <div className="glass-panel hidden sm:flex items-center gap-2 px-3 py-2 rounded-lg shrink-0">
          <span className="text-[10px] font-mono text-white/30">PULSE</span>
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
      </div>
    </div>
  );
}
