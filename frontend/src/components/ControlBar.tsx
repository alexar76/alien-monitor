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
    <div className="absolute top-20 right-4 z-20 flex items-center gap-2">
      {/* Mode switch */}
      <div className="glass-panel flex items-center p-0.5 rounded-lg">
        <button
          onClick={() => onModeChange('test')}
          className={`px-3 py-1.5 text-[10px] font-mono uppercase rounded-md transition-all ${
            mode === 'test' ? 'text-black font-bold' : 'text-white/40 hover:text-white/70'
          }`}
          style={{
            backgroundColor: mode === 'test' ? '#ffdd00' : 'transparent',
          }}
        >
          TEST
        </button>
        <button
          onClick={() => onModeChange('real')}
          className={`px-3 py-1.5 text-[10px] font-mono uppercase rounded-md transition-all ${
            mode === 'real' ? 'text-black font-bold' : 'text-white/40 hover:text-white/70'
          }`}
          style={{
            backgroundColor: mode === 'real' ? '#00ff88' : 'transparent',
          }}
        >
          LIVE
        </button>
        <button
          onClick={() => onModeChange('universe')}
          className={`px-3 py-1.5 text-[10px] font-mono uppercase rounded-md transition-all ${
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

      {/* Theme picker */}
      <div className="glass-panel flex items-center gap-0.5 p-1 rounded-lg">
        {themes.map((t) => (
          <button
            key={t.id}
            onClick={() => onThemeChange(t.id)}
            className="w-6 h-6 rounded flex items-center justify-center text-[10px] font-bold transition-all"
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

      {/* AI toggle */}
      <button
        onClick={onToggleAI}
        className="glass-panel px-3 py-2 text-[10px] font-mono uppercase rounded-lg transition-all"
        style={{
          color: showAI ? themeColor : '#ffffff50',
          borderColor: showAI ? themeColor + '44' : '#ffffff15',
          boxShadow: showAI ? `0 0 10px ${themeColor}33` : 'none',
        }}
      >
        AI
      </button>

      {/* Activity toggle */}
      <button
        onClick={onToggleTx}
        className="glass-panel px-3 py-2 text-[10px] font-mono uppercase rounded-lg transition-all"
        style={{
          color: showTx ? themeColor : '#ffffff50',
          borderColor: showTx ? themeColor + '44' : '#ffffff15',
        }}
      >
        LOG
      </button>

      {/* Pulse intensity slider */}
      <div className="glass-panel flex items-center gap-2 px-3 py-2 rounded-lg">
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
  );
}
