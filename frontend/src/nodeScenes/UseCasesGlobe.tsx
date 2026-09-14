import { Canvas, useFrame } from '@react-three/fiber';
import { useMemo, useRef } from 'react';
import * as THREE from 'three';

/**
 * Use Cases Portal thumbnail — port of use-cases-portal/js/preview3d.js `globe`
 * (wire sphere + core + pins). Signature of the portal boards, not a new look.
 */

function Globe({ accent }: { accent: string }) {
  const group = useRef<THREE.Group>(null!);
  const color = useMemo(() => new THREE.Color(accent), [accent]);
  const pins = useMemo(() => {
    const out: THREE.Vector3[] = [];
    for (let i = 0; i < 10; i++) {
      const th = (i / 10) * Math.PI * 2;
      const ph = 0.35 + (i % 4) * 0.28;
      out.push(
        new THREE.Vector3(
          Math.sin(ph) * Math.cos(th) * 0.72,
          Math.cos(ph) * 0.72,
          Math.sin(ph) * Math.sin(th) * 0.72,
        ),
      );
    }
    return out;
  }, []);

  useFrame((_, dt) => {
    if (!group.current) return;
    group.current.rotation.y += dt * 0.35;
    group.current.rotation.x = Math.sin(performance.now() * 0.0004) * 0.12;
  });

  return (
    <group ref={group}>
      <mesh>
        <sphereGeometry args={[0.72, 28, 28]} />
        <meshBasicMaterial color={color} wireframe transparent opacity={0.5} />
      </mesh>
      <mesh>
        <sphereGeometry args={[0.55, 24, 24]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={0.22}
          metalness={0.35}
          roughness={0.35}
          transparent
          opacity={0.38}
        />
      </mesh>
      {pins.map((p, i) => (
        <mesh key={i} position={p}>
          <sphereGeometry args={[0.045, 8, 8]} />
          <meshBasicMaterial color={i % 3 === 0 ? '#ffffff' : accent} />
        </mesh>
      ))}
      <mesh rotation={[Math.PI / 2.6, 0.2, 0.4]}>
        <torusGeometry args={[0.95, 0.012, 8, 64]} />
        <meshBasicMaterial color={color} transparent opacity={0.35} />
      </mesh>
      <mesh rotation={[0.4, Math.PI / 3, 0.1]}>
        <torusGeometry args={[1.12, 0.008, 8, 64]} />
        <meshBasicMaterial color={color} transparent opacity={0.22} />
      </mesh>
    </group>
  );
}

export default function UseCasesGlobe({
  accent = '#c4f542',
  mobile = false,
}: {
  accent?: string;
  mobile?: boolean;
}) {
  return (
    <Canvas
      dpr={mobile ? 1 : [1, 1.5]}
      camera={{ position: [0, 0.25, 2.6], fov: 42 }}
      gl={{ antialias: !mobile, alpha: true, powerPreference: 'high-performance' }}
      style={{ width: '100%', height: '100%' }}
    >
      <color attach="background" args={['#03050a']} />
      <ambientLight intensity={0.55} />
      <pointLight position={[2.5, 2, 3]} intensity={1.2} color={accent} />
      <pointLight position={[-2, -1.5, -2]} intensity={0.5} color="#60a5fa" />
      <Globe accent={accent} />
    </Canvas>
  );
}
