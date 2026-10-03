import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import OraclePrimitive3D from './components/OraclePrimitive3D';

/**
 * Dev-only: render a single oracle preview in isolation, exactly as the node card does.
 *
 * Exists because "the preview box is black" has at least four possible causes — the chunk not
 * loading, the scene throwing, the scene suspending forever, or the app never selecting a node
 * — and only isolation tells them apart. Open /scene-probe.html?slug=chronos.
 */
const slug = new URLSearchParams(location.search).get('slug') || 'chronos';
(window as unknown as { __probeSlug: string }).__probeSlug = slug;

createRoot(document.getElementById('box')!).render(
  <StrictMode>
    <OraclePrimitive3D slug={slug} accent="#c084fc" />
  </StrictMode>,
);
