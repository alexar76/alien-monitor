import { describe, expect, it } from 'vitest';

/**
 * Performance guards on the two canvas settings that cost the most and were both paying for
 * nothing. Asserted against the SOURCE, because the cost is decided at Canvas construction and
 * there is no browser in this runner.
 *
 * Sources are pulled in with Vite's `?raw` rather than node:fs: this project's tsconfig has no
 * node types, so a `node:fs` import here fails `tsc -b` — which is what the production Docker
 * build runs, so the test would have broken the deploy rather than the code.
 */
const RAW = import.meta.glob('../**/*.{ts,tsx}', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;

function source(suffix: string): string {
  const key = Object.keys(RAW).find((k) => k.endsWith(suffix));
  if (!key) throw new Error(`source not found: ${suffix} (have ${Object.keys(RAW).length} files)`);
  return RAW[key];
}

describe('galaxy canvas', () => {
  it('does not preserve its drawing buffer', () => {
    // The flag forbids Chrome's compositor fast path and nothing in the app reads this canvas.
    // It was the difference between "fast in Firefox" and "crawls in Chrome".
    expect(source('components/EcosystemGraph.tsx')).toContain('preserveDrawingBuffer: false');
  });

  it('has no pixel reader that would justify preserving it', () => {
    // If a screenshot feature ever appears, this fails and the flag can be reconsidered —
    // deliberately, and for that render only.
    expect(source('hooks/useWebGLCanvasReady.ts')).toContain('toDataURL');
    expect(source('App.tsx')).not.toContain('useWebGLCanvasReady');
  });

  it('caps desktop device pixel ratio at 1.5', () => {
    expect(source('components/EcosystemGraph.tsx')).toMatch(/dpr=\{isMobile \? \[1, 1\.25\] : \[1, 1\.5\]\}/);
  });
});

describe('Momus eye embed', () => {
  it('uses an iframe instead of a second inline WebGL canvas in the monitor page', () => {
    const src = source('components/MomusEye.tsx');
    expect(src).toContain('momus-eye.html');
    expect(src).toContain('momus-eye-iframe');
    expect(src).not.toMatch(/lazy\(\(\) => import\('\.\/MomusEyeCanvas'\)\)/);
  });
});

describe('oracle preview', () => {
  it('prefers the portal iframe over a second WebGL context', () => {
    // The monitor page already runs a full-viewport WebGL canvas. A second context in the same
    // document gets starved: measured on the live page at 0.1% lit pixels, while the same
    // bundle renders the same scene at 5-30% in isolation. The iframe has its own document.
    const wrapper = source('components/OraclePrimitive3D.tsx');
    const iframeAt = wrapper.indexOf('if (portalEmbed) {');
    const sceneAt = wrapper.indexOf('if (Scene) {');
    expect(iframeAt).toBeGreaterThan(-1);
    expect(sceneAt).toBeGreaterThan(-1);
    expect(iframeAt).toBeLessThan(sceneAt);
  });

  it('keeps the local scene as a fallback', () => {
    expect(source('components/OraclePrimitive3D.tsx')).toContain('if (Scene) {');
  });
});
