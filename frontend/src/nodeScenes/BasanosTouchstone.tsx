import type { EcoNode } from '../App';

interface Props {
  node: EcoNode;
  accent: string;
  mobile?: boolean;
}

const STONE_FACE = '#171a20';
const GOLD = '#e8c36a';

/**
 * The assay, left to right: a pinned commit is scraped across the stone and leaves a
 * gold streak, which becomes a signed pack.
 *
 * Deliberately verdict-free. The streak brightens with what the touchstone has actually
 * learned (memos and advisory cards) — never with a PASS/REVIEW/FAIL, because no scan
 * has run here and colouring the scene by one would invent the very thing this node
 * must not invent.
 */
export default function BasanosTouchstone({ node, accent, mobile }: Props) {
  const live = node.basanos_live;
  const learned = (live?.memos?.total ?? 0) + (live?.intel?.cards ?? 0);
  // Saturates around a few dozen observations — enough to read as "warm" without
  // implying a scale the agent does not publish.
  const warmth = Math.min(1, learned / 24);
  const streak = 0.35 + warmth * 0.55;
  const intelOn = Boolean(live?.intel_enabled);
  const signed = Boolean(live?.provider_pubkey);

  return (
    <div
      className="absolute inset-0 overflow-hidden"
      style={{
        background: `
          radial-gradient(50% 45% at 24% 55%, ${accent}1e 0%, transparent 70%),
          radial-gradient(38% 38% at 80% 42%, ${GOLD}22 0%, transparent 72%),
          linear-gradient(160deg, #07070a 0%, #0d0b08 55%, #06080c 100%)
        `,
      }}
    >
      <svg viewBox="0 0 360 160" className="absolute inset-0 w-full h-full" aria-hidden>
        <defs>
          <linearGradient id="stoneScrape" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor={GOLD} stopOpacity="0.05" />
            <stop offset="45%" stopColor={GOLD} stopOpacity={streak} />
            <stop offset="100%" stopColor="#fff3d0" stopOpacity={streak} />
          </linearGradient>
          <linearGradient id="stoneBody" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#23262e" />
            <stop offset="100%" stopColor={STONE_FACE} />
          </linearGradient>
          <filter id="stoneGlow">
            <feGaussianBlur stdDeviation="2.2" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Pinned commit — the input the pack is bound to */}
        <g filter="url(#stoneGlow)">
          <circle cx="40" cy="80" r={mobile ? 9 : 11} fill="#0b1220" stroke={accent} strokeWidth="1.6" />
          <circle cx="40" cy="80" r="3" fill={accent} opacity="0.9" />
        </g>
        <path
          d="M52 80 H96"
          stroke={accent}
          strokeWidth="1.4"
          strokeDasharray="3 3"
          opacity="0.55"
          fill="none"
        />

        {/* The stone itself */}
        <g filter="url(#stoneGlow)">
          <polygon
            points="104,44 214,52 226,104 116,118"
            fill="url(#stoneBody)"
            stroke={GOLD}
            strokeWidth="1.2"
            strokeOpacity="0.5"
          />
          {/* the scrape */}
          <path
            d="M122 100 L212 62"
            stroke="url(#stoneScrape)"
            strokeWidth="3.4"
            strokeLinecap="round"
            fill="none"
          >
            <animate
              attributeName="stroke-width"
              values="2.8;4.2;2.8"
              dur="3.4s"
              repeatCount="indefinite"
            />
          </path>
          <path d="M130 110 L206 78" stroke={GOLD} strokeWidth="1" opacity={streak * 0.35} fill="none" />
        </g>

        {/* Allowlisted advisory feed — reorders detectors, never adds one */}
        <path
          d="M170 34 C186 24, 206 26, 216 40"
          fill="none"
          stroke="#8ad4ff"
          strokeWidth="1.4"
          strokeDasharray="4 4"
          opacity={intelOn ? 0.85 : 0.25}
        >
          {intelOn ? (
            <animate attributeName="stroke-dashoffset" from="24" to="0" dur="1.6s" repeatCount="indefinite" />
          ) : null}
        </path>
        <circle cx="170" cy="34" r={mobile ? 5 : 6} fill="#061420" stroke="#8ad4ff" strokeWidth="1.4" />

        {/* Signed pack */}
        <g filter="url(#stoneGlow)">
          <rect
            x="252"
            y="56"
            width={mobile ? 44 : 52}
            height={mobile ? 40 : 46}
            rx="8"
            fill="#0b0906"
            stroke={signed ? GOLD : '#7a8699'}
            strokeWidth="1.7"
          />
          <circle cx={mobile ? 274 : 278} cy={mobile ? 76 : 79} r="7" fill="none" stroke={signed ? GOLD : '#7a8699'} strokeWidth="1.4" />
          <circle cx={mobile ? 274 : 278} cy={mobile ? 76 : 79} r="2.6" fill={signed ? GOLD : '#7a8699'}>
            {signed ? (
              <animate attributeName="opacity" values="0.5;1;0.5" dur="2.4s" repeatCount="indefinite" />
            ) : null}
          </circle>
        </g>

        <text x="40" y="112" textAnchor="middle" fill="#9fb3c8" fontSize="9" fontFamily="ui-monospace, monospace">
          commit
        </text>
        <text x="168" y="136" textAnchor="middle" fill="#c8b184" fontSize="9" fontFamily="ui-monospace, monospace">
          touchstone
        </text>
        <text x="170" y="22" textAnchor="middle" fill="#8ad4ff" fontSize="8" fontFamily="ui-monospace, monospace">
          OSV / GHSA
        </text>
        <text x={mobile ? 274 : 278} y="118" textAnchor="middle" fill="#c8b184" fontSize="9" fontFamily="ui-monospace, monospace">
          signed pack
        </text>
      </svg>
    </div>
  );
}
