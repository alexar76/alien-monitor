import {
  Component,
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import type { PointerEvent as ReactPointerEvent, ReactNode, RefObject } from 'react';
import type { EcoNode } from '../App';
import { useI18n } from '../i18n';
import type { EyeDrive } from './MomusEyeCanvas';

/* ===========================================================================
 *  MOMUS eye — the node-panel mini-animation.
 *
 *  The satellite's signature scene, shrunk to a thumbnail and WIRED TO THE REAL
 *  PAYLOAD. The one rule it exists to respect: an animation that keeps
 *  performing while the thing it depicts is unreachable is a lie. So:
 *
 *    · idle / clean        slow pupil drift, no sweep
 *    · scan observed       the scan blade sweeps — and ONLY then
 *    · high / critical     crimson pulse whose intensity tracks the severity
 *    · MOMUS unreachable   the eye FREEZES and dims, the box says NO LIVE DATA,
 *                          and not one figure is drawn from a remembered value
 *    · severity unreported the eye stays calm and SAYS the breakdown is missing
 *                          — an unreported count is not a zero
 *
 *  Cost: the monitor already runs a heavy R3F scene behind this panel. The
 *  canvas is code-split, mounted only once the box is actually on screen,
 *  ticked on demand at a capped frame rate, and stopped dead when the panel
 *  scrolls away, the tab is hidden, the data goes stale, or the visitor asked
 *  for reduced motion. No WebGL (or a scene that throws) falls back to the CSS
 *  eye, exactly as the satellite's own hero does.
 * ========================================================================= */

const MomusEyeCanvas = lazy(() => import('./MomusEyeCanvas'));

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

/** One-shot WebGL probe. jsdom and locked-down GPUs land on the CSS eye. */
let webglSupport: boolean | null = null;
export function hasWebGL(): boolean {
  if (webglSupport !== null) return webglSupport;
  if (typeof document === 'undefined') {
    webglSupport = false;
    return webglSupport;
  }
  try {
    const canvas = document.createElement('canvas');
    webglSupport = !!(
      typeof WebGLRenderingContext !== 'undefined' &&
      (canvas.getContext('webgl2') || canvas.getContext('webgl'))
    );
  } catch {
    webglSupport = false;
  }
  return webglSupport;
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

/** A crashed canvas must never take the panel down — same shape as the
 *  boundaries in OraclePrimitive3D / EcosystemGraph. */
class EyeBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }
  componentDidCatch(error: Error) {
    console.warn('[MomusEye] scene failed — using the CSS eye', error);
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
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

export default function MomusEye({ live, accent, mobile = false, fps = 24 }: MomusEyeProps) {
  const { t } = useI18n();
  const boxRef = useRef<HTMLDivElement>(null);

  const scanObserved = useObservedScan(live?.corpus?.scans);
  const signal = useMemo(() => momusEyeSignal(live, scanObserved), [live, scanObserved]);

  const reduced = usePrefersReducedMotion();
  const tabVisible = useTabVisible();
  const inView = useInView(boxRef);
  const webgl = hasWebGL();

  // Mount the canvas only once the box has actually been on screen, and keep it
  // mounted afterwards — re-creating a WebGL context is far dearer than idling
  // one that is not being ticked.
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (inView) setArmed(true);
  }, [inView]);

  const running = signal.live && inView && tabVisible && !reduced;

  // Drive state is mutated in place: a 3 s payload refresh or a pointer move
  // must not re-render React or rebuild the canvas.
  const drive = useRef<EyeDrive>({
    alert: 0,
    scanning: false,
    frozen: true,
    px: 0,
    py: 0,
    hover: false,
  });
  drive.current.alert = signal.alert;
  drive.current.scanning = signal.scanning;
  drive.current.frozen = !signal.live;
  if (!running) drive.current.hover = false;

  const onPointerMove = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      // Mouse only: on a touch screen there is no hover, and a scroll gesture
      // must not be read as a gaze.
      if (e.pointerType !== 'mouse' || !running) return;
      const box = boxRef.current?.getBoundingClientRect();
      if (!box || !box.width || !box.height) return;
      drive.current.px = ((e.clientX - box.left) / box.width) * 2 - 1;
      drive.current.py = -(((e.clientY - box.top) / box.height) * 2 - 1);
      drive.current.hover = true;
    },
    [running],
  );
  const onPointerLeave = useCallback(() => {
    drive.current.hover = false;
  }, []);

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
          // Frozen means frozen: dimmed and drained of colour, so a still frame
          // can never be mistaken for a live one.
          filter: signal.live ? undefined : 'grayscale(0.85) brightness(0.5)',
        }}
        role="img"
        aria-label={caption}
        data-testid="momus-eye"
        data-eye-mode={signal.mode}
        data-eye-running={running ? '1' : '0'}
      >
        {webgl && armed ? (
          <EyeBoundary fallback={fallback}>
            <Suspense fallback={fallback}>
              <MomusEyeCanvas
                drive={drive}
                running={running}
                fps={fps}
                dpr={mobile ? [1, 1.25] : [1, 1.5]}
              />
            </Suspense>
          </EyeBoundary>
        ) : (
          fallback
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
