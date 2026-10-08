import type { EcoNode } from '../App';

interface Props {
  node: EcoNode;
  accent: string;
  mobile?: boolean;
}

/** Amber, the hero's "attention, not failure" tone. */
const REFUSED = '#e0b35a';
const DIM = '#5c7183';

/**
 * The gate chain, drawn the way WARDEN's own hero draws it: tool definitions in
 * on the left, four gates, a recorded verdict on the right — inside a dashed
 * enclosure that says the whole thing runs in the HOST's process.
 *
 * That enclosure is the point of this scene. Every other security node on the map
 * is a service you could curl; WARDEN is a library, and the panel has to make
 * that visible rather than leaving a viewer to assume there is a daemon behind it.
 *
 * Only what we actually know is tinted. The feed side is live (the publisher has
 * an address, so records / freshness / refusals are real), the static scan is
 * local and always on, and `origin` + `pinning` depend on the consuming host's
 * policy — so they stay outlined, not lit. The verdict glyph is never coloured
 * green or red here: the decision happens inside the host, and inventing an
 * outcome for a nicer picture is the exact failure this firewall's own tests
 * exist to prevent.
 */
export default function WardenGates({ node, accent, mobile }: Props) {
  const live = node.warden_live;
  const unreachable = live?.feed === 'unreachable' || live == null;
  const floor = live?.builtin_floor ?? 11;
  const records = live?.records ?? 0;
  const refused = live?.refused ?? 0;
  const fresh = Boolean(live?.accepted_by_freshness);
  const signed = Boolean(live?.signed);
  const feedLit = !unreachable && fresh && signed;
  const ruleset = live?.ruleset_version ? `v${live.ruleset_version}` : 'v3';

  const gateR = mobile ? 11 : 13;
  const gates: Array<{ x: number; label: string; sub: string; lit: boolean }> = [
    { x: 128, label: 'static', sub: `scan ${ruleset}`, lit: true },
    // The record count is only shown when a consuming WARDEN would ACCEPT the
    // document. An unsigned or stale feed is refused and the install keeps the
    // built-in floor alone, so printing "11+42" there would credit the gate with
    // records nobody is enforcing.
    { x: 186, label: 'threat', sub: feedLit ? `${floor}+${records}` : `floor ${floor}`, lit: feedLit },
    { x: 244, label: 'origin', sub: 'declared?', lit: false },
    { x: 302, label: 'pinning', sub: 'drift?', lit: false },
  ];

  return (
    <div
      className="absolute inset-0 overflow-hidden"
      style={{
        background: `
          radial-gradient(50% 45% at 14% 45%, ${accent}22 0%, transparent 70%),
          radial-gradient(42% 40% at 88% 58%, ${REFUSED}14 0%, transparent 72%),
          linear-gradient(160deg, #071018 0%, #0c1824 55%, #061016 100%)
        `,
      }}
    >
      <svg viewBox="0 0 400 160" className="absolute inset-0 w-full h-full" aria-hidden>
        <defs>
          <linearGradient id="wdnFlow" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor={accent} stopOpacity="0.15" />
            <stop offset="45%" stopColor={accent} stopOpacity="0.7" />
            <stop offset="100%" stopColor={accent} stopOpacity="0.9" />
          </linearGradient>
          <filter id="wdnGlow">
            <feGaussianBlur stdDeviation="2.2" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* The library boundary: everything inside runs in the host process. */}
        <rect
          x="104"
          y="34"
          width="228"
          height="86"
          rx="12"
          fill="none"
          stroke={accent}
          strokeOpacity="0.28"
          strokeWidth="1"
          strokeDasharray="5 5"
        />
        {!mobile ? (
          <text x="218" y="30" textAnchor="middle" fill={DIM} fontSize="8" fontFamily="ui-monospace, monospace" letterSpacing="1.2">
            IN THE HOST PROCESS
          </text>
        ) : null}

        {/* Tool definitions arriving from the MCP server. */}
        <g filter="url(#wdnGlow)">
          {[64, 77, 90].map((y, i) => (
            <rect
              key={y}
              x={mobile ? 20 : 24}
              y={y}
              width={mobile ? 44 : 52}
              height="9"
              rx="2.5"
              fill="#0b151e"
              stroke={accent}
              strokeOpacity={0.75 - i * 0.18}
              strokeWidth="1.1"
            />
          ))}
        </g>
        <text x={mobile ? 42 : 50} y="56" textAnchor="middle" fill={DIM} fontSize="8" fontFamily="ui-monospace, monospace">
          tool defs
        </text>

        {/* The chain itself. */}
        <path
          d="M80 79 H352"
          fill="none"
          stroke="url(#wdnFlow)"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
        <path d="M80 79 H352" fill="none" stroke={accent} strokeWidth="1.6" strokeDasharray="3 9" opacity="0.9">
          <animate attributeName="stroke-dashoffset" from="24" to="0" dur="1.6s" repeatCount="indefinite" />
        </path>

        {/* Signed feed coming down from the publisher. */}
        <path
          d="M186 44 V62"
          fill="none"
          stroke={feedLit ? accent : DIM}
          strokeWidth="1.3"
          strokeDasharray="4 4"
          opacity={feedLit ? 0.95 : 0.5}
        >
          {feedLit ? (
            <animate attributeName="stroke-dashoffset" from="16" to="0" dur="1.9s" repeatCount="indefinite" />
          ) : null}
        </path>
        <text x="186" y="41" textAnchor="middle" fill={feedLit ? accent : DIM} fontSize="8" fontFamily="ui-monospace, monospace">
          {/* Why the gate is unlit, in the operator's words: a signature that is
              present but past the freshness window is refused just as firmly as
              a missing one, and "signed feed" over a dim gate reads as a bug. */}
          {unreachable ? 'feed down' : !signed ? 'unsigned' : fresh ? 'signed feed' : 'stale feed'}
        </text>

        {gates.map((g) => (
          <g key={g.label}>
            <g filter="url(#wdnGlow)">
              <rect
                x={g.x - gateR}
                y={79 - gateR}
                width={gateR * 2}
                height={gateR * 2}
                rx="5"
                fill="#0b151e"
                stroke={g.lit ? accent : DIM}
                strokeWidth={g.lit ? 1.7 : 1.2}
                strokeOpacity={g.lit ? 1 : 0.75}
              />
              <circle cx={g.x} cy="79" r="2.6" fill={g.lit ? accent : DIM} opacity={g.lit ? 0.95 : 0.55} />
            </g>
            <text x={g.x} y="104" textAnchor="middle" fill="#9fb3c8" fontSize="8" fontFamily="ui-monospace, monospace">
              {g.label}
            </text>
            {!mobile ? (
              <text x={g.x} y="114" textAnchor="middle" fill={DIM} fontSize="7" fontFamily="ui-monospace, monospace">
                {g.sub}
              </text>
            ) : null}
          </g>
        ))}

        {/* What the publisher declined to publish — attention, not failure. */}
        {refused > 0 ? (
          <g>
            <circle cx="204" cy="48" r="3" fill={REFUSED} opacity="0.9" />
            {!mobile ? (
              <text x="210" y="51" fill={REFUSED} fontSize="7" fontFamily="ui-monospace, monospace">
                {refused} refused
              </text>
            ) : null}
          </g>
        ) : null}

        {/* The verdict: deliberately uncoloured. It is decided in the host. */}
        <g filter="url(#wdnGlow)">
          <polygon
            points="352,79 366,66 380,79 366,92"
            fill="#041018"
            stroke={accent}
            strokeOpacity="0.85"
            strokeWidth="1.6"
          />
          <circle cx="366" cy="79" r="2.6" fill={accent} opacity="0.85">
            <animate attributeName="opacity" values="0.45;0.95;0.45" dur="2.4s" repeatCount="indefinite" />
          </circle>
        </g>
        <text x="366" y="106" textAnchor="middle" fill="#9fb3c8" fontSize="8" fontFamily="ui-monospace, monospace">
          verdict
        </text>
        {!mobile ? (
          <text x="366" y="116" textAnchor="middle" fill={DIM} fontSize="7" fontFamily="ui-monospace, monospace">
            allow · block
          </text>
        ) : null}

        <text x="200" y="140" textAnchor="middle" fill={DIM} fontSize="8" fontFamily="ui-monospace, monospace">
          {unreachable
            ? `built-in floor only · ${floor} records · no network`
            : `local facts only · no oracle · score 0..1 in the host`}
        </text>
      </svg>
    </div>
  );
}
