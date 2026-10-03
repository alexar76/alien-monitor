import { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import MomusEyeCanvas, { NEUTRAL_DRIVE, type EyeDrive } from './components/MomusEyeCanvas';

/** Standalone embed entry — loaded inside an iframe from the node panel. */
function MomusEyeEmbed() {
  const drive = useRef<EyeDrive>({ ...NEUTRAL_DRIVE, frozen: false });
  const [running, setRunning] = useState(true);

  useEffect(() => {
    const onMsg = (event: MessageEvent) => {
      const data = event.data;
      if (!data || data.type !== 'momus-eye-drive') return;
      drive.current.alert = typeof data.alert === 'number' ? data.alert : 0;
      drive.current.scanning = !!data.scanning;
      drive.current.frozen = !!data.frozen;
      drive.current.px = typeof data.px === 'number' ? data.px : 0;
      drive.current.py = typeof data.py === 'number' ? data.py : 0;
      drive.current.hover = !!data.hover;
      setRunning(data.running !== false && !drive.current.frozen);
    };
    window.addEventListener('message', onMsg);
    window.parent?.postMessage({ type: 'momus-eye-ready' }, '*');
    return () => window.removeEventListener('message', onMsg);
  }, []);

  return (
    <MomusEyeCanvas
      drive={drive}
      running={running}
      fps={24}
      dpr={[1, 1.5]}
    />
  );
}

createRoot(document.getElementById('root')!).render(<MomusEyeEmbed />);
