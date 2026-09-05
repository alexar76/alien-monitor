import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import type { PointerEvent as ReactPointerEvent, RefObject } from 'react';
import type { EcoNode } from '../App';
import { useI18n } from '../i18n';

/* ===========================================================================
 *  MOMUS eye — the node-panel mini-animation.
 *
 *  The satellite's signature scene, shrunk to a thumbnail and WIRED TO THE REAL
 *  PAYLOAD. The one rule it exists to respect: an animation that keeps
 *  performing while the thing it depicts is unreachable is a lie.
 *
 *  Rendering: the monitor page already runs a full-viewport WebGL canvas for
 *  the galaxy graph. A second R3F canvas in the same document gets starved by
 *  the GPU compositor (measured ≈0.1% lit pixels) and shows up as a black box.
 *  The real eye therefore lives in momus-eye.html — its own document, its own
 *  WebGL context — and is embedded here via iframe + postMessage drive. The CSS
 *  poster underneath matches the landing fallback and stays visible until the
 *  iframe paints, so the panel never shows an empty black square.
 * ========================================================================= */

const ASSET_BASE = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');
const EMBED_SRC = `${ASSET_BASE}/momus-eye.html`;

export type MomusSeverity = 'critical' | 'high' | 'medium' | 'low' | 'info';
export type MomusLive = NonNullable<EcoNode['momus_live']>;

/** What the eye is allowed to say. `unknown` = reachable but no severity data. */
export type MomusEyeMode = 'stale' | 'alert' | 'scanning' | 'clean' | 'unknown';

export interface MomusEyeSignal {
  /** A live payload is present. False → the eye freezes and figures are withheld. */
  live: boolean;
  /** MOMUS actually reported a severity breakdown (an absent one is NOT zeros). */
  severityReported: boolean;
  /** Highest severity with a non-zero count; null when clean or unreported. */
  topSeverity: MomusSeverity | null;
  /** 0..1 pulse intensity — non-zero ONLY for a reported high/critical finding. */
  alert: number;
  /** A scan was observed since the previous payload. */
  scanning: boolean;
  mode: MomusEyeMode;
}

/** Severities highest-first. Exported so the panel's chips and the eye can never
 *  disagree about which severities exist. */
export const MOMUS_SEVERITIES: MomusSeverity[] = ['critical', 'high', 'medium', 'low', 'info'];

/**
 * True only when MOMUS actually reported a severity breakdown.
 *
 * The distinction this whole file exists to protect: an ABSENT `finding_counts`
 * is not five zeros. Five zeros mean "we counted, and found none"; absent means
 * "we never got a count". Rendering the second as the first is the same lie as
 * calling an unreachable probe target a pass.
 */
export function hasSeverityBreakdown(
  counts: Record<string, number> | null | undefined,
): boolean {
  if (!counts || typeof counts !== 'object') return false;
  return MOMUS_SEVERITIES.some((s) => typeof counts[s] === 'number');
}

/** Pulse intensity per severity. Only high and critical pulse — the spec's rule,
 *  and the reason a medium finding cannot masquerade as an emergency. */
const ALERT_LEVEL: Partial<Record<MomusSeverity, number>> = { critical: 1, high: 0.62 };

/**
 * Derive everything the eye is allowed to show from the payload alone.
 *
 * Absent ≠ zero: a missing `finding_counts` yields `severityReported: false`,
 * which the panel renders as "not reported", never as a clean sweep.
 */
export function momusEyeSignal(
  live: MomusLive | null | undefined,
  scanObserved = false,
): MomusEyeSignal {
  if (!live) {
    return {
      live: false,
      severityReported: false,
      topSeverity: null,
      alert: 0,
      scanning: false,
      mode: 'stale',
    };
  }
  const counts = live.finding_counts;
  const severityReported = hasSeverityBreakdown(counts);

  let topSeverity: MomusSeverity | null = null;
  if (severityReported && counts) {
    for (const s of MOMUS_SEVERITIES) {
      if ((counts[s] || 0) > 0) {
        topSeverity = s;
        break;
      }
    }
  }
  const alert = (topSeverity && ALERT_LEVEL[topSeverity]) || 0;
  const scanning = !!scanObserved;
  const mode: MomusEyeMode = alert > 0
    ? 'alert'
    : scanning
      ? 'scanning'
      : severityReported
        ? 'clean'
        : 'unknown';
  return { live: true, severityReported, topSeverity, alert, scanning, mode };
}

/**
 * True for a short window after MOMUS's completed-scan counter is seen to
 * advance. This is an OBSERVATION, not a guess: the first sample only arms the
 * comparison, so a freshly-opened panel never claims a scan it did not witness.
 */
export function useObservedScan(scans: number | undefined, windowMs = 15000): boolean {
  const previous = useRef<number | null>(null);
  const [active, setActive] = useState(false);

  useEffect(() => {
    if (typeof scans !== 'number' || !Number.isFinite(scans)) {
      previous.current = null;
      return undefined;
    }
    const prev = previous.current;
    previous.current = scans;
    if (prev === null || scans <= prev) return undefined;
    setActive(true);
    const id = window.setTimeout(() => setActive(false), windowMs);
    return () => window.clearTimeout(id);
  }, [scans, windowMs]);

  return active;
}

/** Push live drive state into the isolated iframe scene. */
function postEyeDrive(
  iframe: HTMLIFrameElement | null,
  payload: {
    alert: number;
    scanning: boolean;
    frozen: boolean;
    px: number;
    py: number;
    hover: boolean;
    running: boolean;
  },
) {
  iframe?.contentWindow?.postMessage({ type: 'momus-eye-drive', ...payload }, '*');
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false;
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  });
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined;
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener?.('change', onChange);
    return () => mq.removeEventListener?.('change', onChange);
  }, []);
  return reduced;
}

function useTabVisible(): boolean {
  const [visible, setVisible] = useState(
    () => typeof document === 'undefined' || document.visibilityState !== 'hidden',
  );
  useEffect(() => {
    if (typeof document === 'undefined') return undefined;
    const onChange = () => setVisible(document.visibilityState !== 'hidden');
    document.addEventListener('visibilitychange', onChange);
    return () => document.removeEventListener('visibilitychange', onChange);
  }, []);
  return visible;
}

/** True while the box is on screen. Without IntersectionObserver we assume yes
 *  (the panel only mounts this when it is open) — the tab-hidden and stale
 *  brakes still apply. */
function useInView(ref: RefObject<Element>): boolean {
  const [inView, setInView] = useState(typeof IntersectionObserver === 'undefined');
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === 'undefined') return undefined;
    const io = new IntersectionObserver(
      (entries) => setInView(entries.some((e) => e.isIntersecting)),
      { threshold: 0.05 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [ref]);
  return inView;
}

/** A crashed iframe must never take the panel down — the CSS poster stays up. */
function useIframeEmbed(
  boxRef: RefObject<HTMLDivElement>,
  drive: {
    alert: number;
    scanning: boolean;
    frozen: boolean;
    px: number;
    py: number;
    hover: boolean;
  },
  running: boolean,
) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [iframeLive, setIframeLive] = useState(false);
  const [iframeFailed, setIframeFailed] = useState(false);

  useEffect(() => {
    const onMsg = (event: MessageEvent) => {
      if (event.data?.type === 'momus-eye-ready') setIframeLive(true);
    };
    window.addEventListener('message', onMsg);
    return () => window.removeEventListener('message', onMsg);
  }, []);

  useEffect(() => {
    if (iframeFailed) return undefined;
    const t = window.setTimeout(() => {
      if (!iframeLive) setIframeFailed(true);
    }, 10000);
    return () => window.clearTimeout(t);
  }, [iframeFailed, iframeLive]);

  const pushDrive = useCallback(() => {
    postEyeDrive(iframeRef.current, { ...drive, running });
  }, [drive, running]);

  useEffect(() => {
    pushDrive();
  }, [pushDrive]);

  const onPointerMove = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if (e.pointerType !== 'mouse' || !running) return;
      const box = boxRef.current?.getBoundingClientRect();
      if (!box?.width || !box?.height) return;
      postEyeDrive(iframeRef.current, {
        ...drive,
        px: ((e.clientX - box.left) / box.width) * 2 - 1,
        py: -(((e.clientY - box.top) / box.height) * 2 - 1),
        hover: true,
        running,
      });
    },
    [boxRef, drive, running],
  );

  const onPointerLeave = useCallback(() => {
    postEyeDrive(iframeRef.current, { ...drive, hover: false, running });
  }, [drive, running]);

  return {
    iframeRef,
    iframeLive,
    iframeFailed,
    onPointerMove,
    onPointerLeave,
    pushDrive,
  };
}

/** Pure-CSS stand-in: no WebGL, no canvas, still an eye. Mirrors the satellite's
 *  `.momus-stage-fallback`, with the same states this component drives. */
export function MomusEyeFallback({
  mode,
  scanning,
  alert,
}: {
  mode: MomusEyeMode;
  scanning: boolean;
  alert: number;
}) {
  return (
    <div
      className={`momus-eye-fallback${mode === 'stale' ? ' is-frozen' : ''}${
        scanning ? ' is-scanning' : ''
      }${alert > 0 ? ' is-alert' : ''}`}
      data-testid="momus-eye-fallback"
      aria-hidden="true"
    />
  );
}

export interface MomusEyeProps {
  /** The live payload, or undefined/null when MOMUS could not be reached. */
  live?: MomusLive | null;
  /** Panel accent colour (node theme). */
  accent: string;
  mobile?: boolean;
  /** Frame-rate cap while animating. */
  fps?: number;
}

export default function MomusEye({ live, accent, mobile = false, fps: _fps = 24 }: MomusEyeProps) {
  const { t } = useI18n();
  const boxRef = useRef<HTMLDivElement>(null);

  const scanObserved = useObservedScan(live?.corpus?.scans);
  const signal = useMemo(() => momusEyeSignal(live, scanObserved), [live, scanObserved]);

  const reduced = usePrefersReducedMotion();
  const tabVisible = useTabVisible();
  const inView = useInView(boxRef);

  const running = signal.live && inView && tabVisible && !reduced;

  const drivePayload = useMemo(
    () => ({
      alert: signal.alert,
      scanning: signal.scanning,
      frozen: !signal.live,
      px: 0,
      py: 0,
      hover: false,
    }),
    [signal.alert, signal.scanning, signal.live],
  );

  const { iframeRef, iframeLive, iframeFailed, onPointerMove, onPointerLeave } = useIframeEmbed(
    boxRef,
    drivePayload,
    running,
  );

  const height = mobile ? 132 : 156;

  const sevLabel = signal.topSeverity
    ? t(`momus.eye.sev.${signal.topSeverity}`, undefined, signal.topSeverity)
    : '';

  // One caption, in words, for exactly what the animation is doing and why.
  let caption: string;
  let captionColor = 'rgba(255,255,255,0.45)';
  if (signal.mode === 'stale') {
    caption = t('momus.eye.captionStale', undefined, 'Frozen — MOMUS unreachable, no live data');
    captionColor = '#ffcc33';
  } else if (signal.mode === 'alert') {
    caption = t('momus.eye.captionAlert', { severity: sevLabel }, 'Pulsing — {{severity}} finding reported');
    captionColor = signal.topSeverity === 'critical' ? '#ff2d55' : '#ff6b3d';
  } else if (signal.mode === 'scanning') {
    caption = t('momus.eye.captionScanning', undefined, 'Sweeping — a scan was observed');
    captionColor = accent;
  } else if (signal.mode === 'unknown') {
    caption = t('momus.eye.captionUnknown', undefined, 'Calm — no severity breakdown reported');
    captionColor = '#ffcc33';
  } else {
    caption = t('momus.eye.captionIdle', undefined, 'Idle — no high or critical finding reported');
  }
  if (signal.mode === 'alert' && signal.scanning) {
    caption += ` · ${t('momus.eye.andScanning', undefined, 'scan observed')}`;
  }
  const stillReason = !signal.live
    ? null
    : reduced
      ? t('momus.eye.stillReduced', undefined, 'still · reduced motion')
      : !tabVisible
        ? t('momus.eye.stillHidden', undefined, 'paused · tab hidden')
        : !inView
          ? t('momus.eye.stillOffscreen', undefined, 'paused · off screen')
          : null;

  const fallback = (
    <MomusEyeFallback mode={signal.mode} scanning={signal.scanning} alert={signal.alert} />
  );

  const showIframe = !iframeFailed;

  return (
    <div className="mb-3" onClick={(e) => e.stopPropagation()}>
      <div
        ref={boxRef}
        onPointerMove={onPointerMove}
        onPointerLeave={onPointerLeave}
        className="relative w-full rounded-lg overflow-hidden"
        style={{
          height,
          border: `1px solid ${accent}33`,
          backgroundColor: '#04030f',
          boxShadow: `inset 0 0 24px ${accent}11`,
          filter: signal.live ? undefined : 'grayscale(0.85) brightness(0.5)',
        }}
        role="img"
        aria-label={caption}
        data-testid="momus-eye"
        data-eye-mode={signal.mode}
        data-eye-running={running ? '1' : '0'}
        data-eye-iframe={iframeLive ? '1' : '0'}
      >
        {fallback}

        {showIframe && (
          <iframe
            ref={iframeRef}
            src={EMBED_SRC}
            title={t('momus.eye.embedTitle', undefined, 'MOMUS eye preview')}
            loading="lazy"
            onLoad={() => postEyeDrive(iframeRef.current, { ...drivePayload, running })}
            className="absolute inset-0 h-full w-full border-0"
            style={{
              pointerEvents: 'none',
              opacity: iframeLive ? 1 : 0,
              transition: 'opacity 0.35s ease',
            }}
            sandbox="allow-scripts allow-same-origin"
            tabIndex={-1}
            aria-hidden="true"
            data-testid="momus-eye-iframe"
          />
        )}

        {!signal.live && (
          <div className="absolute inset-x-0 bottom-0 px-2 py-1 text-[9px] font-mono uppercase tracking-widest"
               data-testid="momus-eye-stale-badge"
               style={{ background: 'rgba(0,0,0,0.62)', color: '#ffcc33' }}>
            {t('momus.eye.noLiveData', undefined, 'no live data')}
          </div>
        )}
        {signal.live && stillReason && (
          <div className="absolute right-1.5 top-1.5 px-1.5 py-0.5 rounded text-[9px] font-mono"
               style={{ background: 'rgba(0,0,0,0.55)', color: 'rgba(255,255,255,0.5)' }}>
            {stillReason}
          </div>
        )}
      </div>
      <div className="mt-1 text-[10px] font-mono leading-snug" style={{ color: captionColor }}>
        {caption}
      </div>
    </div>
  );
}
