import { Component, Suspense, lazy, useEffect, useMemo, useRef, useState } from 'react';
import type { ComponentType, LazyExoticComponent, ReactNode } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Stars } from '@react-three/drei';
import { SCENE_LOADERS } from '../oracleScenes/loaders';
import { oracleSceneMeta } from '../oracleScenes/meta';

/**
 * Local, self-contained 3D preview of an oracle's mathematical primitive, shown
 * in the node detail panel — a thumbnail of the selected node. Renders the real
 * animated R3F scene (ported from the Oracle Family portal) for the 13 WebGL
 * oracles, and a bundled HTML-canvas iframe for the 4 "ambient" oracles, so the
 * preview always works with no dependency on the remote site.
 *
 * Prefer the local scene over a portal `?embed=1` iframe: the remote embed can
 * sit on a black box for many seconds while the portal JS/WebGL boots. The
 * accent poster paints immediately under whatever is loading.
 *
 * The preview is non-interactive (auto-spins only); clicking anywhere on it
 * opens the FULL-SCREEN live 3D visualization in a new tab — see liveSceneUrl.
 */

// Cache one lazy component per slug so re-opening a panel never re-creates it.
const sceneCache: Record<string, LazyExoticComponent<ComponentType>> = {};
function getScene(slug: string): LazyExoticComponent<ComponentType> | null {
  const loader = SCENE_LOADERS[slug];
  if (!loader) return null;
  if (!sceneCache[slug]) sceneCache[slug] = lazy(loader);
  return sceneCache[slug];
}

const ASSET_BASE = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');

class SceneBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: Error) {
    console.warn('[OraclePrimitive3D] local scene failed — using fallback', error);
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

function Poster({ accent, label }: { accent: string; label?: string }) {
  return (
    <div
      className="absolute inset-0 flex items-center justify-center"
      style={{
        background: `radial-gradient(115% 85% at 50% 16%, ${accent}33, transparent 60%), radial-gradient(90% 70% at 82% 104%, ${accent}22, transparent 70%), #04030f`,
      }}
    >
      {label && (
        <span className="font-mono text-xs tracking-wider" style={{ color: accent, opacity: 0.7 }}>
          {label}
        </span>
      )}
    </div>
  );
}

/**
 * Ambient oracles ship as full-viewport HTML-canvas visuals (fixed-size HUD,
 * corner-anchored text). To read well in a small thumbnail we render the iframe
 * at a full-screen virtual size and CSS-scale it to COVER the box, keeping the
 * HUD proportions the scene was authored for. pointer-events are disabled so a
 * click falls through to the wrapping "open full scene" link.
 */
const AMBIENT_W = 1280;
const AMBIENT_H = 720;
/** Portal embed fallback — poster stays visible until the iframe paints. */
function PortalEmbedFrame({
  embedUrl,
  title,
  accent,
  label,
}: {
  embedUrl: string;
  title: string;
  accent: string;
  label?: string;
}) {
  const [loaded, setLoaded] = useState(false);
  // The portal is a full 3D app and takes ~5s to fire `load` (measured: 4.8s). Until then the
  // poster covers the iframe, because an iframe revealed before it paints shows its own black
  // background — which is exactly the "empty box" this whole change is about. The timer is the
  // safety net: if `load` never arrives (a blocked subresource, a proxy that swallows the
  // event), reveal anyway rather than leaving a poster up forever.
  useEffect(() => {
    if (loaded) return;
    const t = window.setTimeout(() => setLoaded(true), 9000);
    return () => window.clearTimeout(t);
  }, [loaded]);
  return (
    <>
      {!loaded && <Poster accent={accent} label={label} />}
      <iframe
        src={embedUrl}
        title={title}
        loading="eager"
        onLoad={() => setLoaded(true)}
        className="absolute inset-0 h-full w-full"
        style={{ border: 'none', pointerEvents: 'none', opacity: loaded ? 1 : 0 }}
        sandbox="allow-scripts allow-same-origin"
        tabIndex={-1}
        aria-hidden="true"
      />
    </>
  );
}

function AmbientFrame({ slug, boxHeight }: { slug: string; boxHeight: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const [boxW, setBoxW] = useState(320);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(([e]) => setBoxW(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  // Cover-fit: scale from the top-left, then shift up/left by half the overflow
  // so the scaled scene is centered (px offsets — % would resolve against the
  // un-scaled 1280×720 and mis-center).
  const scale = Math.max(boxW / AMBIENT_W, boxHeight / AMBIENT_H);
  const offX = (AMBIENT_W * scale - boxW) / 2;
  const offY = (AMBIENT_H * scale - boxHeight) / 2;
  return (
    <div ref={ref} className="absolute inset-0" style={{ overflow: 'hidden' }}>
      <iframe
        src={`${ASSET_BASE}/ambient/${slug}/index.html`}
        title={`${slug} live preview`}
        loading="lazy"
        tabIndex={-1}
        aria-hidden="true"
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: AMBIENT_W,
          height: AMBIENT_H,
          border: 'none',
          pointerEvents: 'none',
          transformOrigin: 'top left',
          transform: `translate(${-offX}px, ${-offY}px) scale(${scale})`,
        }}
      />
    </div>
  );
}

interface Props {
  slug: string;
  /** Panel theme colour, used for the poster glow + math caption. */
  accent: string;
  mobile?: boolean;
  /** Full-screen live 3D scene; clicking the preview opens it (if present). */
  liveSceneUrl?: string;
  /** Oracle-family portal embed (`?embed=1`) — failure fallback only; local R3F is preferred. */
  embedUrl?: string;
  openLabel?: string;
  primitiveLabel?: string;
}

export default function OraclePrimitive3D({
  slug,
  accent,
  mobile = false,
  liveSceneUrl,
  embedUrl,
  openLabel,
  primitiveLabel,
}: Props) {
  const meta = oracleSceneMeta(slug);
  const tint = meta?.accent || accent;
  const Scene = !meta?.ambient ? getScene(slug) : null;
  const height = mobile ? 180 : 210;

  // Nothing we can render for this slug → let the caller hide the block.
  const renderable = meta?.ambient || !!Scene || !!embedUrl;

  const poster = useMemo(
    () => <Poster accent={tint} label={slug.toUpperCase()} />,
    [tint, slug],
  );

  const portalEmbed = !meta?.ambient && embedUrl ? embedUrl : null;

  const body = useMemo(() => {
    if (meta?.ambient) {
      return <AmbientFrame slug={slug} boxHeight={height} />;
    }
    // ── Portal iframe FIRST, local R3F only as a fallback ────────────────────────
    // This order was committed once, then flipped to local-first in a working-tree change
    // that shipped to production and made the previews black. The reason for the original
    // order is in the monitor page itself: it already runs a full-viewport WebGL canvas for
    // the galaxy, and a SECOND context in the same document gets starved — measured on the
    // live page at 0.1% lit pixels and 7 distinct colours, i.e. the stars and nothing else,
    // while the very same production bundle renders the same scene at 5–30% lit in isolation.
    // The iframe carries its own document and its own context, so it does not compete.
    //
    // The local scene stays as the fallback: a deployment with no portal to embed still shows
    // the primitive rather than an empty box.
    if (portalEmbed) {
      return (
        <PortalEmbedFrame
          embedUrl={portalEmbed}
          title={`${slug} live scene`}
          accent={tint}
          label={slug.toUpperCase()}
        />
      );
    }
    if (Scene) {
      return (
        <SceneBoundary fallback={poster}>
          <Canvas
            className="absolute inset-0"
            // Non-interactive thumbnail: it only auto-spins; a click opens the
            // full scene via the wrapping link.
            style={{ pointerEvents: 'none' }}
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
            <Stars radius={90} depth={45} count={mobile ? 280 : 500} factor={3} fade speed={0.5} />
            <Suspense fallback={null}>
              <Scene />
            </Suspense>
            <OrbitControls enablePan={false} enableZoom={false} enableRotate={false} autoRotate autoRotateSpeed={0.55} />
          </Canvas>
        </SceneBoundary>
      );
    }
    // Neither a portal to embed nor a local scene for this slug.
    return poster;
  }, [slug, meta?.ambient, meta?.camera, portalEmbed, Scene, height, tint, poster, mobile]);

  if (!renderable) return null;

  const box = (
    <div
      className="group relative w-full rounded-lg"
      style={{
        height,
        overflow: 'hidden',
        border: `1px solid ${tint}33`,
        backgroundColor: '#04030f',
        boxShadow: `inset 0 0 24px ${tint}11`,
      }}
    >
      {poster}
      {body}
      {liveSceneUrl && (
        <div
          className="pointer-events-none absolute inset-0 flex items-end justify-end p-2 opacity-0 transition-opacity duration-200 group-hover:opacity-100"
          style={{ background: 'linear-gradient(to top, rgba(0,0,0,0.55), transparent 45%)' }}
        >
          <span className="font-mono text-[10px] tracking-wide" style={{ color: tint }}>
            {openLabel || 'Open full scene'} ↗
          </span>
        </div>
      )}
    </div>
  );

  return (
    <div className="mb-4">
      {liveSceneUrl ? (
        <a
          href={liveSceneUrl}
          target="_blank"
          rel="noreferrer"
          aria-label={`${openLabel || 'Open full scene'} — ${slug}`}
          className="block cursor-pointer"
          onClick={(e) => e.stopPropagation()}
        >
          {box}
        </a>
      ) : (
        box
      )}
      {primitiveLabel && (
        <p className="mt-1.5 text-[10px] font-mono leading-snug text-white/40">{primitiveLabel}</p>
      )}
    </div>
  );
}
