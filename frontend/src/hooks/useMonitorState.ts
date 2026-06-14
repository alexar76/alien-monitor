import { useCallback, useEffect, useRef, useState } from 'react';
import type { EcosystemState } from '../App';
import { apiUrl } from '../api';
import { useWebSocket } from './useWebSocket';

type Mode = 'test' | 'real' | 'universe';

/** WebSocket stream with HTTP /api/state fallback (fixes blank graph when WS is slow or blocked). */
export function useMonitorState(mode: Mode) {
  const [state, setState] = useState<EcosystemState | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const lastWsAt = useRef(0);
  const hasState = useRef(false);

  const handleStateUpdate = useCallback((newState: EcosystemState) => {
    lastWsAt.current = Date.now();
    hasState.current = true;
    setWsConnected(true);
    setState(newState);
  }, []);

  useWebSocket(mode, handleStateUpdate);

  useEffect(() => {
    let cancelled = false;

    const pull = async () => {
      try {
        const res = await fetch(apiUrl('/api/state'), { cache: 'no-store' });
        if (!res.ok) return;
        const data = (await res.json()) as EcosystemState;
        if (cancelled || !data?.nodes?.length) return;
        const staleWs = Date.now() - lastWsAt.current > 4000;
        if (staleWs || !hasState.current) {
          hasState.current = true;
          setState(data);
        }
      } catch {
        // ignore — overlay shows connecting state
      }
    };

    pull();
    const id = window.setInterval(pull, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [mode]);

  return { state, setState, wsConnected };
}
