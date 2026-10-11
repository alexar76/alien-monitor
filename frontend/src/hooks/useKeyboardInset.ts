import { useEffect } from 'react';

/**
 * Publishes the on-screen keyboard as CSS variables on <html>.
 *
 * iOS Safari and Android Chrome (default `interactive-widget=resizes-visual`) open the keyboard
 * over the page without shrinking the layout viewport, so a `position: fixed; bottom: …` sheet
 * keeps its composer under the keyboard. Only `window.visualViewport` knows the visible area:
 *
 * - `--kb-inset`: px of the layout viewport hidden below the visible area (the keyboard);
 * - `--vv-top`:   px the visible area is panned down (iOS scrolls to the focused field).
 *
 * Mobile sheets read them through `--sheet-top` / `--sheet-bottom` in globals.css.
 */
export function useKeyboardInset(): void {
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return undefined;
    const root = document.documentElement;
    const update = () => {
      const top = Math.max(0, vv.offsetTop);
      const inset = Math.max(0, window.innerHeight - vv.height - top);
      root.style.setProperty('--vv-top', `${Math.round(top)}px`);
      root.style.setProperty('--kb-inset', `${Math.round(inset)}px`);
      root.classList.toggle('keyboard-open', inset > 80);
    };
    update();
    vv.addEventListener('resize', update);
    vv.addEventListener('scroll', update);
    window.addEventListener('resize', update);
    return () => {
      vv.removeEventListener('resize', update);
      vv.removeEventListener('scroll', update);
      window.removeEventListener('resize', update);
      root.style.removeProperty('--vv-top');
      root.style.removeProperty('--kb-inset');
      root.classList.remove('keyboard-open');
    };
  }, []);
}
