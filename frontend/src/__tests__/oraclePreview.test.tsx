import { act, cleanup, fireEvent, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import OraclePrimitive3D from '../components/OraclePrimitive3D';
import { ORACLE_SCENE_META } from '../oracleScenes/meta';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe('local oracle previews', () => {
  it.each(Object.keys(ORACLE_SCENE_META))('%s previews and opens a local scene', (slug) => {
    const { container } = render(<OraclePrimitive3D slug={slug} accent="#fff" liveSceneUrl="https://external.invalid/?o=wrong" />);
    const frame = container.querySelector('iframe')!;
    const href = container.querySelector('a')!.getAttribute('href');
    const expected = ORACLE_SCENE_META[slug].ambient
      ? `/ambient/${slug}/index.html` : `/oracle-scene.html?slug=${slug}`;
    expect(frame.getAttribute('src')).toBe(expected);
    expect(href).toBe(expected);
  });

  it('ignores load events and unrelated messages; reveals only the rendered scene', () => {
    const { container, rerender } = render(<OraclePrimitive3D slug="lumen" accent="#fff" />);
    const frame = container.querySelector('iframe')!;
    fireEvent.load(frame);
    expect(frame.style.opacity).toBe('0');
    const message = (source: Window | null, origin: string, slug = 'lumen') => act(() => {
      window.dispatchEvent(new MessageEvent('message', {
        source, origin, data: { type: 'oracle-scene-ready', slug },
      }));
    });
    message(window, window.location.origin);
    message(frame.contentWindow, 'https://external.invalid');
    message(frame.contentWindow, window.location.origin, 'gauss');
    expect(frame.style.opacity).toBe('0');
    message(frame.contentWindow, window.location.origin);
    expect(frame.style.opacity).toBe('1');
    rerender(<OraclePrimitive3D slug="gauss" accent="#fff" />);
    expect(container.querySelector('iframe')!.style.opacity).toBe('0');
  });

  it.each([240, 320, 420])('keeps the entire Percola scene centered inside a %ipx card', (width) => {
    vi.stubGlobal('ResizeObserver', class {
      constructor(private callback: ResizeObserverCallback) {}
      observe() { this.callback([{ contentRect: { width } } as ResizeObserverEntry], this as unknown as ResizeObserver); }
      disconnect() {}
    });
    const { container } = render(<OraclePrimitive3D slug="percola" accent="#fff" />);
    const frame = container.querySelector('iframe')!;
    const match = frame.style.transform.match(/translate\(([-.\d]+)px, ([-.\d]+)px\) scale\(([-.\d]+)\)/)!;
    const [, x, y, scale] = match.map(Number);
    expect(x).toBeGreaterThanOrEqual(0);
    expect(y).toBeGreaterThanOrEqual(0);
    expect(x * 2 + 1280 * scale).toBeCloseTo(width);
    expect(y * 2 + 720 * scale).toBeCloseTo(210);
  });
});
