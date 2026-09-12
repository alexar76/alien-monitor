/**
 * MOMUS eye — the node-panel mini-animation.
 *
 * These tests are almost entirely about ONE property: the eye may only depict
 * state that MOMUS actually reported. The pretty parts (the shader, the lid
 * maths) are untested on purpose — they cannot lie. What can lie is the mapping
 * from payload to motion, so that is what is pinned here:
 *
 *   · an unreachable MOMUS freezes the eye and withholds every figure;
 *   · an ABSENT severity breakdown is never rendered as five zeros;
 *   · a measured zero IS shown as zero, and reads as calm;
 *   · only high/critical pulse, and critical pulses harder than high;
 *   · the sweep runs only for a scan the monitor actually witnessed.
 *
 * jsdom has no WebGL, so every render here lands on the CSS fallback eye — which
 * is precisely the path the panel must survive on a locked-down GPU.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act, cleanup } from '@testing-library/react';
import { renderHook } from '@testing-library/react';

import MomusEye, {
  hasSeverityBreakdown,
  momusEyeSignal,
  useObservedScan,
  MOMUS_SEVERITIES,
  type MomusLive,
} from '../components/MomusEye';
import NodeDetail from '../components/NodeDetail';
import type { EcoNode } from '../App';
import { I18nProvider } from '../i18n';
import en from '../i18n/locales/en.json';
import ru from '../i18n/locales/ru.json';
import es from '../i18n/locales/es.json';
import fr from '../i18n/locales/fr.json';
import zh from '../i18n/locales/zh.json';

const live = (over: Partial<MomusLive> = {}): MomusLive => ({
  version: '0.1.0',
  service: 'momus',
  finding_counts: { critical: 0, high: 0, medium: 0, low: 0, info: 0 },
  ...over,
});

afterEach(cleanup);

// ---------------------------------------------------------------------------
// hasSeverityBreakdown — absent is not zero
// ---------------------------------------------------------------------------

describe('hasSeverityBreakdown', () => {
  it('is false for a missing or non-object breakdown', () => {
    expect(hasSeverityBreakdown(undefined)).toBe(false);
    expect(hasSeverityBreakdown(null)).toBe(false);
    expect(hasSeverityBreakdown({})).toBe(false);
  });

  it('is TRUE for an all-zero breakdown — that is a measurement', () => {
    expect(hasSeverityBreakdown({ critical: 0, high: 0, medium: 0, low: 0, info: 0 })).toBe(true);
  });

  it('is true when even one severity carries a number', () => {
    expect(hasSeverityBreakdown({ high: 2 })).toBe(true);
  });

  it('ignores non-numeric junk in the severity slots', () => {
    expect(hasSeverityBreakdown({ high: '3' } as unknown as Record<string, number>)).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// momusEyeSignal — the payload → motion mapping
// ---------------------------------------------------------------------------

describe('momusEyeSignal', () => {
  it('freezes and reports nothing when there is no payload', () => {
    for (const absent of [undefined, null]) {
      const s = momusEyeSignal(absent);
      expect(s.mode).toBe('stale');
      expect(s.live).toBe(false);
      expect(s.alert).toBe(0);
      expect(s.scanning).toBe(false);
      expect(s.severityReported).toBe(false);
      expect(s.topSeverity).toBeNull();
    }
  });

  it('stays frozen even if a scan was observed a moment before the outage', () => {
    // The eye must not keep sweeping for a source it can no longer reach.
    const s = momusEyeSignal(null, true);
    expect(s.mode).toBe('stale');
    expect(s.scanning).toBe(false);
  });

  it('reads an all-zero breakdown as CLEAN, not as unknown', () => {
    const s = momusEyeSignal(live());
    expect(s.mode).toBe('clean');
    expect(s.severityReported).toBe(true);
    expect(s.topSeverity).toBeNull();
    expect(s.alert).toBe(0);
  });

  it('reads an ABSENT breakdown as unknown, not as clean', () => {
    const s = momusEyeSignal(live({ finding_counts: undefined }));
    expect(s.mode).toBe('unknown');
    expect(s.severityReported).toBe(false);
    expect(s.alert).toBe(0);
  });

  it('pulses for a critical finding, hardest of all', () => {
    const s = momusEyeSignal(live({ finding_counts: { critical: 1, high: 0 } }));
    expect(s.mode).toBe('alert');
    expect(s.topSeverity).toBe('critical');
    expect(s.alert).toBe(1);
  });

  it('pulses for high, but less than for critical', () => {
    const high = momusEyeSignal(live({ finding_counts: { critical: 0, high: 3 } }));
    const crit = momusEyeSignal(live({ finding_counts: { critical: 1, high: 3 } }));
    expect(high.mode).toBe('alert');
    expect(high.alert).toBeGreaterThan(0);
    expect(high.alert).toBeLessThan(crit.alert);
  });

  it('does NOT pulse for medium, low or info — severity is not decoration', () => {
    for (const sev of ['medium', 'low', 'info'] as const) {
      const s = momusEyeSignal(live({ finding_counts: { [sev]: 9 } }));
      expect(s.alert).toBe(0);
      expect(s.mode).not.toBe('alert');
      expect(s.topSeverity).toBe(sev);
    }
  });

  it('picks the highest non-zero severity', () => {
    const s = momusEyeSignal(live({ finding_counts: { critical: 0, high: 0, medium: 4, low: 7 } }));
    expect(s.topSeverity).toBe('medium');
  });

  it('sweeps only for an observed scan, and an alert outranks a sweep', () => {
    expect(momusEyeSignal(live(), true).mode).toBe('scanning');
    const both = momusEyeSignal(live({ finding_counts: { critical: 1 } }), true);
    expect(both.mode).toBe('alert');
    expect(both.scanning).toBe(true);
  });

  it('orders severities highest-first', () => {
    expect(MOMUS_SEVERITIES).toEqual(['critical', 'high', 'medium', 'low', 'info']);
  });
});

// ---------------------------------------------------------------------------
// useObservedScan — a scan is witnessed, never assumed
// ---------------------------------------------------------------------------

describe('useObservedScan', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('does not claim a scan from the FIRST sample — that only arms the comparison', () => {
    const { result } = renderHook(({ n }) => useObservedScan(n), {
      initialProps: { n: 42 },
    });
    expect(result.current).toBe(false);
  });

  it('reports a scan when the counter is seen to advance, then lets it expire', () => {
    const { result, rerender } = renderHook(({ n }) => useObservedScan(n, 1000), {
      initialProps: { n: 1 },
    });
    expect(result.current).toBe(false);

    rerender({ n: 2 });
    expect(result.current).toBe(true);

    act(() => {
      vi.advanceTimersByTime(1001);
    });
    expect(result.current).toBe(false);
  });

  it('ignores a counter that stands still or goes backwards', () => {
    const { result, rerender } = renderHook(({ n }) => useObservedScan(n, 1000), {
      initialProps: { n: 5 },
    });
    rerender({ n: 5 });
    expect(result.current).toBe(false);
    rerender({ n: 3 });
    expect(result.current).toBe(false);
  });

  it('never fires when the counter is absent', () => {
    const { result, rerender } = renderHook(
      ({ n }: { n: number | undefined }) => useObservedScan(n, 1000),
      { initialProps: { n: undefined as number | undefined } },
    );
    rerender({ n: undefined });
    expect(result.current).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Rendering — CSS poster always paints; WebGL runs in an isolated iframe document.
// ---------------------------------------------------------------------------

function mount(payload: MomusLive | null | undefined) {
  return render(
    <I18nProvider>
      <MomusEye live={payload} accent="#ff2d55" />
    </I18nProvider>,
  );
}

describe('MomusEye rendering', () => {
  it('always paints the CSS poster (never a blank box)', () => {
    mount(live());
    expect(screen.getByTestId('momus-eye-fallback')).toBeTruthy();
  });

  it('embeds the isolated WebGL document', () => {
    mount(live());
    const iframe = screen.getByTestId('momus-eye-iframe') as HTMLIFrameElement;
    expect(iframe.getAttribute('src')).toMatch(/momus-eye\.html$/);
  });

  it('freezes, dims and says NO LIVE DATA when MOMUS is unreachable', () => {
    mount(undefined);
    const box = screen.getByTestId('momus-eye');
    expect(box.getAttribute('data-eye-mode')).toBe('stale');
    // Not merely un-animated: stopped, and visibly drained of colour.
    expect(box.getAttribute('data-eye-running')).toBe('0');
    expect(box.style.filter).toContain('grayscale');
    expect(screen.getByTestId('momus-eye-fallback').className).toContain('is-frozen');
    // the badge over the canvas, distinct from the caption underneath it
    expect(screen.getByTestId('momus-eye-stale-badge').textContent).toMatch(/no live data/i);
    // and it must not narrate a state it cannot see
    expect(box.getAttribute('aria-label')).toMatch(/unreachable/i);
  });

  it('shows no stale banner and no grayscale while the payload is live', () => {
    mount(live());
    const box = screen.getByTestId('momus-eye');
    expect(box.getAttribute('data-eye-mode')).toBe('clean');
    expect(box.style.filter).toBe('');
    expect(screen.queryByTestId('momus-eye-stale-badge')).toBeNull();
  });

  it('names the reported severity in the caption when it pulses', () => {
    mount(live({ finding_counts: { critical: 2 } }));
    const box = screen.getByTestId('momus-eye');
    expect(box.getAttribute('data-eye-mode')).toBe('alert');
    expect(box.getAttribute('aria-label')).toMatch(/critical/i);
    expect(screen.getByTestId('momus-eye-fallback').className).toContain('is-alert');
  });

  it('says the breakdown is missing rather than implying a clean sweep', () => {
    mount(live({ finding_counts: undefined }));
    const box = screen.getByTestId('momus-eye');
    expect(box.getAttribute('data-eye-mode')).toBe('unknown');
    expect(box.getAttribute('aria-label')).toMatch(/no severity breakdown reported/i);
  });

  it('renders a still eye and says so when reduced motion is requested', () => {
    const original = window.matchMedia;
    window.matchMedia = ((q: string) =>
      ({
        matches: q.includes('prefers-reduced-motion'),
        media: q,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
        onchange: null,
        dispatchEvent: () => false,
      }) as unknown as MediaQueryList) as typeof window.matchMedia;
    try {
      mount(live());
      const box = screen.getByTestId('momus-eye');
      expect(box.getAttribute('data-eye-running')).toBe('0');
      expect(screen.getByText(/reduced motion/i)).toBeTruthy();
    } finally {
      window.matchMedia = original;
    }
  });
});

// ---------------------------------------------------------------------------
// Panel wiring — the eye is present on the momus node, reachable or not
// ---------------------------------------------------------------------------

describe('NodeDetail · momus panel', () => {
  const momusNode = (over: Partial<EcoNode> = {}): EcoNode => ({
    id: 'momus',
    label: 'MOMUS',
    group: 'satellite',
    icon: '🔴',
    description: 'adversarial audit',
    metrics: {},
    status: 'active',
    position: { x: 0, y: 0, z: 0 },
    ...over,
  });

  function panel(node: EcoNode) {
    return render(
      <I18nProvider>
        <NodeDetail node={node} onClose={() => {}} themeColor="#ff2d55" />
      </I18nProvider>,
    );
  }

  it('still shows the eye — frozen — when MOMUS never answered', () => {
    // The old panel rendered nothing at all here. An empty panel is honest; a
    // frozen eye that says why is honest AND useful. What is forbidden is the
    // third option: a lively eye over remembered numbers.
    panel(momusNode({ status: 'offline' }));
    expect(screen.getByTestId('momus-eye').getAttribute('data-eye-mode')).toBe('stale');
    expect(screen.getByText(/could not be reached/i)).toBeTruthy();
    // and no invented figures came along with it
    expect(screen.queryByText('Scan parameters')).toBeNull();
    expect(screen.queryByText('Findings')).toBeNull();
    expect(screen.queryByText(/^critical \d/)).toBeNull();
  });

  it('draws the severity chips when MOMUS reported a breakdown, zeros included', () => {
    panel(momusNode({ momus_live: live({ finding_counts: { critical: 0, high: 2, medium: 0, low: 0, info: 1 } }) }));
    expect(screen.getByText('critical 0')).toBeTruthy();
    expect(screen.getByText('high 2')).toBeTruthy();
    expect(screen.getByText('info 1')).toBeTruthy();
    expect(screen.queryByText(/not a count of zero/i)).toBeNull();
  });

  it('withholds the chips and names the gap when no breakdown was reported', () => {
    panel(momusNode({ momus_live: live({ finding_counts: undefined }) }));
    expect(screen.getByText(/not a count of zero/i)).toBeTruthy();
    expect(screen.queryByText('critical 0')).toBeNull();
    expect(screen.queryByText('high 0')).toBeNull();
  });

  it('labels UNI settlement as a simulation so no one reads it as money moving', () => {
    panel(momusNode({ momus_live: live({ settlement: { mode: 'uni', moves_real_value: false } }) }));
    expect(screen.getByText(/no money moves/i)).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// i18n — every string the eye can say exists in all five catalogs
// ---------------------------------------------------------------------------

describe('MOMUS eye i18n coverage', () => {
  const catalogs: Record<string, Record<string, unknown>> = {
    en: en as Record<string, unknown>,
    ru: ru as Record<string, unknown>,
    es: es as Record<string, unknown>,
    fr: fr as Record<string, unknown>,
    zh: zh as Record<string, unknown>,
  };

  const KEYS = [
    'momus.eye.captionStale',
    'momus.eye.captionAlert',
    'momus.eye.captionScanning',
    'momus.eye.captionUnknown',
    'momus.eye.captionIdle',
    'momus.eye.andScanning',
    'momus.eye.noLiveData',
    'momus.eye.stillReduced',
    'momus.eye.stillHidden',
    'momus.eye.stillOffscreen',
    'momus.unreachable',
    'momus.counts_unreported',
    ...MOMUS_SEVERITIES.map((s) => `momus.eye.sev.${s}`),
  ];

  function resolve(dict: Record<string, unknown>, path: string): string | undefined {
    let cur: unknown = dict;
    for (const part of path.split('.')) {
      if (cur == null || typeof cur !== 'object') return undefined;
      cur = (cur as Record<string, unknown>)[part];
    }
    return typeof cur === 'string' ? cur : undefined;
  }

  for (const [loc, dict] of Object.entries(catalogs)) {
    it(`${loc} defines every eye string`, () => {
      for (const key of KEYS) {
        expect(resolve(dict, key), `${loc} missing ${key}`).toBeTruthy();
      }
    });
  }

  it('keeps the {{severity}} placeholder in every translation of the alert caption', () => {
    for (const [loc, dict] of Object.entries(catalogs)) {
      expect(resolve(dict, 'momus.eye.captionAlert'), loc).toContain('{{severity}}');
    }
  });

  it('actually translates the stale caption — a copied English string is not a translation', () => {
    const base = resolve(catalogs.en, 'momus.eye.captionStale');
    for (const loc of ['ru', 'es', 'fr', 'zh']) {
      expect(resolve(catalogs[loc], 'momus.eye.captionStale'), loc).not.toBe(base);
    }
  });
});
