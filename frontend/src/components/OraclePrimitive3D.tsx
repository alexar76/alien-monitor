import { useEffect, useRef, useState } from 'react';
import { SCENE_LOADERS } from '../oracleScenes/loaders';
import { oracleSceneMeta } from '../oracleScenes/meta';

// All previews and full scenes are served by the monitor itself. WebGL scenes
// use their own document so they do not share the galaxy's React/Canvas tree.
const ASSET_BASE = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');

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
 * at a full-screen virtual size and CSS-scale it to FIT the box, keeping the
 * HUD proportions the scene was authored for. pointer-events are disabled so a
 * click falls through to the wrapping "open full scene" link.
 */
const AMBIENT_W = 1280;
const AMBIENT_H = 720;
/** Reveal only our own scene's ready signal, never an arbitrary iframe load. */
function LocalSceneFrame({ slug, src, accent }: { slug: string; src: string; accent: string }) {
  const ref = useRef<HTMLIFrameElement>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const receive = (event: MessageEvent) => {
      if (event.origin !== window.location.origin || event.source !== ref.current?.contentWindow) return;
      if (event.data?.slug !== slug) return;
      if (event.data.type === 'oracle-scene-ready') setReady(true);
      if (event.data.type === 'oracle-scene-error') setReady(false);
    };
    window.addEventListener('message', receive);
    return () => window.removeEventListener('message', receive);
  }, [slug]);
  return (
    <>
      {!ready && <Poster accent={accent} label={slug.toUpperCase()} />}
      <iframe
        ref={ref}
        src={src}
        title={`${slug} live scene`}
        loading="eager"
        className="absolute inset-0 h-full w-full"
        style={{ border: 'none', pointerEvents: 'none', opacity: ready ? 1 : 0 }}
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
  // Contain and center the entire scene, including its edge-anchored HUD.
  const scale = Math.min(boxW / AMBIENT_W, boxHeight / AMBIENT_H);
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
  openLabel?: string;
  primitiveLabel?: string;
}

export default function OraclePrimitive3D({
  slug,
  accent,
  mobile = false,
  liveSceneUrl,
  openLabel,
  primitiveLabel,
}: Props) {
  const meta = oracleSceneMeta(slug);
  const tint = meta?.accent || accent;
  const height = mobile ? 180 : 210;
  const renderable = meta?.ambient || Object.prototype.hasOwnProperty.call(SCENE_LOADERS, slug);
  const sceneUrl = meta?.ambient
    ? `${ASSET_BASE}/ambient/${slug}/index.html`
    : `${ASSET_BASE}/oracle-scene.html?slug=${encodeURIComponent(slug)}`;
  const poster = <Poster accent={tint} label={slug.toUpperCase()} />;
  const body = meta?.ambient
    ? <AmbientFrame key={slug} slug={slug} boxHeight={height} />
    : <LocalSceneFrame key={slug} slug={slug} src={sceneUrl} accent={tint} />;

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
          href={sceneUrl}
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
