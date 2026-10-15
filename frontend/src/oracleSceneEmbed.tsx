import { Component, Suspense, lazy, useRef } from 'react';
import type { ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Stars } from '@react-three/drei';
import { SCENE_LOADERS } from './oracleScenes/loaders';
import { oracleSceneMeta } from './oracleScenes/meta';

const slug = new URLSearchParams(location.search).get('slug') || '';
const meta = oracleSceneMeta(slug);
const loader = Object.prototype.hasOwnProperty.call(SCENE_LOADERS, slug) ? SCENE_LOADERS[slug] : undefined;
const Scene = loader ? lazy(loader) : null;

function report(type: string) {
  window.parent.postMessage({ type, slug }, window.location.origin);
}

// Signal only after the scene has committed and a frame has rendered.
function Ready({ slug }: { slug: string }) {
  const frames = useRef(0);
  useFrame(() => {
    if (++frames.current === 2) {
      document.documentElement.dataset.sceneReady = slug;
      report('oracle-scene-ready');
    }
  });
  return null;
}

class Boundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error) {
    console.warn('[OracleScene]', error);
    report('oracle-scene-error');
  }
  render() {
    return this.state.failed ? <p role="status">3D scene unavailable</p> : this.props.children;
  }
}

createRoot(document.getElementById('root')!).render(
  <Boundary>
    {Scene ? (
          <Canvas
            style={{ position: 'absolute', inset: 0 }}
            // Non-interactive thumbnail: it only auto-spins; a click opens the
            // full scene via the wrapping link.
            camera={{ position: meta?.camera || [0, 2, 14], fov: 48 }}
            dpr={[1, 1.25]}
            gl={{ antialias: true, alpha: false, powerPreference: 'low-power' }}
            frameloop="always"
          >
            <color attach="background" args={['#04030f']} />
            <fog attach="fog" args={['#04030f', 18, 55]} />
            <ambientLight intensity={0.18} />
            <pointLight position={[8, 10, 6]} intensity={2.2} color="#6ee7ff" />
            <pointLight position={[-6, 5, -4]} intensity={1.5} color="#c084fc" />
            <pointLight position={[0, -3, 8]} intensity={0.6} color="#f472b6" />
            <Stars radius={90} depth={45} count={500} factor={3} fade speed={0.5} />
            <Suspense fallback={null}>
              <Scene />
              <Ready slug={slug} />
            </Suspense>
            <OrbitControls enablePan={false} enableZoom={false} enableRotate={false} autoRotate autoRotateSpeed={0.55} />
          </Canvas>
    ) : <p role="status">Unknown scene</p>}
  </Boundary>,
);
