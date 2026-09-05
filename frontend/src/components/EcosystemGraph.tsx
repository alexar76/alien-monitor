import { Component, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import {
  OrbitControls,
  Sphere,
  Line,
  Html,
  Stars,
} from '@react-three/drei';
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib';
import { EffectComposer, Bloom, Vignette, Noise } from '@react-three/postprocessing';
import * as THREE from 'three';
import type { EcoNode, EcoLink, EcosystemState } from '../App';
import { useIsMobile } from '../hooks/useIsMobile';
import { sanitizeEcoGraphNodes } from '../lib/ecoGraphSanitize';
import { chartFromNodes, type StarChart } from '../lib/mapWindow';
import {

  LABEL_BUDGET,
  labelTargets,
  LIT_HUB_BUDGET,
  REAL_NODE_BUDGET,
  cameraRange,
  isFederation,
  isHubRole,
  nearestHubs,
  visibleNodes,
} from '../lib/federationLayout';

/** Map labels get the NAME, the panel gets the sentence.
 *
 * Peers in this federation name themselves "NAME — what it does" (ATLAS, GAIA, MOMUS, CHARON
 * all do). Rendered whole on a 3D label with `whitespace-nowrap`, the tagline runs off the
 * viewport and overlaps its neighbours. The panel still shows the full string, so nothing is
 * hidden — it is just not written across the map.
 */
export function shortLabel(label: string): string {
  const s = String(label || '');
  const cut = s.split(/\s[—–-]\s/)[0].trim();
  const base = cut || s;
  return base.length > 28 ? base.slice(0, 27).trimEnd() + '…' : base;
}

// ---------------------------------------------------------------------------
// Color mapping
// ---------------------------------------------------------------------------
const GROUP_COLORS: Record<string, string> = {
  core: '#00f0ff',
  contract: '#ff00ff',
  client: '#00ff88',
  infra: '#7b2fff',
  sdk: '#ffdd00',
  network: '#3366ff',
  chain: '#ff6633',
  product: '#ffaa44',
  factory_product: '#ffaa44',
  economy: '#ffd700',
  cluster: '#ffcc66',
  agent: '#66ffcc',
  oracle: '#a64dff',
  argus: '#36e6ff',
  community: '#c9a227',
  media: '#ff4466',
  observability: '#00e5cc',
  cognition: '#9b59ff',
  physical: '#43e65a',
  security: '#ff2d6f',
  // A federated hub is not a capability service and must not look like one: these are the
  // colours that let an operator tell "another hub" from "a thing that answers calls", and
  // "its peers" from ours. Without an entry a node falls back to core cyan and reads as ours.
  peer_hub: '#38e0ff',
  peer_hub_node: '#7fd4ff',
  // A hub somebody else observed but nobody approved, seen from one hop further out:
  // the amber of a stranger, dimmed to the weight of a planet.
  pending_hub_node: '#c9a04d',
  pending_hub: '#ffcc4d',
  // A federated service that declared no categories. Not core cyan (that reads as ours) and
  // not any family's colour (that would be a guess) — see backend/node_palette.py, which
  // stamps the real colour whenever the peer said what it does.
  peer_hub_provider: '#8a93a6',
};

const GROUP_EMISSIVE: Record<string, string> = {
  core: '#004466',
  contract: '#440044',
  client: '#004422',
  infra: '#220066',
  sdk: '#443300',
  network: '#001144',
  chain: '#441100',
  product: '#553300',
  factory_product: '#553300',
  economy: '#665500',
  cluster: '#664422',
  agent: '#113322',
  oracle: '#3a0a66',
  argus: '#0a3344',
  community: '#3d3010',
  media: '#440a14',
  observability: '#003328',
  cognition: '#220044',
  physical: '#0d4417',
  security: '#440a1a',
  peer_hub: '#0a3a44',
  peer_hub_node: '#12303d',
  peer_hub_provider: '#1b1f27',
  pending_hub_node: '#2b2312',
  pending_hub: '#443311',
};

const getNodeColor = (g: string) => GROUP_COLORS[g] || '#00f0ff';
const getNodeEmissive = (g: string) => GROUP_EMISSIVE[g] || '#001122';

function clamp01(n: number): number {
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

/** Federation / LUMEN-style trust in metrics (0..1 or 0..100). */
function nodeTrust01(node: EcoNode): number | null {
  const m = node.metrics || {};
  const raw = m.trust_score ?? m.trust ?? m.lumen_score ?? m.reputation;
  if (raw == null || !Number.isFinite(Number(raw))) return null;
  const v = Number(raw);
  return clamp01(v > 1 ? v / 100 : v);
}

/** Fatter sphere when more trusted. Primary hub stays the sun; peers stay leaner. */
function hubNodeSize(node: EcoNode): number {
  const trust = nodeTrust01(node);
  const t = trust == null ? (node.id === 'hub' ? 1 : 0.45) : trust;
  if (node.id === 'hub') return 0.52 + 0.28 * t; // ~0.52..0.80
  return 0.34 + 0.22 * t; // ~0.34..0.56 — smaller sun for competing hubs
}

// ---------------------------------------------------------------------------
// Wormhole — spiral particle tunnel along a connection
// ---------------------------------------------------------------------------
function WormholeTunnel({
  src,
  tgt,
  color,
  intensity,
}: {
  src: THREE.Vector3;
  tgt: THREE.Vector3;
  color: string;
  intensity: number;
}) {
  const pointsRef = useRef<THREE.Points>(null!);
  const particleCount = 60;

  const { positions, randoms } = useMemo(() => {
    const pos = new Float32Array(particleCount * 3);
    const rnd = new Float32Array(particleCount);
    for (let i = 0; i < particleCount; i++) {
      rnd[i] = Math.random();
      pos[i * 3] = 0;
      pos[i * 3 + 1] = 0;
      pos[i * 3 + 2] = 0;
    }
    return { positions: pos, randoms: rnd };
  }, [particleCount]);

  useFrame(({ clock }) => {
    if (!pointsRef.current) return;
    const t = clock.getElapsedTime();
    const posArr = pointsRef.current.geometry.attributes.position.array as Float32Array;

    for (let i = 0; i < particleCount; i++) {
      const progress = ((t * 0.3 + randoms[i]) % 1);
      // Spiral offset
      const spiralRadius = 0.15 * Math.sin(progress * Math.PI);
      const angle = progress * Math.PI * 6 + i * 0.5;
      const ox = Math.cos(angle) * spiralRadius;
      const oy = Math.sin(angle) * spiralRadius;
      const oz = 0;

      // Interpolate between src and tgt
      posArr[i * 3] = src.x + (tgt.x - src.x) * progress + ox;
      posArr[i * 3 + 1] = src.y + (tgt.y - src.y) * progress + oy;
      posArr[i * 3 + 2] = src.z + (tgt.z - src.z) * progress + oz;
    }
    pointsRef.current.geometry.attributes.position.needsUpdate = true;
  });

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          array={positions}
          count={particleCount}
          itemSize={3}
        />
      </bufferGeometry>
      <pointsMaterial
        size={0.06}
        color={color}
        transparent
        opacity={0.8 * intensity}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

// ---------------------------------------------------------------------------
// Nebula cloud — particle cluster around a position
// ---------------------------------------------------------------------------
function NebulaCloud({
  center,
  color,
  radius = 2,
  count = 300,
}: {
  center: THREE.Vector3;
  color: string;
  radius?: number;
  count?: number;
}) {
  const pointsRef = useRef<THREE.Points>(null!);
  const { positions } = useMemo(() => {
    const pos = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      const r = radius * (0.3 + Math.random() * 0.7);
      pos[i * 3] = center.x + r * Math.sin(phi) * Math.cos(theta);
      pos[i * 3 + 1] = center.y + r * Math.sin(phi) * Math.sin(theta);
      pos[i * 3 + 2] = center.z + r * Math.cos(phi);
    }
    return { positions: pos };
  }, [center, radius, count]);

  useFrame(({ clock }) => {
    if (!pointsRef.current) return;
    const t = clock.getElapsedTime();
    pointsRef.current.rotation.y += 0.0001;
    pointsRef.current.rotation.x += 0.00005;
    const mat = pointsRef.current.material as THREE.PointsMaterial;
    mat.opacity = 0.06 + Math.sin(t * 0.5) * 0.02;
  });

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" array={positions} count={count} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial
        size={0.08}
        color={color}
        transparent
        opacity={0.06}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

// ---------------------------------------------------------------------------
// Asteroid belt — ring of particles around origin
// ---------------------------------------------------------------------------
function AsteroidBelt({
  radius,
  color,
  count = 400,
  tilt = 0,
}: {
  radius: number;
  color: string;
  count?: number;
  tilt?: number;
}) {
  const pointsRef = useRef<THREE.Points>(null!);

  const { positions } = useMemo(() => {
    const pos = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const angle = (i / count) * Math.PI * 2 + (Math.random() - 0.5) * 0.3;
      const r = radius + (Math.random() - 0.5) * 0.6;
      pos[i * 3] = Math.cos(angle) * r;
      pos[i * 3 + 1] = (Math.random() - 0.5) * 0.15;
      pos[i * 3 + 2] = Math.sin(angle) * r;
    }
    return { positions: pos };
  }, [radius, count]);

  useFrame((_, delta) => {
    if (pointsRef.current) {
      pointsRef.current.rotation.y += delta * 0.05;
      if (tilt) pointsRef.current.rotation.x = tilt;
    }
  });

  return (
    <points ref={pointsRef} rotation={[tilt, 0, 0]}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" array={positions} count={count} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial
        size={0.04}
        color={color}
        transparent
        opacity={0.15}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

// ---------------------------------------------------------------------------
// Solar Corona — glowing atmosphere around a hub (primary or competing)
// ---------------------------------------------------------------------------
function SolarCorona({
  color,
  intensity,
  scale = 1,
}: {
  color: string;
  intensity: number;
  scale?: number;
}) {
  const groupRef = useRef<THREE.Group>(null!);
  const layers = [0.65, 0.75, 0.9, 1.1].map((r) => r * scale);

  useFrame(({ clock }) => {
    if (!groupRef.current) return;
    const t = clock.getElapsedTime();
    groupRef.current.children.forEach((mesh, i) => {
      const s = 1 + Math.sin(t * 2 + i) * 0.08 * intensity;
      mesh.scale.setScalar(s);
      ((mesh as THREE.Mesh).material as THREE.MeshBasicMaterial).opacity = (0.12 - i * 0.02) * intensity;
    });
  });

  return (
    <group ref={groupRef}>
      {layers.map((radius, i) => (
        <mesh key={i}>
          <sphereGeometry args={[radius, 48, 48]} />
          <meshBasicMaterial
            color={color}
            transparent
            opacity={0.12 - i * 0.02}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
          />
        </mesh>
      ))}
    </group>
  );
}

// ---------------------------------------------------------------------------
// Gravity well — expanding rings around a hub
// ---------------------------------------------------------------------------
function GravityWell({
  color,
  intensity,
  scale = 1,
}: {
  color: string;
  intensity: number;
  scale?: number;
}) {
  const ringRefs = useRef<THREE.Mesh[]>([]);

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    ringRefs.current.forEach((ring, i) => {
      if (!ring) return;
      const phase = i * 0.5;
      const s = (0.8 + (t * 0.3 + phase) % 4) * scale;
      ring.scale.set(s, s, s);
      ring.rotation.z += 0.002;
      ring.rotation.x += 0.001;
      (ring.material as THREE.MeshBasicMaterial).opacity =
        Math.max(0, (1 - ((t * 0.3 + phase) % 4) / 4) * 0.2 * intensity);
    });
  });

  return (
    <group>
      {[0, 1, 2, 3].map((i) => (
        <mesh
          key={i}
          ref={(el) => { ringRefs.current[i] = el!; }}
          rotation={[Math.PI / 2 + i * 0.3, i * 0.4, 0]}
        >
          <ringGeometry args={[0.5 * scale, 0.54 * scale, 80]} />
          <meshBasicMaterial
            color={color}
            transparent
            opacity={0.2}
            side={THREE.DoubleSide}
            depthWrite={false}
          />
        </mesh>
      ))}
    </group>
  );
}

/** Orbit belts that sit on secondary hubs (primary uses scene-level GravityWell). */
function HubOrbitBelts({ color, radius }: { color: string; radius: number }) {
  const g = useRef<THREE.Group>(null!);
  useFrame(() => {
    if (!g.current) return;
    g.current.rotation.y += 0.0035;
    g.current.rotation.z += 0.0012;
  });
  const belts = [
    { tilt: 0.55, yaw: 0.15, roll: 0.08, scale: 1.7, tube: 0.014, opacity: 0.62 },
    { tilt: 1.05, yaw: 0.7, roll: 0.35, scale: 2.15, tube: 0.011, opacity: 0.48 },
    { tilt: 0.28, yaw: 1.4, roll: 0.9, scale: 2.55, tube: 0.009, opacity: 0.36 },
    { tilt: 1.35, yaw: 2.1, roll: 0.2, scale: 3.05, tube: 0.007, opacity: 0.26 },
    { tilt: 0.8, yaw: 2.8, roll: 1.1, scale: 3.55, tube: 0.006, opacity: 0.18 },
  ];
  return (
    <group ref={g}>
      {belts.map((b, i) => (
        <mesh key={i} rotation={[Math.PI / 2 + b.tilt, b.yaw, b.roll]}>
          <torusGeometry args={[radius * b.scale, b.tube, 10, 64]} />
          <meshBasicMaterial
            color={color}
            transparent
            opacity={b.opacity}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
          />
        </mesh>
      ))}
    </group>
  );
}

// ---------------------------------------------------------------------------
// Cosmic dust — ambient floating particles everywhere
// ---------------------------------------------------------------------------
function CosmicDust({ color, count = 500 }: { color: string; count?: number }) {
  const pointsRef = useRef<THREE.Points>(null!);
  const spread = 25;

  const { positions } = useMemo(() => {
    const pos = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      pos[i * 3] = (Math.random() - 0.5) * spread * 2;
      pos[i * 3 + 1] = (Math.random() - 0.5) * spread * 2;
      pos[i * 3 + 2] = (Math.random() - 0.5) * spread * 2;
    }
    return { positions: pos };
  }, [count, spread]);

  useFrame((_, delta) => {
    if (pointsRef.current) {
      pointsRef.current.rotation.y += delta * 0.02;
      pointsRef.current.rotation.x += delta * 0.01;
    }
  });

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" array={positions} count={count} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial
        size={0.03}
        color={color}
        transparent
        opacity={0.15}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

// ---------------------------------------------------------------------------
// Main eco node — planet/sun style
// ---------------------------------------------------------------------------
function EcoNodeMesh({
  node,
  onClick,
  themeColor,
  pulseIntensity,
  showLabel = true,
}: {
  node: EcoNode;
  onClick: (n: EcoNode) => void;
  themeColor: string;
  pulseIntensity: number;
  /** Labels are budgeted to the nodes nearest the camera — see LABEL_BUDGET. */
  showLabel?: boolean;
}) {
  // Same budget, same reason. A sun's five orbit belts are five torus meshes; at a
  // thousand hubs that alone is five thousand of them, each with its own material and
  // frame callback. Distance decides how much of a node is actually built.
  const detailed = showLabel;
  const groupRef = useRef<THREE.Group>(null!);
  const coronaRef = useRef<THREE.Mesh>(null!);
  const orbitRingRef = useRef<THREE.Mesh>(null!);
  const [hovered, setHovered] = useState(false);

  const nodeColor = node.color || getNodeColor(node.group);
  const isActive = node.status === 'active';
  const isOracle = node.group === 'oracle';
  const isHub = isHubRole(node);
  const isPrimaryHub = node.id === 'hub';
  const showCorona = isActive || isOracle || isHub;
  const dimmed = node.status === 'offline' || node.status === 'disabled';  // offline or crypto-disabled networks/contracts → greyed out
  const nodeSize = isHub
    ? hubNodeSize(node)
    : node.group === 'core'
      ? 0.45
      : node.group === 'cluster'
        ? // A nebula holding the whole product catalogue read as the smallest ball on the
          // map — the same 0.28 as one satellite. Grow it with what it holds, gently
          // (log), so nineteen products and ninety look different without the ninety
          // swallowing the forge next to it.
          Math.min(0.78, 0.32 + 0.075 * Math.log2(1 + Number(node.metrics?.count ?? 1)))
        : node.group === 'contract'
          ? 0.38
          : 0.28;
  const baseY = node.position.y;
  const baseX = node.position.x;
  const baseZ = node.position.z;

  // Hubs stay planted — a wobbling sun plus a scene-level corona reads as two spheres.
  const wobble = useMemo(() => {
    if (isHub) {
      return { speed: 0, ampX: 0, ampY: 0, ampZ: 0, phase: 0 };
    }
    return {
      speed: 0.5 + Math.random() * 1.5,
      ampX: 0.1 + Math.random() * 0.2,
      ampY: 0.1 + Math.random() * 0.2,
      ampZ: 0.1 + Math.random() * 0.2,
      phase: Math.random() * Math.PI * 2,
    };
  }, [isHub]);

  useFrame(({ clock }) => {
    if (!groupRef.current) return;
    // A node the camera is nowhere near does not need to breathe. At five thousand nodes
    // this callback runs five thousand times a frame, and the wobble it computes is a
    // sub-pixel movement on something the size of a dot.
    if (!detailed) return;
    const t = clock.getElapsedTime();
    const p = wobble.phase;

    groupRef.current.position.x = baseX + Math.sin(t * wobble.speed + p) * wobble.ampX;
    groupRef.current.position.y = baseY + Math.cos(t * wobble.speed * 0.7 + p) * wobble.ampY;
    groupRef.current.position.z = baseZ + Math.sin(t * wobble.speed * 0.6 + p + 1) * wobble.ampZ;

    if (showCorona && coronaRef.current) {
      const pulse = isActive
        ? 1 + Math.sin(t * 3 + p) * 0.15 * pulseIntensity
        : 1 + Math.sin(t * 1.2 + p) * 0.04;
      coronaRef.current.scale.setScalar(pulse);
      (coronaRef.current.material as THREE.MeshBasicMaterial).opacity =
        (isActive ? 0.08 : 0.045) + Math.sin(t * (isActive ? 2.5 : 1.4)) * (isActive ? 0.04 : 0.015) * pulseIntensity;
    }

    if (orbitRingRef.current) {
      orbitRingRef.current.rotation.z += 0.003;
      orbitRingRef.current.rotation.x += 0.001;
    }
  });

  return (
    <group ref={groupRef} position={[baseX, baseY, baseZ]}>
      {/* Corona / outer glow */}
      <mesh ref={coronaRef}>
        <sphereGeometry args={[nodeSize * (isHub ? 1.7 : 2), detailed ? 32 : 10, detailed ? 32 : 10]} />
        <meshBasicMaterial
          color={nodeColor}
          transparent
          opacity={isHub ? 0.15 : 0.08}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </mesh>

      {/* Main body */}
      <mesh
        onClick={(e) => { e.stopPropagation(); onClick(node); }}
        onPointerEnter={() => setHovered(true)}
        onPointerLeave={() => setHovered(false)}
      >
        <sphereGeometry args={[nodeSize, detailed ? 48 : 12, detailed ? 48 : 12]} />
        <meshStandardMaterial
          color={dimmed ? '#3b424d' : nodeColor}
          emissive={dimmed ? '#000000' : getNodeEmissive(node.group)}
          emissiveIntensity={hovered ? 1.4 : dimmed ? 0.05 : isHub ? 0.9 : 0.5}
          metalness={0.4}
          roughness={0.15}
          transparent
          opacity={dimmed ? 0.4 : 1}
        />
      </mesh>

      {/* Hover halo */}
      {hovered && (
        <mesh>
          <sphereGeometry args={[nodeSize * 1.8, 24, 24]} />
          <meshBasicMaterial
            color={nodeColor}
            transparent
            opacity={0.2}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
          />
        </mesh>
      )}

      {/* Orbital ring for active nodes; faint ring for idle oracles so they stay visible.
          Primary hub uses scene-level GravityWell; secondary hubs get HubOrbitBelts. */}
      {(isActive || isOracle) && !isHub && (
        <mesh ref={orbitRingRef} rotation={[Math.PI / 3, 0, 0]}>
          <torusGeometry args={[nodeSize * 1.6, 0.015, 8, 24]} />
          <meshBasicMaterial color={nodeColor} transparent opacity={isActive ? 0.5 : 0.18} depthWrite={false} />
        </mesh>
      )}
      {isHub && !isPrimaryHub && detailed && (
        <HubOrbitBelts color={nodeColor} radius={nodeSize} />
      )}

      {/* Label */}
      {(showLabel || hovered) && (
      <Html
        position={[0, -nodeSize - 0.35, 0]}
        center
        distanceFactor={14}
        occlude={false}
        style={{ pointerEvents: 'none' }}
      >
        <div
          className="text-[9px] font-mono whitespace-nowrap transition-opacity duration-200"
          style={{
            color: dimmed ? '#6b7280' : nodeColor,
            textShadow: dimmed ? 'none' : `0 0 8px ${nodeColor}, 0 0 2px ${nodeColor}`,
            opacity: hovered ? 1 : dimmed ? 0.38 : 0.55,
            letterSpacing: '0.05em',
          }}
        >
          {shortLabel(node.label)}
        </div>
      </Html>
      )}

      {/* Status dot */}
      <mesh position={[nodeSize + 0.08, nodeSize + 0.05, 0]}>
        <sphereGeometry args={[0.05, 8, 8]} />
        <meshBasicMaterial
          color={
            node.status === 'active' ? '#00ff88' :
            node.status === 'error' ? '#ff3355' :
            node.status === 'idle' ? '#ffdd00' : '#555'
          }
          transparent
          opacity={0.9}
          blending={THREE.AdditiveBlending}
        />
      </mesh>
    </group>
  );
}

// ---------------------------------------------------------------------------
// Constellation lines — glowing, animated bezier connections
// ---------------------------------------------------------------------------
function ConstellationLines({
  links,
  nodePositions,
  themeColor,
}: {
  links: EcoLink[];
  nodePositions: Map<string, THREE.Vector3>;
  themeColor: string;
}) {
  // ONE geometry for every edge, not one `<Line>` mesh per edge.
  //
  // drei's `<Line>` is a Line2 — its own geometry, its own shader material, its own
  // resolution uniform. Five thousand edges is five thousand of those, and it outweighed
  // every node on the map put together. A federation is mostly edges, so this is the piece
  // that has to be batched before any of the others matter.
  const SEGMENTS = 8;
  const vertices = useMemo(() => {
    const usable: [THREE.Vector3, THREE.Vector3][] = [];
    for (const link of links) {
      const srcId = typeof link.source === 'string' ? link.source : '';
      const tgtId = typeof link.target === 'string' ? link.target : '';
      const src = nodePositions.get(srcId);
      const tgt = nodePositions.get(tgtId);
      if (src && tgt) usable.push([src, tgt]);
    }
    // Two vertices per drawn segment: lineSegments takes disjoint pairs.
    const array = new Float32Array(usable.length * SEGMENTS * 2 * 3);
    const mid = new THREE.Vector3();
    const a = new THREE.Vector3();
    const b = new THREE.Vector3();
    let at = 0;
    for (const [src, tgt] of usable) {
      mid.addVectors(src, tgt).multiplyScalar(0.5);
      mid.y += 0.3;
      const curve = new THREE.QuadraticBezierCurve3(src, mid.clone(), tgt);
      curve.getPoint(0, a);
      for (let i = 1; i <= SEGMENTS; i += 1) {
        curve.getPoint(i / SEGMENTS, b);
        array[at++] = a.x; array[at++] = a.y; array[at++] = a.z;
        array[at++] = b.x; array[at++] = b.y; array[at++] = b.z;
        a.copy(b);
      }
    }
    return array;
  }, [links, nodePositions]);

  const count = vertices.length / 3;
  if (!count) return null;

  return (
    <lineSegments key={count}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" array={vertices} count={count} itemSize={3} />
      </bufferGeometry>
      <lineBasicMaterial color={themeColor} transparent opacity={0.08} depthWrite={false} />
    </lineSegments>
  );
}

// ---------------------------------------------------------------------------
// Star cluster — many small bodies (factory catalog / templates)
// ---------------------------------------------------------------------------
function StarCluster({
  node,
  onClick,
}: {
  node: EcoNode;
  onClick: (n: EcoNode) => void;
}) {
  const groupRef = useRef<THREE.Group>(null!);
  const count = Math.min(Math.max(Number(node.metrics?.count) || 12, 8), 48);
  const clusterColor = getNodeColor('cluster');
  const base = useMemo(
    () => new THREE.Vector3(node.position.x, node.position.y, node.position.z),
    [node.position.x, node.position.y, node.position.z],
  );

  const stars = useMemo(() => {
    const out: { offset: THREE.Vector3; size: number; phase: number }[] = [];
    for (let i = 0; i < count; i++) {
      const u = (i + 0.5) / count;
      const phi = Math.acos(1 - 2 * u);
      const theta = i * GOLDEN_ANGLE_LOCAL;
      const r = 0.35 + (i % 5) * 0.08;
      out.push({
        offset: new THREE.Vector3(
          r * Math.sin(phi) * Math.cos(theta),
          r * Math.sin(phi) * Math.sin(theta) * 0.6,
          r * Math.cos(phi),
        ),
        size: 0.04 + (i % 3) * 0.015,
        phase: Math.random() * Math.PI * 2,
      });
    }
    return out;
  }, [count]);

  useFrame(({ clock }) => {
    if (!groupRef.current) return;
    groupRef.current.position.copy(base);
    const t = clock.getElapsedTime();
    groupRef.current.children.forEach((child, i) => {
      if (!(child instanceof THREE.Mesh)) return;
      const s = stars[i];
      if (!s) return;
      const tw = 1 + Math.sin(t * 2 + s.phase) * 0.15;
      child.position.copy(s.offset).multiplyScalar(tw);
    });
  });

  return (
    <group ref={groupRef} position={[base.x, base.y, base.z]}>
      <mesh
        onClick={(e) => {
          e.stopPropagation();
          onClick(node);
        }}
      >
        <sphereGeometry args={[0.55, 24, 24]} />
        <meshBasicMaterial
          color={clusterColor}
          transparent
          opacity={0.12}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </mesh>
      {stars.map((s, i) => (
        <mesh
          key={i}
          position={s.offset}
          onClick={(e) => {
            e.stopPropagation();
            onClick(node);
          }}
        >
          <sphereGeometry args={[s.size, 8, 8]} />
          <meshStandardMaterial
            color={clusterColor}
            emissive={clusterColor}
            emissiveIntensity={1.2}
            roughness={0.35}
            metalness={0.1}
          />
        </mesh>
      ))}
      <Html distanceFactor={14} position={[0, 0.9, 0]} center>
        <div
          className="text-[9px] font-mono px-1.5 py-0.5 rounded pointer-events-none whitespace-nowrap"
          style={{
            color: clusterColor,
            background: 'rgba(0,0,0,0.55)',
            border: `1px solid ${clusterColor}44`,
          }}
        >
          {shortLabel(node.label)}
        </div>
      </Html>
    </group>
  );
}

const GOLDEN_ANGLE_LOCAL = 2.399963229728653282;

function focusDistanceForNode(nodeId: string, group: string): number {
  if (nodeId === 'hub') return 14;
  if (nodeId === 'factory' || nodeId === 'competing_hub' || nodeId === 'signal_hunt_hub' || group === 'peer_hub') return 11;
  if (group === 'cluster') return 7;
  if (group === 'core') return 10;
  if (group === 'contract') return 8;
  return 6.5;
}

// ---------------------------------------------------------------------------
// Camera — fly to selection and keep OrbitControls target locked
// ---------------------------------------------------------------------------
function CameraRig({
  focusNodeId,
  nodePositions,
  nodeGroups,
}: {
  focusNodeId: string | null;
  nodePositions: Map<string, THREE.Vector3>;
  nodeGroups: Map<string, string>;
}) {
  const { camera } = useThree();
  const controls = useThree((s) => s.controls as OrbitControlsImpl | null);
  const animRef = useRef({
    active: false,
    start: 0,
    from: new THREE.Vector3(),
    to: new THREE.Vector3(),
    lookFrom: new THREE.Vector3(),
    lookTo: new THREE.Vector3(),
  });
  const lastFocusId = useRef<string | null>(null);

  useEffect(() => {
    if (!focusNodeId) {
      lastFocusId.current = null;
      return;
    }
    const target = nodePositions.get(focusNodeId);
    if (!target || lastFocusId.current === focusNodeId) return;
    lastFocusId.current = focusNodeId;

    const group = nodeGroups.get(focusNodeId) ?? 'core';
    const dist = focusDistanceForNode(focusNodeId, group);
    const dir = camera.position.clone().sub(target);
    if (dir.lengthSq() < 0.01) {
      dir.set(0.35, 0.22, 1).normalize();
    } else {
      dir.normalize();
    }
    const to = target.clone().add(dir.multiplyScalar(dist));
    const lookFrom = new THREE.Vector3();
    camera.getWorldDirection(lookFrom).normalize().multiplyScalar(10).add(camera.position);

    animRef.current = {
      active: true,
      start: performance.now(),
      from: camera.position.clone(),
      to,
      lookFrom,
      lookTo: target.clone(),
    };
  }, [focusNodeId, camera, nodePositions, nodeGroups]);

  useFrame(() => {
    const anim = animRef.current;
    if (anim.active) {
      const elapsed = (performance.now() - anim.start) / 1000;
      const duration = 1.4;
      const t = Math.min(elapsed / duration, 1);
      const e = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
      camera.position.lerpVectors(anim.from, anim.to, e);
      const lookX = anim.lookFrom.x + (anim.lookTo.x - anim.lookFrom.x) * e;
      const lookY = anim.lookFrom.y + (anim.lookTo.y - anim.lookFrom.y) * e;
      const lookZ = anim.lookFrom.z + (anim.lookTo.z - anim.lookFrom.z) * e;
      camera.lookAt(lookX, lookY, lookZ);
      if (controls) {
        controls.target.set(lookX, lookY, lookZ);
      }
      if (t >= 1) {
        anim.active = false;
      }
      return;
    }

    if (!focusNodeId || !controls) return;
    const target = nodePositions.get(focusNodeId);
    if (!target) return;
    controls.target.lerp(target, 0.14);
    controls.update();
  });

  return null;
}

/**
 * A round mask for the star field.
 *
 * Built once in a canvas rather than shipped as a file: it is sixteen pixels of radial
 * falloff, and an asset would be one more thing to serve and to get wrong behind a base
 * path. Without it every star is a square, which is exactly what appeared on the map.
 */
const starSprite = (() => {
  if (typeof document === 'undefined') return null;
  const size = 32;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  const grd = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  grd.addColorStop(0, 'rgba(255,255,255,1)');
  grd.addColorStop(0.55, 'rgba(255,255,255,0.85)');
  grd.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = grd;
  ctx.fillRect(0, 0, size, size);
  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
})();

/**
 * Everything on the map, as one draw call.
 *
 * A node built as a real object is a `<group>` with several meshes, materials and a frame
 * callback; five thousand of those measured 2 fps and a 65-second load, and the cost is
 * linear, so a hundred thousand is not slower, it is a page that never finishes. This is
 * the whole graph as a single `<points>` — a hundred thousand positions is 1.2 MB in one
 * buffer and one draw call — and the nodes near the camera get their real bodies drawn on
 * top of it. A hub the camera is far from is a star; fly to it and it becomes a world.
 *
 * It stays clickable: three raycasts Points, so a distant hub can still be selected, which
 * focuses the camera on it and pulls its neighbourhood in.
 */
function FarFieldNodes({
  chart,
  onPick,
}: {
  chart: StarChart;
  onPick: (id: string) => void;
}) {
  const { positions, colors, ids } = chart;
  const count = ids.length;
  const pointsRef = useRef<THREE.Points>(null!);

  // A star a hundred units out is a sub-pixel dot, and three raycasts Points against a
  // FIXED world-space threshold — one unit by default. At the far field that is far below
  // a pixel, so the cloud was unclickable, which is the one interaction it has to support:
  // travelling to a hub you can see but have not loaded. Scale the threshold with how far
  // the camera is, and scope it to this object so the dust and nebulae stay inert.
  useEffect(() => {
    const obj = pointsRef.current;
    if (!obj) return;
    const base = THREE.Points.prototype.raycast;
    obj.raycast = function farFieldRaycast(raycaster, intersects) {
      const params = raycaster.params.Points || {};
      const previous = params.threshold;
      const viewDistance = raycaster.ray.origin.length() || 1;
      raycaster.params.Points = { ...params, threshold: Math.max(0.6, viewDistance * 0.012) };
      base.call(this, raycaster, intersects);
      raycaster.params.Points = { ...raycaster.params.Points, threshold: previous };
    };
  }, []);

  if (!count) return null;

  return (
    <points
      ref={pointsRef}
      onClick={(e) => {
        e.stopPropagation();
        const hit = ids[e.index ?? -1];
        if (hit) onPick(hit);
      }}
    >
      <bufferGeometry key={`${chart.epoch}:${count}`}>
        <bufferAttribute attach="attributes-position" array={positions} count={count} itemSize={3} />
        <bufferAttribute attach="attributes-color" array={colors} count={count} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial
        // A star, not a tile. three draws a Point as a square quad unless something masks
        // it, and `sizeAttenuation` grows that quad as the camera closes — so every node,
        // which also has its own star in the chart, wore a bright cyan SQUARE across its
        // sphere at close range. The map is drawn from a chart of stars: a fixed pixel size
        // is what a star chart wants anyway, and it means a star can never swell into a
        // blob over the body sitting on the same coordinate.
        size={2.6}
        sizeAttenuation={false}
        map={starSprite}
        alphaTest={0.25}
        vertexColors
        transparent
        opacity={0.9}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

/**
 * The suns worth lighting right now.
 *
 * Sampled from the camera twice a second rather than every frame: the set only changes
 * when the camera travels, and re-deriving it per frame would cost more than the lights
 * it saves. Lit ids are the state, so a hub that is already lit keeps its live node object
 * as the graph ticks instead of freezing at whatever it looked like when it entered the set.
 */
function useNearestIds(
  items: EcoNode[],
  budget: number,
  pick: (n: EcoNode[], c: THREE.Vector3, b: number) => EcoNode[] = nearestHubs,
): Set<string> {
  const { camera } = useThree();
  const [ids, setIds] = useState<string[]>([]);
  const sinceSample = useRef(0);

  const sample = () => {
    const next = pick(items, camera.position, budget).map((n) => n.id);
    setIds((prev) =>
      prev.length === next.length && prev.every((id, i) => id === next[i]) ? prev : next,
    );
  };

  // Something that just appeared should not wait half a second in the dark.
  useEffect(sample, [items, camera, budget]);

  useFrame((_state, delta) => {
    sinceSample.current += delta;
    if (sinceSample.current < 0.5) return;
    sinceSample.current = 0;
    sample();
  });

  return useMemo(() => new Set(ids), [ids]);
}

/**
 * Report where the camera is, on the same half-second sample as everything else.
 *
 * This is what decides which window the client asks the server for, so it has to be a
 * sample and not a frame callback: a request per frame turns a scaling fix into a different
 * load problem. `windowIsStale` upstream decides whether a sample is worth acting on.
 */
function useCameraReport(
  report?: (center: { x: number; y: number; z: number }, radius: number) => void,
): null {
  const { camera } = useThree();
  const controls = useThree((s) => s.controls as OrbitControlsImpl | null);
  const since = useRef(0);
  useFrame((_state, delta) => {
    if (!report) return;
    since.current += delta;
    if (since.current < 0.5) return;
    since.current = 0;
    // The target is what the reader is looking AT; the distance to it is how much of the
    // map is on screen, which is exactly the radius worth loading.
    const target = controls?.target;
    const centre = target ?? camera.position;
    const radius = target ? camera.position.distanceTo(target) : 40;
    report({ x: centre.x, y: centre.y, z: centre.z }, Math.max(8, radius));
  });
  return null;
}

// ---------------------------------------------------------------------------
// Scene content
// ---------------------------------------------------------------------------
function SceneContent({
  state,
  onNodeClick,
  themeColor,
  pulseIntensity,
  focusNodeId,
  fundingEvents,
  scenario,
  brightScene = false,
  chart = null,
  onPickUnloaded,
  onCameraMove,
}: {
  state: EcosystemState | null;
  onNodeClick: (n: EcoNode) => void;
  themeColor: string;
  pulseIntensity: number;
  focusNodeId: string | null;
  fundingEvents?: Array<{ id: string; amount: number; token: string; source: string; ts: string }> | null;
  scenario?: { phase: string; phase_progress: number; phase_color: string; tick_count: number; funding_total: number; hub_count: number; buyer_rounds: number } | null;
  /** Brighter lights when Bloom/post-FX is off (safe GPU path). */
  brightScene?: boolean;
  /** Server star chart, when the map is too big to ship whole. */
  chart?: StarChart | null;
  /** A star the client has no node for yet — ask the server for its window. */
  onPickUnloaded?: (id: string) => void;
  /** Where the camera is, sampled — what decides which window to fetch. */
  onCameraMove?: (center: { x: number; y: number; z: number }, radius: number) => void;
}) {
  const nodePositions = useMemo(() => {
    const map = new Map<string, THREE.Vector3>();
    if (state) {
      for (const node of state.nodes) {
        map.set(node.id, new THREE.Vector3(node.position.x, node.position.y, node.position.z));
      }
    }
    return map;
  }, [state]);

  const nodeGroups = useMemo(() => {
    const map = new Map<string, string>();
    if (state) {
      for (const node of state.nodes) {
        map.set(node.id, node.group);
      }
    }
    return map;
  }, [state]);

  const allLinks = state?.links ?? [];
  const hubPos = new THREE.Vector3(0, 0, 0);
  const secondaryHubs = useMemo(
    () => (state?.nodes ?? []).filter((n) => n.id !== 'hub' && isHubRole(n)),
    [state?.nodes],
  );
  // Detail is a budget, not a property of the node. Every sun used to get its own
  // `pointLight`, and three recompiles its shaders per light count and pays for each light
  // on every fragment — a federation of a hundred hubs would render at a slideshow, a
  // thousand not at all. Only the ones the camera is actually near are lit.
  const litHubIds = useNearestIds(secondaryHubs, LIT_HUB_BUDGET);
  const litHubs = useMemo(
    () => secondaryHubs.filter((h) => litHubIds.has(h.id)),
    [secondaryHubs, litHubIds],
  );
  const maxCameraDistance = useMemo(() => cameraRange(state?.nodes ?? []), [state?.nodes]);

  // A hub's constellation belongs to that hub, and appears when the hub does: selected, or
  // near enough to have earned a light. Five thousand nodes at once is 1 fps — measured —
  // and unreadable long before that.
  const openHubIds = useMemo(() => {
    const open = new Set(litHubIds);
    if (focusNodeId) open.add(focusNodeId);
    return open;
  }, [litHubIds, focusNodeId]);
  const drawnNodes = useMemo(
    () => visibleNodes(sanitizeEcoGraphNodes(state?.nodes ?? []), openHubIds),
    [state?.nodes, openHubIds],
  );
  // The star field: the server's chart when the map is too big to ship, otherwise derived
  // from the nodes we already have. Either way the cloud is one draw call.
  const farField = useMemo(
    () => chart ?? chartFromNodes(drawnNodes),
    [chart, drawnNodes],
  );
  const onFarFieldPick = useCallback(
    (id: string) => {
      const known = (state?.nodes ?? []).find((n) => n.id === id);
      if (known) onNodeClick(known);
      else onPickUnloaded?.(id);
    },
    [state?.nodes, onNodeClick, onPickUnloaded],
  );

  // Real bodies go to the nodes the camera is near; the rest are stars in the cloud below.
  const realIds = useNearestIds(drawnNodes, REAL_NODE_BUDGET);
  const realNodes = useMemo(
    () => (drawnNodes.length <= REAL_NODE_BUDGET
      ? drawnNodes
      : drawnNodes.filter((n) => realIds.has(n.id) || isFederation(n))),
    [drawnNodes, realIds],
  );
  // One `<Html>` label is a real DOM node that drei repositions every frame; they are the
  // most expensive thing on the page well before the meshes are.
  // Labels go by what a node is, then by distance — see labelTargets. Lights stay purely
  // nearest-first, because a light is a cost paid for what the camera can actually see.
  const labelledIds = useNearestIds(realNodes, LABEL_BUDGET, labelTargets);
  useCameraReport(onCameraMove);

  // Edges follow the same rule as the bodies they connect, and BOTH ends have to qualify.
  //
  // "Federation peer" is the same fact about every hub, so at a thousand of them it is a
  // thousand lines converging on one point — a starburst that hides everything behind it
  // and says nothing, because on that map being a peer is not news. Requiring both ends to
  // be near keeps the edges that describe local structure (a hub and its planets, a hub
  // and the neighbour it shares) and drops the ones whose other end is off in the dark.
  const activeLinks = useMemo(() => {
    if (realNodes.length === drawnNodes.length) return allLinks;
    const near = new Set(realNodes.map((n) => n.id));
    return allLinks.filter((l) => {
      const src = typeof l.source === 'string' ? l.source : '';
      const tgt = typeof l.target === 'string' ? l.target : '';
      return near.has(src) && near.has(tgt);
    });
  }, [allLinks, realNodes, drawnNodes.length]);

  // Nebula cluster centers
  const nebulaCenters = useMemo(() => [
    { center: new THREE.Vector3(0, 0, 0), color: '#00f0ff', radius: 2.5 },        // core
    { center: new THREE.Vector3(6, 1, 0), color: '#ff00ff', radius: 2.0 },         // contracts
    { center: new THREE.Vector3(-4, 2, -3), color: '#00ff88', radius: 2.0 },       // clients
    { center: new THREE.Vector3(0, -4, -2), color: '#7b2fff', radius: 2.0 },       // plugins
    // Competing lab galaxy — far SE/back (matches COMPETING_GALAXY_ANCHOR)
    { center: new THREE.Vector3(30, 12, -20), color: '#ff8c42', radius: 3.5 },
  ], []);

  // Wormhole connections (only major ones)
  const wormholeLinks = useMemo(() => {
    const major = activeLinks.filter((_, i) => i < 12);
    return major.map(link => {
      const srcId = typeof link.source === 'string' ? link.source : '';
      const tgtId = typeof link.target === 'string' ? link.target : '';
      return {
        src: nodePositions.get(srcId) ?? hubPos,
        tgt: nodePositions.get(tgtId) ?? hubPos,
      };
    }).filter(w => w.src && w.tgt);
  }, [activeLinks, nodePositions]);

  return (
    <>
      <CameraRig
        focusNodeId={focusNodeId}
        nodePositions={nodePositions}
        nodeGroups={nodeGroups}
      />

      {/* Lighting — boosted when post-FX disabled (otherwise scene looks like a black void) */}
      <ambientLight intensity={brightScene ? 0.5 : 0.15} />
      <pointLight position={[0, 0, 0]} intensity={brightScene ? 4 : 2.5} color={themeColor} distance={24} />
      <pointLight position={[8, 5, 5]} intensity={brightScene ? 1.2 : 0.4} color="#ff00ff" distance={18} />
      <pointLight position={[-8, -3, -5]} intensity={brightScene ? 0.9 : 0.3} color="#3366ff" distance={18} />
      {litHubs.map((h) => (
        <pointLight
          key={`light-${h.id}`}
          position={[h.position.x, h.position.y, h.position.z]}
          intensity={brightScene ? 2.2 : 1.4}
          color={h.color || '#ff8c42'}
          distance={16}
        />
      ))}

      {/* Deep space starfield */}
      <Stars radius={50} depth={50} count={3000} factor={2.5} saturation={0} fade speed={0.3} />

      {/* Cosmic dust */}
      <CosmicDust color={themeColor} count={400} />

      {/* Nebula clouds around clusters */}
      {nebulaCenters.map((nc, i) => (
        <NebulaCloud key={i} center={nc.center} color={nc.color} radius={nc.radius} />
      ))}

      {/* Asteroid belts at different radii */}
      <AsteroidBelt radius={7} color={themeColor} count={500} tilt={0.3} />
      <AsteroidBelt radius={10} color="#ff00ff" count={350} tilt={-0.4} />
      <AsteroidBelt radius={12} color="#7b2fff" count={300} tilt={0.15} />

      {/* Solar corona around hub */}
      <SolarCorona color={themeColor} intensity={pulseIntensity} />

      {/* Gravity well rings */}
      <GravityWell color={themeColor} intensity={pulseIntensity} />

      {/* Secondary hubs — smaller sun + orbit well at each galaxy / peer hub */}
      {litHubs.map((h) => {
        const trust = nodeTrust01(h);
        const scale = 0.5 + 0.35 * (trust ?? 0.45);
        const color = h.color || getNodeColor(h.group);
        return (
          <group key={`hub-fx-${h.id}`} position={[h.position.x, h.position.y, h.position.z]}>
            <SolarCorona color={color} intensity={pulseIntensity * 0.85} scale={scale} />
            <GravityWell color={color} intensity={pulseIntensity * 0.75} scale={scale} />
          </group>
        );
      })}

      {/* Constellation connections */}
      <ConstellationLines links={activeLinks} nodePositions={nodePositions} themeColor={themeColor} />

      {/* Wormhole tunnels */}
      {wormholeLinks.map((wl, i) => (
        <WormholeTunnel
          key={i}
          src={wl.src}
          tgt={wl.tgt}
          color={themeColor}
          intensity={pulseIntensity}
        />
      ))}

      {/* External funding stream */}
      <FundingStream
        hubPosition={hubPos}
        active={(fundingEvents?.length ?? 0) > 0}
        intensity={pulseIntensity}
      />

      {/* Phase ring around hub */}
      {scenario && (
        <PhaseRing
          phaseColor={scenario.phase_color}
          progress={scenario.phase_progress}
          active={true}
        />
      )}

      {/* Every node, as one draw call — the far field of the map. */}
      <FarFieldNodes chart={farField} onPick={onFarFieldPick} />

      {/* Ecosystem nodes the camera is near, built for real on top of it */}
      {realNodes.map((node) =>
        node.group === 'cluster' ? (
          <StarCluster key={node.id} node={node} onClick={onNodeClick} />
        ) : (
          <EcoNodeMesh
            key={node.id}
            node={node}
            onClick={onNodeClick}
            themeColor={themeColor}
            pulseIntensity={pulseIntensity}
            showLabel={labelledIds.has(node.id)}
          />
        ),
      )}

      {/* Outer orbital ring */}
      <mesh rotation={[Math.PI / 2.2, 0.2, 0]}>
        <torusGeometry args={[8.5, 0.02, 8, 160]} />
        <meshBasicMaterial color={themeColor} transparent opacity={0.06} depthWrite={false} />
      </mesh>
      <mesh rotation={[Math.PI / 2.5, -0.3, 0.1]}>
        <torusGeometry args={[9.5, 0.015, 8, 140]} />
        <meshBasicMaterial color="#ff00ff" transparent opacity={0.04} depthWrite={false} />
      </mesh>

      <OrbitControls
        makeDefault
        enableDamping
        enablePan
        dampingFactor={0.06}
        minDistance={3}
        // A fixed 52 was fine for one ecosystem and is a wall for a federation: a hundred
        // hubs reach radius 54, a thousand reach 126, and neither can be framed by a camera
        // that stops at 52. The limit follows the map.
        maxDistance={maxCameraDistance}
        maxPolarAngle={Math.PI * 0.78}
        touches={{ ONE: 2, TWO: 2 }}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// Funding Stream — cosmic particles flowing from outside toward hub
// ---------------------------------------------------------------------------
function FundingStream({
  hubPosition,
  active,
  intensity,
}: {
  hubPosition: THREE.Vector3;
  active: boolean;
  intensity: number;
}) {
  const pointsRef = useRef<THREE.Points>(null!);
  const particleCount = 80;

  const { positions, origins } = useMemo(() => {
    const pos = new Float32Array(particleCount * 3);
    const org = new Float32Array(particleCount * 3);
    for (let i = 0; i < particleCount; i++) {
      // Particles originate from outside the scene
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.random() * Math.PI * 0.6 + 0.2;
      const dist = 15 + Math.random() * 10;
      org[i * 3] = Math.cos(theta) * Math.cos(phi) * dist;
      org[i * 3 + 1] = Math.sin(phi) * dist * 0.7;
      org[i * 3 + 2] = Math.sin(theta) * Math.cos(phi) * dist;
      pos[i * 3] = org[i * 3];
      pos[i * 3 + 1] = org[i * 3 + 1];
      pos[i * 3 + 2] = org[i * 3 + 2];
    }
    return { positions: pos, origins: org };
  }, [particleCount]);

  useFrame(({ clock }) => {
    if (!pointsRef.current || !active) return;
    const t = clock.getElapsedTime();
    const posArr = pointsRef.current.geometry.attributes.position.array as Float32Array;

    for (let i = 0; i < particleCount; i++) {
      const progress = ((t * 0.15 + i * 0.012) % 1);
      const ease = progress < 0.5
        ? 2 * progress * progress
        : -1 + (4 - 2 * progress) * progress;

      posArr[i * 3] = origins[i * 3] + (hubPosition.x - origins[i * 3]) * ease;
      posArr[i * 3 + 1] = origins[i * 3 + 1] + (hubPosition.y - origins[i * 3 + 1]) * ease;
      posArr[i * 3 + 2] = origins[i * 3 + 2] + (hubPosition.z - origins[i * 3 + 2]) * ease;
    }
    pointsRef.current.geometry.attributes.position.needsUpdate = true;

    const mat = pointsRef.current.material as THREE.PointsMaterial;
    mat.opacity = active ? 0.25 * intensity : 0;
  });

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" array={positions} count={particleCount} itemSize={3} />
      </bufferGeometry>
      <pointsMaterial
        size={0.08}
        color="#ffdd00"
        transparent
        opacity={0}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

// ---------------------------------------------------------------------------
// Phase Ring — rotating ring showing evolution phase progress
// ---------------------------------------------------------------------------
function PhaseRing({
  phaseColor,
  progress,
  active,
}: {
  phaseColor: string;
  progress: number;
  active: boolean;
}) {
  const ringRef = useRef<THREE.Mesh>(null!);

  useFrame((_, delta) => {
    if (ringRef.current) {
      ringRef.current.rotation.z += delta * (0.3 + progress * 0.6);
      ringRef.current.rotation.x += delta * 0.1;
    }
  });

  if (!active) return null;

  const ringRadius = 1.5 + progress * 0.5;

  return (
    <group>
      {/* Phase progress ring */}
      <mesh ref={ringRef} rotation={[Math.PI / 2.5, 0, 0]}>
        <torusGeometry args={[ringRadius, 0.03, 16, 100, progress * Math.PI * 2]} />
        <meshBasicMaterial
          color={phaseColor}
          transparent
          opacity={0.6}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </mesh>
      {/* Full ring ghost */}
      <mesh rotation={[Math.PI / 2.5, 0, 0]}>
        <torusGeometry args={[ringRadius, 0.015, 8, 100]} />
        <meshBasicMaterial
          color={phaseColor}
          transparent
          opacity={0.1}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </mesh>
    </group>
  );
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------
interface Props {
  state: EcosystemState | null;
  onNodeClick: (node: EcoNode) => void;
  focusNodeId?: string | null;
  themeColor: string;
  pulseIntensity: number;
  fundingEvents?: Array<{
    id: string;
    amount: number;
    token: string;
    source: string;
    ts: string;
  }> | null;
  scenario?: {
    phase: string;
    phase_progress: number;
    phase_color: string;
    tick_count: number;
    funding_total: number;
    hub_count: number;
    buyer_rounds: number;
  } | null;
  /** Server star chart, when the map is too big to ship whole (see lib/mapWindow). */
  chart?: StarChart | null;
  /** A star with no node behind it yet — the caller fetches its window. */
  onPickUnloaded?: (id: string) => void;
  /** Sampled camera target + view radius; decides which window to load. */
  onCameraMove?: (center: { x: number; y: number; z: number }, radius: number) => void;
}

function useCosmicPostFx(): boolean {
  const isMobile = useIsMobile();
  return useMemo(() => {
    if (isMobile) return false;
    if (typeof window === 'undefined') return true;
    const params = new URLSearchParams(window.location.search);
    if (params.get('safe') === '1' || params.get('fx') === '0') return false;
    if (import.meta.env.VITE_DISABLE_POSTFX === '1') return false;
    return true;
  }, [isMobile]);
}

/** If Bloom/post-FX crashes, keep the 3D scene — drop only the composer pass. */
class PostFxBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  render() {
    if (this.state.failed) return null;
    return this.props.children;
  }
}

export default function EcosystemGraph({
  state,
  onNodeClick,
  focusNodeId = null,
  themeColor,
  pulseIntensity,
  fundingEvents,
  scenario,
  chart = null,
  onPickUnloaded,
  onCameraMove,
}: Props) {
  const isMobile = useIsMobile();
  const enablePostFx = useCosmicPostFx();

  return (
    <div className="absolute inset-0 touch-none">
      <Canvas
        frameloop="always"
        gl={{
          // MSAA off above ~1.5 device pixels: at that density it buys very little and costs a
          // full multisample resolve every frame.
          antialias: typeof window === 'undefined' || window.devicePixelRatio < 1.75,
          alpha: false,
          // preserveDrawingBuffer was true and NOTHING read this canvas — the only pixel
          // reader in the app, `useWebGLCanvasReady`, has no callers. The flag is not free:
          // it forbids Chrome's compositor fast path, so every frame pays extra copies of a
          // full-screen buffer. Firefox is barely affected, which is exactly the reported
          // shape of the problem ("fast in Firefox, crawls in Chrome"). If a screenshot
          // feature ever needs it, turn it on for that render only.
          preserveDrawingBuffer: false,
          powerPreference: 'high-performance',
          failIfMajorPerformanceCaveat: false,
          toneMapping: THREE.ACESFilmicToneMapping,
          toneMappingExposure: 1.35,
          outputColorSpace: THREE.SRGBColorSpace,
        }}
        camera={{ position: [0, 4, 16], fov: isMobile ? 58 : 52, near: 0.1, far: 120 }}
        // 1.5 rather than 2 on desktop: a Retina screen at dpr 2 renders 2880x1800 for a
        // 1440x900 window — four times the pixels of dpr 1, for a difference almost nobody can
        // see on a dark starfield, and it is paid on every single frame.
        dpr={isMobile ? [1, 1.25] : [1, 1.5]}
      >
        <SceneContent
          state={state}
          onNodeClick={onNodeClick}
          themeColor={themeColor}
          pulseIntensity={pulseIntensity}
          focusNodeId={focusNodeId}
          fundingEvents={fundingEvents}
          scenario={scenario}
          brightScene={!enablePostFx}
          chart={chart}
          onPickUnloaded={onPickUnloaded}
          onCameraMove={onCameraMove}
        />

        {enablePostFx && (
          <PostFxBoundary>
            <EffectComposer multisampling={0} enableNormalPass={false}>
              <Bloom
                luminanceThreshold={0.15}
                luminanceSmoothing={0.9}
                intensity={0.85}
                radius={0.55}
                mipmapBlur
              />
              <Vignette darkness={0.45} offset={0.12} />
              <Noise opacity={0.012} />
            </EffectComposer>
          </PostFxBoundary>
        )}
      </Canvas>

      {/* Radial vignette overlay for depth */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: enablePostFx
            ? 'radial-gradient(ellipse at center, transparent 35%, rgba(5,5,12,0.7) 100%)'
            : 'radial-gradient(ellipse at center, transparent 55%, rgba(5,5,12,0.45) 100%)',
        }}
      />
    </div>
  );
}
