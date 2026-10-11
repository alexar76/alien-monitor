import { useEffect, useMemo, useRef } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';

/* ===========================================================================
 *  METIS star — the node-panel rendering of the landing-page scene.
 *
 *  This is the same procedural cosmic star as metis/docs/landing/index.html:
 *  an iridescent icosahedron core, Fibonacci-sphere spikes coloured by
 *  direction, glowing tips, three orbital rings, a coloured starfield.
 *
 *  It is drawn, not photographed. There is no screenshot of the landing here
 *  and there must not be one — the star is procedural everywhere it appears.
 *
 *  ── WHY THE NUMBERS MATCH THE LANDING ────────────────────────────────────
 *  An earlier pass cut this to 40 spikes, one ring and 90 starfield points to
 *  "save frames". That is not what a thinner version of this scene looks like:
 *  40 spikes on a Fibonacci sphere leaves visible gaps, so the urchin reads as
 *  a smooth blue ball with stubble, and one cyan ring reads as a stray ellipse
 *  rather than orbital structure. It looked broken, because at that density
 *  the shape is a different shape.
 *
 *  The cut also bought very little. Spikes are ONE InstancedMesh — 200 costs
 *  the same draw call as 40, and the per-frame work is 200 matrix composes.
 *  Rings are three trivial torus meshes. The starfield is one Points draw.
 *  What actually governs cost here is the frame rate and DPR, and those are
 *  already throttled by the caller (`fps`, `dpr`) and by `frameloop="demand"`.
 *
 *  Still omitted from the landing scene, deliberately, because they cost real
 *  frames and say nothing at panel size: lightning bolts between spike tips,
 *  bloom post-processing, and cognition-driven hue shifts.
 *
 *  Idle behaviour: slow breathing scale, gentle spike ripple, hue drift.
 * ========================================================================= */

// ── palette (identical to the landing-page scene) ──────────────────────────
const CYAN = new THREE.Color('#00e5ff');
const VIOLET = new THREE.Color('#7c4dff');
const MAGENTA = new THREE.Color('#ff2fb0');

/** Landing uses 260 desktop / 160 mobile. The caller picks; this is the default. */
const DEFAULT_SPIKES = 200;
const CORE_R = 0.4;
const TAU = Math.PI * 2;

/** Ring colour, radius offset and tilt — the landing's three, verbatim. */
const RINGS: Array<{ color: THREE.Color; r: number; rot: [number, number, number] }> = [
  { color: CYAN, r: 1.55, rot: [0, 0, 0] },
  { color: VIOLET, r: 1.83, rot: [1.1, 0.7, 0.5] },
  { color: MAGENTA, r: 2.11, rot: [2.2, 1.4, 1.0] },
];

// ── procedural spike directions (Fibonacci sphere, deterministic) ──────────
function spikeDirs(n: number): THREE.Vector3[] {
  const dirs: THREE.Vector3[] = [];
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2;
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const th = i * 2.399963229; // golden-angle advance
    dirs.push(new THREE.Vector3(Math.cos(th) * r, y, Math.sin(th) * r));
  }
  return dirs;
}

function hueOf(i: number, dirs: THREE.Vector3[]): number {
  const d = dirs[i];
  return ((d.y * 0.5 + 0.5) * 0.5 + (Math.atan2(d.z, d.x) / TAU) * 0.5 + 1) % 1;
}

/** Starfield: spherical shell in the landing's four colours, not a random cube.
 *  The cube version put points in the near corners of the frustum, which read as
 *  dirt on the lens rather than distance. */
function useStarfield(count: number) {
  return useMemo(() => {
    const pos = new Float32Array(count * 3);
    const col = new Float32Array(count * 3);
    const pal = [CYAN, VIOLET, new THREE.Color('#ffffff'), new THREE.Color('#2b8cff')];
    for (let i = 0; i < count; i++) {
      const r = 6 + Math.random() * 9;
      const th = Math.random() * TAU;
      const ph = Math.acos(2 * Math.random() - 1);
      pos[i * 3] = r * Math.sin(ph) * Math.cos(th);
      pos[i * 3 + 1] = r * Math.sin(ph) * Math.sin(th);
      pos[i * 3 + 2] = r * Math.cos(ph);
      const c = pal[(Math.random() * pal.length) | 0];
      col[i * 3] = c.r;
      col[i * 3 + 1] = c.g;
      col[i * 3 + 2] = c.b;
    }
    return { pos, col };
  }, [count]);
}

/** Spike mesh, built imperatively exactly as the landing does it.
 *
 *  It was declarative before, and two things silently broke:
 *
 *  · `<coneGeometry onUpdate={g => g.translate(0, .5, 0)}>` never fired, so the
 *    cone stayed centred on the origin — spanning y −0.5…+0.5 instead of 0…1.
 *    Half of every spike pointed back into the core and the visible reach was
 *    half of `baseLen`, which is why the urchin sat in the middle of the rings
 *    instead of nearly touching them.
 *  · The instance colours never reached `vColor`, so `emissive + vColor * uEmis`
 *    evaluated to black and 260 spikes rendered as dark needles.
 *
 *  Constructing the InstancedMesh here removes the attach-order guesswork: the
 *  geometry is translated once, instanceColor is allocated before anything reads
 *  it, and the emissive patch is attached to a material that definitely exists.
 */
function useSpikeMesh(dirs: THREE.Vector3[], baseLen: number[]) {
  return useMemo(() => {
    const geo = new THREE.ConeGeometry(0.03, 1, 7);
    geo.translate(0, 0.5, 0);                       // base at origin → tip at +1

    // NO `vertexColors`. Three feeds an InstancedMesh's per-instance colours to
    // `vColor` on its own (USE_INSTANCING_COLOR). Setting vertexColors as well
    // makes the shader also read a per-VERTEX `color` attribute, which this cone
    // geometry does not have — so vColor came out (0,0,0) and every spike
    // rendered black, both as diffuse tint and through the emissive patch below.
    // The landing's material does not set it either; that is the difference.
    const mat = new THREE.MeshStandardMaterial({
      color: 0xffffff, emissive: 0x000000, roughness: 0.35, metalness: 0.25,
    });
    mat.onBeforeCompile = (sh) => {
      sh.uniforms.uEmis = { value: 0.5 };
      sh.fragmentShader = 'uniform float uEmis;\n' + sh.fragmentShader.replace(
        'vec3 totalEmissiveRadiance = emissive;',
        'vec3 totalEmissiveRadiance = emissive + vColor * uEmis;');
    };

    const mesh = new THREE.InstancedMesh(geo, mat, dirs.length);
    mesh.frustumCulled = false;
    const up = new THREE.Vector3(0, 1, 0);
    const q = new THREE.Quaternion(), m = new THREE.Matrix4();
    const p = new THREE.Vector3(), s = new THREE.Vector3(), c = new THREE.Color();
    for (let i = 0; i < dirs.length; i++) {
      q.setFromUnitVectors(up, dirs[i]);
      p.copy(dirs[i]).multiplyScalar(CORE_R);
      s.set(1, baseLen[i], 1);
      mesh.setMatrixAt(i, m.compose(p, q, s));
      c.setHSL(hueOf(i, dirs), 0.85, 0.6);
      mesh.setColorAt(i, c);
    }
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    return mesh;
  }, [dirs, baseLen]);
}

// ── star scene ─────────────────────────────────────────────────────────────
function StarScene({ running, spikeCount }: { running: boolean; spikeCount: number }) {
  const root = useRef<THREE.Group>(null);
  const coreMat = useRef<THREE.MeshStandardMaterial>(null);
  const innerGlow = useRef<THREE.MeshBasicMaterial>(null);
  const ringRefs = useRef<Array<THREE.Mesh | null>>([]);
  const tips = useRef<THREE.Points>(null);

  const tmpC = useMemo(() => new THREE.Color(), []);

  const dirs = useMemo(() => spikeDirs(spikeCount), [spikeCount]);
  // 0.55 + rand*0.95, as on the landing. The panel version used *0.75, which is
  // why the spikes looked cropped against the rings.
  const baseLen = useMemo(() => dirs.map(() => 0.55 + Math.random() * 0.95), [dirs]);
  const phase = useMemo(() => dirs.map(() => Math.random() * TAU), [dirs]);
  const stars = useStarfield(700);
  const spikeMesh = useSpikeMesh(dirs, baseLen);

  // Scratch objects, reused every frame. With 200 instances a `.clone()` in the
  // loop is 200 allocations per painted frame, i.e. GC pressure at 24 fps.
  const UP = useMemo(() => new THREE.Vector3(0, 1, 0), []);
  const scratch = useMemo(() => ({
    q: new THREE.Quaternion(), m: new THREE.Matrix4(),
    p: new THREE.Vector3(), s: new THREE.Vector3(),
  }), []);

  const st = useMemo(() => ({ t: 0 }), []);

  useFrame((_, rawDelta) => {
    const dt = running ? Math.min(rawDelta, 1 / 15) : 0;
    st.t += dt;
    const t = st.t;

    // breathing scale
    const hb = Math.exp(-14 * ((t * 0.9) % 1) * ((t * 0.9) % 1));
    const s = 1 + 0.04 * hb + 0.02 * Math.sin(t * 0.6);
    if (root.current) root.current.scale.setScalar(s);

    // spike ripple — gentle wave
    {
      const wave = 0.18;
      const drift = (t * 0.05) % 1;
      // `scale`, not `s` — `s` is the breathing scalar a few lines up, and letting
      // a Vector3 shadow it inside the loop is a trap for whoever edits this next.
      const { q, m, p, s: scale } = scratch;
      for (let i = 0; i < spikeCount; i++) {
        const lm = 1 + wave * Math.sin(t * 2.2 + phase[i] + i * 0.05) + hb * 0.1;
        q.setFromUnitVectors(UP, dirs[i]);
        p.copy(dirs[i]).multiplyScalar(CORE_R);
        scale.set(1, baseLen[i] * lm, 1);
        m.compose(p, q, scale);
        spikeMesh.setMatrixAt(i, m);
        tmpC.setHSL((hueOf(i, dirs) + drift) % 1, 0.85, 0.6);
        spikeMesh.setColorAt(i, tmpC);
      }
      spikeMesh.instanceMatrix.needsUpdate = true;
      if (spikeMesh.instanceColor) spikeMesh.instanceColor.needsUpdate = true;
    }

    // core emissive pulse
    if (coreMat.current) {
      coreMat.current.emissiveIntensity = 0.25 + 0.25 * hb;
    }
    if (innerGlow.current) {
      innerGlow.current.opacity = 0.12 + 0.14 * hb;
    }

    // orbital rings — each on its own axis, so they read as three planes rather
    // than one wobbling hoop.
    ringRefs.current.forEach((r, i) => {
      if (!r) return;
      r.rotation.z += dt * (0.22 - i * 0.05);
      r.rotation.x += dt * (0.08 + i * 0.04);
    });

    // tip points pulse
    if (tips.current) {
      (tips.current.material as THREE.PointsMaterial).opacity = 0.55 + 0.25 * hb;
      (tips.current.material as THREE.PointsMaterial).size = 0.04 + 0.01 * hb;
    }
  });

  return (
    <group ref={root}>
      {/* iridescent core */}
      <mesh>
        <icosahedronGeometry args={[0.42, 3]} />
        <meshStandardMaterial
          ref={coreMat}
          color={0x1b2f7a}
          emissive={0x2b8cff}
          emissiveIntensity={0.3}
          roughness={0.25}
          metalness={0.3}
        />
      </mesh>
      {/* inner glow kernel */}
      <mesh>
        <icosahedronGeometry args={[0.26, 2]} />
        <meshBasicMaterial
          ref={innerGlow}
          color={0xbfe9ff}
          transparent
          opacity={0.22}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>

      {/* instanced spikes — one draw call whatever the count */}
      <primitive object={spikeMesh} />

      {/* glowing spike tips */}
      <points ref={tips}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[new Float32Array(dirs.flatMap((d, i) => {
              const dist = CORE_R + baseLen[i];
              return [d.x * dist, d.y * dist, d.z * dist];
            })), 3]}
            count={spikeCount}
            itemSize={3}
          />
        </bufferGeometry>
        <pointsMaterial
          color={0xdff3ff}
          size={0.05}
          transparent
          opacity={0.7}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </points>

      {/* three orbital rings — cyan / violet / magenta, the landing's set.
          One ring alone read as a stray ellipse instead of orbital structure. */}
      {RINGS.map((r, i) => (
        <mesh
          key={i}
          ref={(el) => { ringRefs.current[i] = el; }}
          rotation={r.rot}
        >
          <torusGeometry args={[r.r, 0.012, 8, 120]} />
          <meshBasicMaterial
            color={r.color}
            transparent
            opacity={0.5}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </mesh>
      ))}

      {/* starfield — coloured spherical shell, behind the star */}
      <points>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[stars.pos, 3]} />
          <bufferAttribute attach="attributes-color" args={[stars.col, 3]} />
        </bufferGeometry>
        <pointsMaterial
          size={0.09}
          vertexColors
          transparent
          opacity={0.85}
          sizeAttenuation
          depthWrite={false}
        />
      </points>
    </group>
  );
}

// ── helpers ─────────────────────────────────────────────────────────────────

function FitToBox({ target }: { target: React.RefObject<THREE.Group | null> }) {
  const size = useThree((s) => s.size);
  const camera = useThree((s) => s.camera);
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    const g = target.current;
    const cam = camera as THREE.PerspectiveCamera;
    if (!g || !cam.isPerspectiveCamera || !size.width || !size.height) return;
    const visH = 2 * Math.tan((cam.fov * Math.PI) / 360) * cam.position.z;
    const visW = visH * (size.width / size.height);
    const sc = Math.min(visW / 4.2, visH / 4.2);
    g.scale.setScalar(sc);
    invalidate();
  }, [size, camera, invalidate, target]);
  return null;
}

function FrameDriver({ running, fps }: { running: boolean; fps: number }) {
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    invalidate();
    if (!running) return undefined;
    const id = window.setInterval(() => invalidate(), Math.max(16, Math.round(1000 / fps)));
    return () => window.clearInterval(id);
  }, [running, fps, invalidate]);
  return null;
}

// ── public API ──────────────────────────────────────────────────────────────

export interface MetisStarCanvasProps {
  running: boolean;
  fps?: number;
  dpr?: [number, number];
  /** Landing uses 260 desktop / 160 mobile. Instanced, so this is nearly free. */
  spikeCount?: number;
}

export default function MetisStarCanvas({
  running,
  fps = 24,
  dpr = [1, 1.25],
  spikeCount = DEFAULT_SPIKES,
}: MetisStarCanvasProps) {
  const rootRef = useRef<THREE.Group>(null);
  return (
    <Canvas
      className="absolute inset-0"
      style={{ pointerEvents: 'none' }}
      frameloop="demand"
      dpr={dpr}
      camera={{ position: [0, 0.4, 7], fov: 46, near: 0.1, far: 60 }}   /* fov 46 = the landing's lens */
      gl={{
        antialias: true,
        alpha: false,
        preserveDrawingBuffer: true,
        powerPreference: 'low-power',
        failIfMajorPerformanceCaveat: false,
        toneMapping: THREE.ACESFilmicToneMapping,
        toneMappingExposure: 1.0,
      }}
    >
      <color attach="background" args={['#03040a']} />
      <ambientLight intensity={0.7} color="#16304f" />
      <pointLight position={[5, 5, 7]} intensity={8.4} color="#62b0ff" />
      <pointLight position={[-6, -2, 4]} intensity={4.3} color="#7c4dff" />
      <pointLight position={[-3, 4, -6]} intensity={3.6} color="#00e5ff" />
      <group ref={rootRef}>
        <StarScene running={running} spikeCount={spikeCount} />
      </group>
      <FitToBox target={rootRef} />
      <FrameDriver running={running} fps={fps} />
    </Canvas>
  );
}
