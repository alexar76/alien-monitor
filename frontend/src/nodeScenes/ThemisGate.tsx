import type { EcoNode } from '../App';

interface Props {
  node: EcoNode;
  accent: string;
  mobile?: boolean;
}

const DECISION_COLOR: Record<string, string> = {
  approve: '#43e65a',
  review: '#ffcc33',
  reject: '#ff2d55',
};

/**
 * Compact admission trail under the node title:
 * Candidate → Auditor ⇄ Metis → Hub, tinted by the latest decision.
 */
export default function ThemisGate({ node, accent, mobile }: Props) {
  const live = node.themis_live;
  const decision = String(live?.latest?.decision || '').toLowerCase();
  const metis = String(live?.latest?.metis_status || '').toLowerCase();
  const outcome = DECISION_COLOR[decision] || accent;
  const metisPulse = metis === 'pending';
  const receiptReady = metis === 'completed' || decision === 'approve';

  return (
    <div
      className="absolute inset-0 overflow-hidden"
      style={{
        background: `
          radial-gradient(55% 45% at 18% 50%, ${accent}22 0%, transparent 70%),
          radial-gradient(40% 40% at 82% 48%, ${outcome}28 0%, transparent 72%),
          linear-gradient(160deg, #05070f 0%, #0a0614 55%, #041018 100%)
        `,
      }}
    >
      <svg
        viewBox="0 0 360 160"
        className="absolute inset-0 w-full h-full"
        aria-hidden
      >
        <defs>
          <linearGradient id="scaTrail" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor={accent} stopOpacity="0.2" />
            <stop offset="55%" stopColor="#a855f7" stopOpacity="0.55" />
            <stop offset="100%" stopColor={outcome} stopOpacity="0.85" />
          </linearGradient>
          <filter id="scaGlow">
            <feGaussianBlur stdDeviation="2.4" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <path
          d="M42 88 H118 Q148 88 160 70 T210 52 H268"
          fill="none"
          stroke="url(#scaTrail)"
          strokeWidth="2.2"
          strokeLinecap="round"
          opacity="0.9"
        />
        <path
          d="M160 70 C178 42, 210 34, 232 48"
          fill="none"
          stroke="#a855f7"
          strokeWidth="1.6"
          strokeDasharray="4 4"
          opacity={metisPulse ? 0.95 : 0.45}
        >
          {metisPulse ? (
            <animate
              attributeName="stroke-dashoffset"
              from="24"
              to="0"
              dur="1.2s"
              repeatCount="indefinite"
            />
          ) : null}
        </path>

        {/* Candidate */}
        <g filter="url(#scaGlow)">
          <circle cx="42" cy="88" r={mobile ? 9 : 11} fill="#0b1220" stroke={accent} strokeWidth="1.6" />
          <circle cx="42" cy="88" r="3.2" fill={accent} opacity="0.9" />
        </g>
        {/* Auditor */}
        <g filter="url(#scaGlow)">
          <rect
            x="108"
            y="72"
            width="28"
            height="28"
            rx="7"
            fill="#0b1220"
            stroke={outcome}
            strokeWidth="1.8"
          />
          <circle cx="122" cy="86" r="4" fill={outcome}>
            {decision === 'review' ? (
              <animate attributeName="opacity" values="0.45;1;0.45" dur="1.8s" repeatCount="indefinite" />
            ) : null}
          </circle>
        </g>
        {/* Metis */}
        <g filter="url(#scaGlow)">
          <circle
            cx="232"
            cy="48"
            r={mobile ? 8 : 10}
            fill="#14081f"
            stroke="#a855f7"
            strokeWidth="1.7"
          />
          <circle cx="232" cy="48" r="3.4" fill="#c084fc">
            {metisPulse ? (
              <animate attributeName="r" values="2.4;5.2;2.4" dur="1.4s" repeatCount="indefinite" />
            ) : null}
          </circle>
        </g>
        {/* Hub */}
        <g filter="url(#scaGlow)">
          <polygon
            points="268,52 286,40 304,52 286,64"
            fill="#041018"
            stroke={receiptReady ? '#00f0ff' : outcome}
            strokeWidth="1.7"
          />
          <circle
            cx="286"
            cy="52"
            r="3"
            fill={receiptReady ? '#00f0ff' : outcome}
            opacity={receiptReady ? 1 : 0.7}
          >
            {receiptReady ? (
              <animate attributeName="opacity" values="0.55;1;0.55" dur="2.2s" repeatCount="indefinite" />
            ) : null}
          </circle>
        </g>

        <text x="42" y="118" textAnchor="middle" fill="#9fb3c8" fontSize="9" fontFamily="ui-monospace, monospace">
          Candidate
        </text>
        <text x="122" y="118" textAnchor="middle" fill="#9fb3c8" fontSize="9" fontFamily="ui-monospace, monospace">
          Auditor
        </text>
        <text x="232" y="30" textAnchor="middle" fill="#c4b5fd" fontSize="9" fontFamily="ui-monospace, monospace">
          Metis
        </text>
        <text x="286" y="82" textAnchor="middle" fill="#9fb3c8" fontSize="9" fontFamily="ui-monospace, monospace">
          Hub
        </text>
        {decision ? (
          <text
            x="180"
            y="148"
            textAnchor="middle"
            fill={outcome}
            fontSize="11"
            fontFamily="ui-monospace, monospace"
            letterSpacing="1.5"
          >
            {decision.toUpperCase()}
          </text>
        ) : null}
      </svg>
    </div>
  );
}
