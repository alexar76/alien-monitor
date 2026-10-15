import { Canvas, useFrame } from '@react-three/fiber';
import { useMemo, useRef } from 'react';
import * as THREE from 'three';
import type { EcoNode } from '../App';

/**
 * eSIM operator thumbnail — what an operator running the kit IS, drawn from its own numbers:
 * a coverage globe with one light per country its catalogue reaches (healthz `countries`), the
 * eSIM chip it sells floating in front, signal waves leaving the chip, and agents orbiting it —
 * one per buyer that confirmed a delivery in 30 days (`deliveries_30d.distinct_buyers`), so a
 * seller nobody has bought from yet has an empty orbit rather than invented customers.
 * A demo seller's waves are dim: it quotes, it does not sell.
 */

const GOLD = '#e8c36a';
const MAX_PINS = 80;
const MAX_BUYERS = 12;

function spherePoints(count: number, radius: number): THREE.Vector3[] {
  // Golden-spiral spread: even coverage without randomness, the same picture on every reload.
  const out: THREE.Vector3[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i++) {
    const y = 1 - (i / Math.max(1, count - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const th = golden * i;
    out.push(new THREE.Vector3(Math.cos(th) * r * radius, y * radius, Math.sin(th) * r * radius));
  }
  return out;
}

function CoverageGlobe({ accent, countries }: { accent: string; countries: number }) {
  const group = useRef<THREE.Group>(null!);
  const color = useMemo(() => new THREE.Color(accent), [accent]);
  const pins = useMemo(() => spherePoints(Math.min(MAX_PINS, Math.max(0, countries)), 0.86), [countries]);

  useFrame((_, dt) => {
    if (group.current) group.current.rotation.y += dt * 0.18;
  });

  return (
    <group ref={group} position={[0, -0.05, -0.55]}>
      <mesh>
        <sphereGeometry args={[0.85, 24, 18]} />
        <meshBasicMaterial color={color} wireframe transparent opacity={0.16} />
      </mesh>
      <mesh>
        <sphereGeometry args={[0.8, 24, 24]} />
        <meshStandardMaterial color="#04140f" emissive={color} emissiveIntensity={0.08} transparent opacity={0.55} />
      </mesh>
      {pins.map((p, i) => (
        <mesh key={i} position={p}>
          <sphereGeometry args={[0.018, 6, 6]} />
          <meshBasicMaterial color={i % 5 === 0 ? '#ffffff' : accent} />
        </mesh>
      ))}
    </group>
  );
}

function simCardShape(): THREE.Shape {
  // A SIM outline: a rounded card with the one cut corner every SIM has.
  const w = 0.46, h = 0.6, r = 0.035, cut = 0.11;
  const x0 = -w / 2, y0 = -h / 2, x1 = w / 2, y1 = h / 2;
  const shape = new THREE.Shape();
  shape.moveTo(x0 + r, y0);
  shape.lineTo(x1 - r, y0);
  shape.quadraticCurveTo(x1, y0, x1, y0 + r);
  shape.lineTo(x1, y1 - cut);
  shape.lineTo(x1 - cut, y1);
  shape.lineTo(x0 + r, y1);
  shape.quadraticCurveTo(x0, y1, x0, y1 - r);
  shape.lineTo(x0, y0 + r);
  shape.quadraticCurveTo(x0, y0, x0 + r, y0);
  return shape;
}

function Chip({ accent }: { accent: string }) {
  const group = useRef<THREE.Group>(null!);
  const card = useMemo(
    () => new THREE.ExtrudeGeometry(simCardShape(), { depth: 0.03, bevelEnabled: false, curveSegments: 6 }),
    [],
  );
  const contacts = useMemo(() => {
    const out: [number, number][] = [];
    for (const x of [-0.072, 0.072]) for (const y of [-0.088, 0, 0.088]) out.push([x, y]);
    return out;
  }, []);

  useFrame(({ clock }) => {
    if (!group.current) return;
    const t = clock.getElapsedTime();
    group.current.position.y = 0.05 + Math.sin(t * 1.1) * 0.05;
    group.current.rotation.y = Math.sin(t * 0.6) * 0.45;
    group.current.rotation.x = -0.18 + Math.sin(t * 0.8) * 0.06;
  });

  return (
    <group ref={group} position={[0, 0.05, 0.55]}>
      <mesh geometry={card} position={[0, 0, -0.015]}>
        <meshStandardMaterial color={accent} emissive={accent} emissiveIntensity={0.35} metalness={0.45} roughness={0.3} />
      </mesh>
      {/* The chip: a darker gold pad, bright contacts separated by thin gaps. */}
      <mesh position={[0, -0.04, 0.018]}>
        <boxGeometry args={[0.27, 0.29, 0.004]} />
        <meshStandardMaterial color="#6b5222" emissive="#3a2a0e" emissiveIntensity={0.4} metalness={0.3} roughness={0.5} />
      </mesh>
      {contacts.map(([x, y], i) => (
        <mesh key={i} position={[x, y - 0.04, 0.022]}>
          <boxGeometry args={[0.13, 0.08, 0.004]} />
          <meshStandardMaterial color={GOLD} emissive={GOLD} emissiveIntensity={0.55} metalness={0.35} roughness={0.3} />
        </mesh>
      ))}
    </group>
  );
}

function SignalWaves({ accent, selling }: { accent: string; selling: boolean }) {
  const waves = useRef<(THREE.Mesh | null)[]>([]);
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    waves.current.forEach((mesh, i) => {
      if (!mesh) return;
      const phase = (t * 0.45 + i / 3) % 1;
      mesh.scale.setScalar(0.6 + phase * 1.1);
      (mesh.material as THREE.MeshBasicMaterial).opacity = (1 - phase) * (selling ? 0.55 : 0.18);
    });
  });
  return (
    <group position={[0, 0.32, 0.55]} rotation={[0, 0, Math.PI / 4]}>
      {[0, 1, 2].map((i) => (
        <mesh key={i} ref={(m) => { waves.current[i] = m; }}>
          <torusGeometry args={[0.32, 0.008, 6, 40, Math.PI / 2]} />
          <meshBasicMaterial color={accent} transparent opacity={0.3} depthWrite={false} />
        </mesh>
      ))}
    </group>
  );
}

function BuyerOrbit({ accent, buyers }: { accent: string; buyers: number }) {
  const group = useRef<THREE.Group>(null!);
  const count = Math.min(MAX_BUYERS, Math.max(0, buyers));
  useFrame((_, dt) => {
    if (group.current) group.current.rotation.y -= dt * 0.5;
  });
  return (
    <group rotation={[0.42, 0, 0.12]} position={[0, -0.05, -0.1]}>
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[1.12, 0.004, 6, 72]} />
        <meshBasicMaterial color={accent} transparent opacity={0.25} />
      </mesh>
      <group ref={group}>
        {Array.from({ length: count }, (_, i) => {
          const a = (i / Math.max(1, count)) * Math.PI * 2;
          return (
            <mesh key={i} position={[Math.cos(a) * 1.12, 0, Math.sin(a) * 1.12]}>
              <octahedronGeometry args={[0.045, 0]} />
              <meshBasicMaterial color="#ffffff" />
            </mesh>
          );
        })}
      </group>
    </group>
  );
}

export default function EsimOperatorScene({
  node,
  accent = '#2ef2b0',
  mobile = false,
}: {
  node: EcoNode;
  accent?: string;
  mobile?: boolean;
}) {
  const esim = node.esim;
  const countries = Number(esim?.countries ?? node.metrics?.countries ?? 0) || 0;
  const buyers = Number(esim?.deliveries_30d?.distinct_buyers ?? 0) || 0;
  const selling = esim?.demo === false;
  return (
    <Canvas
      dpr={mobile ? 1 : [1, 1.5]}
      camera={{ position: [0, 0.35, 2.75], fov: 42 }}
      gl={{ antialias: !mobile, alpha: true, powerPreference: 'high-performance' }}
      style={{ width: '100%', height: '100%' }}
    >
      <color attach="background" args={['#03050a']} />
      <ambientLight intensity={0.5} />
      <pointLight position={[2.2, 2, 3]} intensity={1.3} color={accent} />
      <pointLight position={[-2.4, -1, 2]} intensity={0.6} color={GOLD} />
      <CoverageGlobe accent={accent} countries={countries} />
      <BuyerOrbit accent={accent} buyers={buyers} />
      <Chip accent={accent} />
      <SignalWaves accent={accent} selling={selling} />
    </Canvas>
  );
}
