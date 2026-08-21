import { lazy, Suspense } from 'react';
import type { EcoNode } from '../App';
import MomusEye from '../components/MomusEye';
import OraclePrimitive3D from '../components/OraclePrimitive3D';
import type { ResolvedNodeScene } from './resolve';

const MetisStarCanvas = lazy(() => import('../components/MetisStarCanvas'));
const UseCasesGlobe = lazy(() => import('./UseCasesGlobe'));
const SignalHuntField = lazy(() => import('./SignalHuntField'));
const ThemisGate = lazy(() => import('./ThemisGate'));

/**
 * Shared chrome for every node preview under title+description.
 * Implementations stay product-local; this only frames them uniformly.
 */

interface Props {
  scene: ResolvedNodeScene;
  node: EcoNode;
  themeColor: string;
  mobile?: boolean;
  t: (key: string, vars?: Record<string, string | number>, defaultValue?: string) => string;
}

function Frame({
  accent,
  mobile,
  children,
  caption,
  liveUrl,
  openLabel,
}: {
  accent: string;
  mobile?: boolean;
  children: React.ReactNode;
  caption: string;
  liveUrl?: string;
  openLabel: string;
}) {
  const body = (
    <div
      className="relative w-full rounded-lg overflow-hidden"
      style={{
        height: mobile ? 150 : 190,
        border: `1px solid ${accent}33`,
        backgroundColor: '#03040a',
        boxShadow: `inset 0 0 24px ${accent}11`,
      }}
    >
      {children}
    </div>
  );

  return (
    <div className="mb-4" onClick={(e) => e.stopPropagation()}>
      {liveUrl ? (
        <a
          href={liveUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="block group"
          title={openLabel}
        >
          {body}
          <div className="mt-1 flex items-center justify-between gap-2">
            <div className="text-[10px] font-mono leading-snug text-white/40">{caption}</div>
            <div
              className="text-[10px] font-mono shrink-0 opacity-70 group-hover:opacity-100 transition-opacity"
              style={{ color: accent }}
            >
              {openLabel} →
            </div>
          </div>
        </a>
      ) : (
        <>
          {body}
          <div className="mt-1 text-[10px] font-mono leading-snug text-white/40">{caption}</div>
        </>
      )}
    </div>
  );
}

function Fallback({ accent }: { accent: string }) {
  return (
    <div
      className="absolute inset-0"
      style={{
        background: `radial-gradient(40% 30% at 50% 50%, ${accent}33 0%, transparent 70%)`,
      }}
    />
  );
}

export default function NodeSceneSlot({ scene, node, themeColor, mobile = false, t }: Props) {
  const openLabel = t('nodeDetail.oracle.openScene', undefined, 'Open full scene');

  if (scene.kind === 'oracle') {
    const embedUrl = node.url
      ? node.url + (node.url.includes('?') ? '&' : '?') + 'embed=1'
      : undefined;
    return (
      <div className="mb-4" onClick={(e) => e.stopPropagation()}>
        <OraclePrimitive3D
          slug={scene.slug}
          accent={themeColor}
          mobile={mobile}
          liveSceneUrl={node.url}
          embedUrl={embedUrl}
          openLabel={openLabel}
          primitiveLabel={scene.meta.primitive}
        />
      </div>
    );
  }

  const { entry, accent } = scene;
  const caption = t(entry.captionKey, undefined, entry.captionDefault);
  const liveUrl = entry.liveUrlFromNode ? node.url : undefined;

  if (entry.kind === 'momus') {
    return (
      <div className="mb-4" onClick={(e) => e.stopPropagation()}>
        <MomusEye live={node.momus_live} accent={themeColor} mobile={mobile} />
      </div>
    );
  }

  if (entry.kind === 'atlas') {
    const embed = node.atlas_live?.embed_url || node.links?.embed;
    if (!embed) return null;
    return (
      <Frame accent={accent} mobile={mobile} caption={caption} liveUrl={liveUrl} openLabel={openLabel}>
        <iframe
          title={t('common.atlasMiniMap', undefined, 'ATLAS mini map')}
          src={embed}
          className="w-full h-full border-0 block"
          loading="lazy"
          referrerPolicy="no-referrer"
          sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"
        />
      </Frame>
    );
  }

  if (entry.kind === 'metis') {
    return (
      <Frame accent={accent} mobile={mobile} caption={caption} liveUrl={liveUrl} openLabel={openLabel}>
        <Suspense fallback={<Fallback accent={accent} />}>
          <MetisStarCanvas
            running
            fps={mobile ? 18 : 24}
            dpr={mobile ? [1, 1] : [1, 1.25]}
            spikeCount={mobile ? 160 : 260}
          />
        </Suspense>
      </Frame>
    );
  }

  if (entry.kind === 'use_cases') {
    return (
      <Frame accent={accent} mobile={mobile} caption={caption} liveUrl={liveUrl} openLabel={openLabel}>
        <Suspense fallback={<Fallback accent={accent} />}>
          <UseCasesGlobe accent={accent} mobile={mobile} />
        </Suspense>
      </Frame>
    );
  }

  if (entry.kind === 'signal_hunt') {
    return (
      <Frame accent={accent} mobile={mobile} caption={caption} liveUrl={liveUrl} openLabel={openLabel}>
        <Suspense fallback={<Fallback accent={accent} />}>
          <SignalHuntField accent={accent} mobile={mobile} />
        </Suspense>
      </Frame>
    );
  }

  if (entry.kind === 'themis') {
    return (
      <Frame accent={accent} mobile={mobile} caption={caption} liveUrl={liveUrl} openLabel={openLabel}>
        <Suspense fallback={<Fallback accent={accent} />}>
          <ThemisGate node={node} accent={accent} mobile={mobile} />
        </Suspense>
      </Frame>
    );
  }

  return null;
}
