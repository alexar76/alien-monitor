import { useCallback, useEffect, useRef, useState } from 'react';
import type { EcoNode, EcoLink } from '../App';
import { apiUrl } from '../api';
import { monitorAuthHeaders } from '../monitorAuth';
import {
  EMPTY_CHART,
  chartFromNodes,
  fetchChart,
  fetchWindow,
  mergeWindow,
  windowIsStale,
  type MapPointer,
  type MapWindow,
  type StarChart,
} from '../lib/mapWindow';

interface Viewport {
  x: number;
  y: number;
  z: number;
  radius: number;
}

/**
 * The map when it is bigger than a message.
 *
 * Past the server's threshold the tick carries only this deployment's own ecosystem and a
 * pointer — total, and an epoch for the star chart. This hook turns that into something the
 * scene can draw: the chart fetched once per epoch into typed arrays, and a window of full
 * nodes refetched when the camera has actually travelled.
 *
 * Below the threshold it does nothing at all: `windowed` is false, the tick already holds
 * everything, and the chart is derived locally from the nodes on screen.
 */
export function useWindowedMap(
  nodes: EcoNode[],
  links: EcoLink[],
  pointer: MapPointer | null | undefined,
) {
  const windowed = Boolean(pointer?.windowed);
  const epoch = pointer?.epoch || '';
  const [chart, setChart] = useState<StarChart>(EMPTY_CHART);
  const [window_, setWindow] = useState<MapWindow | null>(null);
  const loadedEpoch = useRef('');
  const lastView = useRef<Viewport | null>(null);
  const inFlight = useRef(false);
  const focus = useRef<string[]>([]);

  // ── the chart, once per epoch ──────────────────────────────────────────────
  useEffect(() => {
    if (!windowed || !epoch || loadedEpoch.current === epoch) return;
    let cancelled = false;
    loadedEpoch.current = epoch;
    (async () => {
      try {
        const next = await fetchChart(
          apiUrl,
          { headers: monitorAuthHeaders(), credentials: 'same-origin' },
          pointer?.digest_page || 4000,
        );
        if (!cancelled) setChart(next);
      } catch {
        // A failed or superseded chart must not pin the epoch: clearing it lets the next
        // tick try again rather than leaving the map permanently starless.
        if (!cancelled) loadedEpoch.current = '';
      }
    })();
    return () => { cancelled = true; };
  }, [windowed, epoch, pointer?.digest_page]);

  // Small map: the chart is just what is already here.
  useEffect(() => {
    if (windowed) return;
    setChart(chartFromNodes(nodes));
    setWindow(null);
    loadedEpoch.current = '';
    lastView.current = null;
  }, [windowed, nodes]);

  const loadWindow = useCallback(async (view: Viewport, force = false) => {
    if (!windowed || inFlight.current) return;
    if (!force && !windowIsStale(lastView.current, view)) return;
    inFlight.current = true;
    lastView.current = view;
    try {
      const got = await fetchWindow(
        apiUrl,
        { headers: monitorAuthHeaders(), credentials: 'same-origin' },
        { x: view.x, y: view.y, z: view.z, radius: view.radius, focus: focus.current },
      );
      setWindow(got);
    } catch {
      // Keep the last good window: an empty map is a worse answer than a stale one.
      lastView.current = null;
    } finally {
      inFlight.current = false;
    }
  }, [windowed]);

  const onCameraMove = useCallback(
    (center: { x: number; y: number; z: number }, radius: number) => {
      void loadWindow({ ...center, radius });
    },
    [loadWindow],
  );

  /** A star the client has no node for. Ask for it by name, wherever the camera is. */
  const onPickUnloaded = useCallback(
    (id: string) => {
      if (!windowed) return;
      focus.current = [id];
      const view = lastView.current || { x: 0, y: 0, z: 0, radius: 40 };
      void loadWindow(view, true);
    },
    [windowed, loadWindow],
  );

  const merged = mergeWindow(nodes, links, windowed ? window_ : null);
  return { windowed, chart, onCameraMove, onPickUnloaded, ...merged };
}
