import { useEffect, useRef } from 'react';

type Mode = 'test' | 'real' | 'universe';

export function useWebSocket(
  mode: Mode,
  onStateUpdate: (state: any) => void,
) {
  const wsRef = useRef<WebSocket | null>(null);
  const modeRef = useRef<Mode>(mode);
  modeRef.current = mode;

  useEffect(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ cmd: 'set_mode', mode }));
    }
  }, [mode]);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const basePath = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');
    const wsUrl = `${protocol}//${window.location.host}${basePath}/ws`;

    function connect() {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        // Send current mode preference
        ws.send(JSON.stringify({ cmd: 'set_mode', mode: modeRef.current }));
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'state_update' && msg.data) {
            onStateUpdate(msg.data);
          }
        } catch {
          // ignore parse errors
        }
      };

      ws.onclose = () => {
        // Reconnect after 2 seconds
        setTimeout(connect, 2000);
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connect();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [mode, onStateUpdate]);
}
