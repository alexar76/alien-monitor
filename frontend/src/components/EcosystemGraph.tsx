import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import {
  OrbitControls,
  Sphere,
  Line,
  Html,
  Stars,
} from '@react-three/drei';
import { EffectComposer, Bloom, Vignette, Noise } from '@react-three/postprocessing';
import * as THREE from 'three';
import type { EcoNode, EcoLink, EcosystemState } from '../App';

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
};

const GROUP_EMISSIVE: Record<string, string> = {
  core: '#004466',
  contract: '#440044',
  client: '#004422',
  infra: '#220066',
  sdk: '#443300',
  network: '#001144',
  chain: '#441100',
};

const getNodeColor = (g: string) => GROUP_COLORS[g] || '#00f0ff';
const getNodeEmissive = (g: string) => GROUP_EMISSIVE[g] || '#001122';

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
// Solar Corona — glowing atmosphere around central hub
// ---------------------------------------------------------------------------
function SolarCorona({ color, intensity }: { color: string; intensity: number }) {
  const groupRef = useRef<THREE.Group>(null!);
  const layers = [0.65, 0.75, 0.9, 1.1];

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
// Gravity well — central mass that attracts nodes
// ---------------------------------------------------------------------------
function GravityWell({ color, intensity }: { color: string; intensity: number }) {
  const ringRefs = useRef<THREE.Mesh[]>([]);

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    ringRefs.current.forEach((ring, i) => {
      if (!ring) return;
      const phase = i * 0.5;
      const s = 0.8 + (t * 0.3 + phase) % 4;
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
          <ringGeometry args={[0.5, 0.54, 80]} />
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

// ---------------------------------------------------------------------------
// Main eco node — planet/sun style
// ---------------------------------------------------------------------------
function EcoNodeMesh({
  node,
  onClick,
  themeColor,
  pulseIntensity,
}: {
  node: EcoNode;
  onClick: (n: EcoNode) => void;
  themeColor: string;
  pulseIntensity: number;
}) {
  const groupRef = useRef<THREE.Group>(null!);
  const coronaRef = useRef<THREE.Mesh>(null!);
  const orbitRingRef = useRef<THREE.Mesh>(null!);
  const [hovered, setHovered] = useState(false);

  const nodeColor = getNodeColor(node.group);
  const isActive = node.status === 'active';
  const isHub = node.group === 'core' && node.id === 'hub';
  const nodeSize = isHub ? 0.7 : node.group === 'core' ? 0.45 : node.group === 'contract' ? 0.38 : 0.28;
  const baseY = node.position.y;
  const baseX = node.position.x;
  const baseZ = node.position.z;

  // Wobble parameters per node
  const wobble = useMemo(() => ({
    speed: 0.5 + Math.random() * 1.5,
    ampX: 0.1 + Math.random() * 0.2,
    ampY: 0.1 + Math.random() * 0.2,
    ampZ: 0.1 + Math.random() * 0.2,
    phase: Math.random() * Math.PI * 2,
  }), []);

  useFrame(({ clock }) => {
    if (!groupRef.current) return;
    const t = clock.getElapsedTime();
    const p = wobble.phase;

    groupRef.current.position.x = baseX + Math.sin(t * wobble.speed + p) * wobble.ampX;
    groupRef.current.position.y = baseY + Math.cos(t * wobble.speed * 0.7 + p) * wobble.ampY;
    groupRef.current.position.z = baseZ + Math.sin(t * wobble.speed * 0.6 + p + 1) * wobble.ampZ;

    if (isActive && coronaRef.current) {
      const pulse = 1 + Math.sin(t * 3 + p) * 0.15 * pulseIntensity;
      coronaRef.current.scale.setScalar(pulse);
      (coronaRef.current.material as THREE.MeshBasicMaterial).opacity =
        0.08 + Math.sin(t * 2.5) * 0.04 * pulseIntensity;
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
        <sphereGeometry args={[nodeSize * (isHub ? 2.5 : 2), 32, 32]} />
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
        <sphereGeometry args={[nodeSize, 48, 48]} />
        <meshStandardMaterial
          color={nodeColor}
          emissive={getNodeEmissive(node.group)}
          emissiveIntensity={hovered ? 1.4 : isHub ? 0.9 : 0.5}
          metalness={0.4}
          roughness={0.15}
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

      {/* Orbital ring for active nodes */}
      {isActive && !isHub && (
        <mesh ref={orbitRingRef} rotation={[Math.PI / 3, 0, 0]}>
          <torusGeometry args={[nodeSize * 1.6, 0.015, 8, 24]} />
          <meshBasicMaterial color={nodeColor} transparent opacity={0.5} depthWrite={false} />
        </mesh>
      )}

      {/* Label */}
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
            color: nodeColor,
            textShadow: `0 0 8px ${nodeColor}, 0 0 2px ${nodeColor}`,
            opacity: hovered ? 1 : 0.55,
            letterSpacing: '0.05em',
          }}
        >
          {node.label}
        </div>
      </Html>

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
  const lineData = useMemo(() => {
    const result: { src: THREE.Vector3; tgt: THREE.Vector3 }[] = [];
    for (const link of links) {
      const srcId = typeof link.source === 'string' ? link.source : '';
      const tgtId = typeof link.target === 'string' ? link.target : '';
      const src = nodePositions.get(srcId);
      const tgt = nodePositions.get(tgtId);
      if (src && tgt) result.push({ src, tgt });
    }
    return result;
  }, [links, nodePositions]);

  const points = useMemo(() => {
    return lineData.map((ld) => {
      const mid = new THREE.Vector3().addVectors(ld.src, ld.tgt).multiplyScalar(0.5);
      mid.y += 0.3;
      const curve = new THREE.QuadraticBezierCurve3(ld.src, mid, ld.tgt);
      return curve.getPoints(32);
    });
  }, [lineData]);

  return (
    <group>
      {points.map((pts, i) => (
        <Line
          key={i}
          points={pts}
          color={themeColor}
          lineWidth={0.3}
          transparent
          opacity={0.08}
          depthWrite={false}
        />
      ))}
    </group>
  );
}

// ---------------------------------------------------------------------------
// Scene camera controller with fly-to
// ---------------------------------------------------------------------------
function CameraController({
  flyTarget,
  onFlyComplete,
}: {
  flyTarget: THREE.Vector3 | null;
  onFlyComplete: () => void;
}) {
  const { camera } = useThree();
  const controlsRef = useRef<any>(null);
  const animRef = useRef({ active: false, start: 0, from: new THREE.Vector3(), to: new THREE.Vector3(), lookFrom: new THREE.Vector3(), lookTo: new THREE.Vector3() });

  useEffect(() => {
    if (!flyTarget) return;

    const from = camera.position.clone();
    const lookFrom = new THREE.Vector3();
    camera.getWorldDirection(lookFrom).normalize().multiplyScalar(10).add(from);

    // Fly to a position offset from the target
    const offset = new THREE.Vector3(
      (Math.random() - 0.5) * 4,
      2 + Math.random() * 3,
      3 + Math.random() * 4,
    );
    const to = flyTarget.clone().add(offset);
    const lookTo = flyTarget.clone();

    animRef.current = {
      active: true,
      start: performance.now(),
      from,
      to,
      lookFrom,
      lookTo,
    };
  }, [flyTarget, camera]);

  useFrame(() => {
    const anim = animRef.current;
    if (!anim.active) return;

    const elapsed = (performance.now() - anim.start) / 1000;
    const duration = 1.5;
    const t = Math.min(elapsed / duration, 1.0);
    // Ease in-out
    const e = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;

    camera.position.lerpVectors(anim.from, anim.to, e);
    camera.lookAt(
      anim.lookFrom.x + (anim.lookTo.x - anim.lookFrom.x) * e,
      anim.lookFrom.y + (anim.lookTo.y - anim.lookFrom.y) * e,
      anim.lookFrom.z + (anim.lookTo.z - anim.lookFrom.z) * e,
    );

    if (t >= 1) {
      anim.active = false;
      onFlyComplete();
    }
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
  flyToNodeId,
  onFlyComplete,
}: {
  state: EcosystemState | null;
  onNodeClick: (n: EcoNode) => void;
  themeColor: string;
  pulseIntensity: number;
  flyToNodeId: string | null;
  onFlyComplete: () => void;
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

  const flyTarget = useMemo(() => {
    if (!flyToNodeId) return null;
    return nodePositions.get(flyToNodeId) ?? null;
  }, [flyToNodeId, nodePositions]);

  const activeLinks = state?.links ?? [];
  const hubPos = new THREE.Vector3(0, 0, 0);

  // Nebula cluster centers
  const nebulaCenters = useMemo(() => [
    { center: new THREE.Vector3(0, 0, 0), color: '#00f0ff', radius: 2.5 },        // core
    { center: new THREE.Vector3(6, 1, 0), color: '#ff00ff', radius: 2.0 },         // contracts
    { center: new THREE.Vector3(-4, 2, -3), color: '#00ff88', radius: 2.0 },       // clients
    { center: new THREE.Vector3(0, -4, -2), color: '#7b2fff', radius: 2.0 },       // plugins
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
      <CameraController flyTarget={flyTarget} onFlyComplete={onFlyComplete} />

      {/* Lighting */}
      <ambientLight intensity={0.15} />
      <pointLight position={[0, 0, 0]} intensity={2.5} color={themeColor} distance={20} />
      <pointLight position={[8, 5, 5]} intensity={0.4} color="#ff00ff" distance={15} />
      <pointLight position={[-8, -3, -5]} intensity={0.3} color="#3366ff" distance={15} />

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

      {/* Ecosystem nodes */}
      {state?.nodes.map((node) => (
        <EcoNodeMesh
          key={node.id}
          node={node}
          onClick={onNodeClick}
          themeColor={themeColor}
          pulseIntensity={pulseIntensity}
        />
      ))}

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
        enableDamping
        dampingFactor={0.06}
        minDistance={3}
        maxDistance={35}
        maxPolarAngle={Math.PI * 0.78}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------
interface Props {
  state: EcosystemState | null;
  onNodeClick: (node: EcoNode) => void;
  themeColor: string;
  pulseIntensity: number;
}

export default function EcosystemGraph({ state, onNodeClick, themeColor, pulseIntensity }: Props) {
  const [flyToNodeId, setFlyToNodeId] = useState<string | null>(null);

  const handleNodeClick = useCallback((node: EcoNode) => {
    setFlyToNodeId(node.id);
    onNodeClick(node);
  }, [onNodeClick]);

  const handleFlyComplete = useCallback(() => {
    setFlyToNodeId(null);
  }, []);

  return (
    <div className="absolute inset-0">
      <Canvas
        gl={{
          antialias: true,
          alpha: true,
          toneMapping: THREE.ACESFilmicToneMapping,
          toneMappingExposure: 1.3,
          outputColorSpace: THREE.SRGBColorSpace,
        }}
        camera={{ position: [0, 4, 16], fov: 52, near: 0.1, far: 120 }}
        dpr={[1, 1.5]}
      >
        <SceneContent
          state={state}
          onNodeClick={handleNodeClick}
          themeColor={themeColor}
          pulseIntensity={pulseIntensity}
          flyToNodeId={flyToNodeId}
          onFlyComplete={handleFlyComplete}
        />

        {/* Post processing — makes everything GLOW */}
        <EffectComposer>
          <Bloom
            luminanceThreshold={0.2}
            luminanceSmoothing={0.9}
            intensity={0.8}
            radius={0.5}
            mipmapBlur
          />
          <Vignette darkness={0.5} offset={0.15} />
          <Noise opacity={0.015} />
        </EffectComposer>
      </Canvas>

      {/* Radial vignette overlay for depth */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: 'radial-gradient(ellipse at center, transparent 35%, rgba(5,5,12,0.7) 100%)',
        }}
      />
    </div>
  );
}
