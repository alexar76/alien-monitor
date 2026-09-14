import { useEffect, useMemo, useRef } from 'react';
import type { MutableRefObject } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';

/* ===========================================================================
 *  MOMUS eye — COMPACT node-panel edition.
 *
 *  A miniature of the satellite's signature scene
 *  (momus/frontend/src/scenes/momus.tsx): the same almond lid maths, the same
 *  procedural fibre-iris shader, the same crimson→amber palette on the family's
 *  deep-space background. What is gone is everything that cost frames and said
 *  nothing here — the probe beams, the orbiting target orbs, the chest-window
 *  brackets, the nebula and the post-processing stack. The monitor already runs
 *  a heavy R3F scene behind this panel; this one is a thumbnail, not a rival.
 *
 *  NOTHING in here invents state. Every motion is switched by `EyeDrive`, which
 *  the panel fills from the momus_live payload:
 *
 *      · idle          → slow pupil drift + breathing dilation, no sweep
 *      · scanning      → the scan blade sweeps (ONLY while the monitor has
 *                        actually observed MOMUS's scan counter advance)
 *      · alert > 0     → crimson pulse, intensity tracks reported severity
 *      · frozen        → neutral pose, zero motion; the driver stops calling
 *                        invalidate(), so the last frame simply stands still
 *
 *  Cost control: `frameloop="demand"` — the canvas renders only when the parent
 *  ticks it (capped fps, and not at all when the panel is off-screen, the tab is
 *  hidden, the data is stale, or the visitor asked for reduced motion).
 * ========================================================================= */

/** Live drive state, MUTATED IN PLACE by the panel: a 3 s payload refresh or a
 *  pointer move must never re-render React or re-create the WebGL context. */
export interface EyeDrive {
  /** 0..1 red-pulse intensity. Non-zero ONLY for a reported high/critical finding. */
  alert: number;
  /** True ONLY while a scan has been observed; drives the sweep. */
  scanning: boolean;
  /** True when the payload is not live — the eye holds a neutral pose. */
  frozen: boolean;
  /** Pointer in -1..1 panel coordinates (x right, y up); used only while `hover`. */
  px: number;
  py: number;
  hover: boolean;
}

export const NEUTRAL_DRIVE: EyeDrive = {
  alert: 0,
  scanning: false,
  frozen: false,
  px: 0,
  py: 0,
  hover: false,
};

// ── palette (identical to the satellite scene) ──────────────────────────────
const CRIMSON = new THREE.Color('#ff2d55');
const AMBER = new THREE.Color('#ff6b3d');
const WHITE = new THREE.Color('#fff2f5');

// ── eye geometry (same constants as the full scene) ─────────────────────────
const W = 3.55;
const H_UP = 1.62;
const H_DN = 1.24;
const BULGE = 0.34;
const IRIS_IN = 0.34;
const IRIS_OUT = 1.3;
const IRIS_Z = 0.3;
const PUPIL_R = 0.5;

const N_BLADES = 48; // 108 in the full scene — this one is 200 px tall
const N_STARS = 90;
const TAU = Math.PI * 2;

const clamp = (v: number, lo: number, hi: number) => (v < lo ? lo : v > hi ? hi : v);

/** 32-bit integer hash — deterministic layout, no Math.random() anywhere. */
function hash32(n: number): number {
  let x = n | 0;
  x = (x ^ 61) ^ (x >>> 16);
  x = (x + (x << 3)) | 0;
  x = x ^ (x >>> 4);
  x = Math.imul(x, 0x27d4eb2d);
  x = x ^ (x >>> 15);
  return x >>> 0;
}
const unit = (h: number, shift: number) => ((h >>> shift) % 1000) / 1000;

/** Circular arc through (-W,0), (0,h), (W,0) — the lid curve, built from maths. */
function lidY(x: number, h: number): number {
  const R = (W * W + h * h) / (2 * h);
  return Math.sqrt(Math.max(0, R * R - x * x)) + (h - R);
}
function lensLoop(scale: number, segs = 96): THREE.Vector3[] {
  const pts: THREE.Vector3[] = [];
  const push = (x: number, y: number) => {
    const zx = x / (W * scale);
    pts.push(new THREE.Vector3(x, y, BULGE * (1 - zx * zx)));
  };
  for (let i = 0; i <= segs; i++) {
    const x = (-W + (2 * W * i) / segs) * scale;
    push(x, lidY(x / scale, H_UP) * scale);
  }
  for (let i = segs - 1; i >= 1; i--) {
    const x = (-W + (2 * W * i) / segs) * scale;
    push(x, -lidY(x / scale, H_DN) * scale);
  }
  return pts;
}

// ── iris shader: the family's procedural fibres + a SWITCHABLE scan sweep ────
const IRIS_VERT = `
varying vec2 vP;
void main(){ vP = position.xy; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }
`;
// uSweep is the one addition to the satellite's shader: at 0 the sweep term
// vanishes entirely, so "not scanning" looks like not scanning — not like a
// scan running slowly.
const IRIS_FRAG = `
precision mediump float;
varying vec2 vP;
uniform float uTime, uScan, uPupil, uTension, uSweep;
float h1(float x){ return fract(sin(x*127.1)*43758.5453); }
void main(){
  float r = length(vP);
  float a = atan(vP.y, vP.x);

  float seed  = h1(floor((a+3.14159265)*22.0));
  float fibre = 0.42 + 0.58*pow(0.5+0.5*sin(a*64.0 + seed*9.0 + r*5.0), 1.6);
  fibre *= 0.66 + 0.34*sin(a*171.0 + seed*20.0 - r*11.0);

  float inner  = smoothstep(uPupil-0.05, uPupil+0.22, r);
  float outer  = 1.0 - smoothstep(1.04, 1.30, r);
  float rim    = exp(-pow((r-(uPupil+0.09))/0.10, 2.0));
  float limbal = exp(-pow((r-1.225)/0.05, 2.0));

  float d = mod(a - uScan + 3.14159265, 6.28318531) - 3.14159265;
  float lead  = exp(-pow(d/0.15, 2.0));
  float trail = exp(max(-7.0, d*2.6)) * step(d, 0.02);
  float scan  = (lead*1.8 + trail*0.85) * uSweep;

  vec3 amber   = vec3(1.00, 0.42, 0.24);
  vec3 crimson = vec3(1.00, 0.18, 0.33);
  vec3 col = mix(amber, crimson, smoothstep(uPupil, 1.22, r));

  float br = (0.22 + 0.85*fibre) * inner * outer;
  br += rim*0.42*inner + limbal*0.34;
  br *= 1.0 + scan*1.25;
  col *= br;
  col += vec3(1.0, 0.76, 0.64) * lead * uSweep * inner * outer * 0.55;
  col += vec3(1.0, 0.24, 0.34) * uTension * 0.26 * inner * outer;
  gl_FragColor = vec4(col * (0.97 + 0.03*sin(uTime*2.1 + r*6.0)), 1.0);
}
`;

/** Scales the eye so the whole almond fits whatever box the panel gives us. */
function FitToBox({ target }: { target: MutableRefObject<THREE.Group | null> }) {
  const size = useThree((s) => s.size);
  const camera = useThree((s) => s.camera);
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    const g = target.current;
    const cam = camera as THREE.PerspectiveCamera;
    if (!g || !cam.isPerspectiveCamera || !size.width || !size.height) return;
    const visH = 2 * Math.tan((cam.fov * Math.PI) / 360) * cam.position.z;
    const visW = visH * (size.width / size.height);
    const s = Math.min(visW / (2 * W * 1.14), visH / ((H_UP + H_DN) * 1.55));
    g.scale.setScalar(s);
    invalidate();
  }, [size, camera, invalidate, target]);
  return null;
}

/** Frame-rate cap: in demand mode NOTHING renders unless we tick it. */
function FrameDriver({ running, fps }: { running: boolean; fps: number }) {
  const invalidate = useThree((s) => s.invalidate);
  useEffect(() => {
    // Always paint one frame so a state change (e.g. going stale) is visible,
    // then stop unless we are allowed to animate.
    invalidate();
    if (!running) return undefined;
    const id = window.setInterval(() => invalidate(), Math.max(16, Math.round(1000 / fps)));
    return () => window.clearInterval(id);
  }, [running, fps, invalidate]);
  return null;
}

function EyeScene({
  drive,
  still,
}: {
  drive: MutableRefObject<EyeDrive>;
  /** True when only ONE frame will be painted (reduced motion, off-screen,
   *  hidden tab). Eased values snap to their target instead of easing, or the
   *  single frame would show a half-arrived state. */
  still: boolean;
}) {
  const root = useRef<THREE.Group>(null);
  const gaze = useRef<THREE.Group>(null);
  const irisMat = useRef<THREE.ShaderMaterial>(null);
  const blades = useRef<THREE.InstancedMesh>(null);
  const pupil = useRef<THREE.Mesh>(null);
  const glowMat = useRef<THREE.MeshBasicMaterial>(null);
  const catchRef = useRef<THREE.Mesh>(null);
  const sweep = useRef<THREE.Group>(null);
  const sweepBar = useRef<THREE.Mesh>(null);
  const sweepTip = useRef<THREE.Mesh>(null);
  const haloRef = useRef<THREE.Mesh>(null);
  const haloMat = useRef<THREE.MeshBasicMaterial>(null);
  const rimMat = useRef<THREE.MeshBasicMaterial>(null);

  // scratch — zero allocation on the hot path
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const tmpC = useMemo(() => new THREE.Color(), []);

  const rimGeo = useMemo(() => {
    const curve = new THREE.CatmullRomCurve3(lensLoop(1), true, 'centripetal', 0.5);
    return new THREE.TubeGeometry(curve, 150, 0.028, 4, true);
  }, []);
  const rimGeo2 = useMemo(() => {
    const curve = new THREE.CatmullRomCurve3(lensLoop(1.085), true, 'centripetal', 0.5);
    return new THREE.TubeGeometry(curve, 110, 0.014, 3, true);
  }, []);
  const scleraGeo = useMemo(() => {
    const pts2 = lensLoop(0.985).map((p) => new THREE.Vector2(p.x, p.y));
    return new THREE.ShapeGeometry(new THREE.Shape(pts2));
  }, []);

  const starGeo = useMemo(() => {
    const pos = new Float32Array(N_STARS * 3);
    for (let i = 0; i < N_STARS; i++) {
      const h = hash32(i * 2654435761 + 17);
      pos[i * 3] = (unit(h, 2) - 0.5) * 26;
      pos[i * 3 + 1] = (unit(h, 11) - 0.5) * 16;
      pos[i * 3 + 2] = -4 - unit(h, 20) * 9;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    return g;
  }, []);

  // Blade layout is FIXED (angle, radii, hue mix, flicker phase) — only colour
  // changes per frame, so the instance matrices are written exactly once.
  const bladeSpec = useMemo(() => {
    const a = new Float32Array(N_BLADES * 4);
    for (let i = 0; i < N_BLADES; i++) {
      const h = hash32(i * 40503 + 7);
      const j0 = unit(h, 2);
      const j1 = unit(h, 12);
      a[i * 4] = (i / N_BLADES) * TAU;
      a[i * 4 + 1] = 0.66 + j0 * 0.12; // inner radius (clear of the dilated pupil)
      a[i * 4 + 2] = 1.16 + j1 * 0.14; // outer radius
      a[i * 4 + 3] = j0 * 0.65 + j1 * 0.35; // crimson ↔ amber mix
    }
    return a;
  }, []);

  useEffect(() => {
    const mesh = blades.current;
    if (!mesh) return;
    for (let i = 0; i < N_BLADES; i++) {
      const ang = bladeSpec[i * 4];
      const r0 = bladeSpec[i * 4 + 1];
      const r1 = bladeSpec[i * 4 + 2];
      const mix = bladeSpec[i * 4 + 3];
      const len = Math.max(0.02, r1 - r0);
      const rm = (r0 + r1) * 0.5;
      dummy.position.set(Math.cos(ang) * rm, Math.sin(ang) * rm, IRIS_Z + 0.035);
      dummy.rotation.set(0, 0, ang);
      dummy.scale.set(len, 0.02 + 0.012 * mix, 0.012);
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
    }
    mesh.instanceMatrix.needsUpdate = true;
  }, [bladeSpec, dummy]);

  const irisUniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uScan: { value: 0 },
      uPupil: { value: PUPIL_R },
      uTension: { value: 0 },
      uSweep: { value: 0 },
    }),
    [],
  );

  // Animation state advances ONLY on rendered frames, so "paused" is genuinely
  // frozen rather than resumed further along an invisible timeline.
  const st = useMemo(() => ({ t: 0, scanPhase: 0, sweepAmp: 0, tension: 0, gx: 0, gy: 0 }), []);

  useFrame((_, rawDelta) => {
    const d = drive.current;
    const frozen = d.frozen;
    const dt = frozen ? 0 : Math.min(rawDelta, 1 / 15);
    st.t += dt;
    const t = st.t;

    // Eased switches — nothing pops on or off. But when only one frame will be
    // painted there is nothing to ease INTO: snap, or a reduced-motion visitor
    // gets a calm eye over a critical finding, which is the exact lie this
    // component exists to avoid.
    const kFast = still ? 1 : 1 - Math.exp(-dt * 6);
    const kSlow = still ? 1 : 1 - Math.exp(-dt * 3);
    const wantSweep = !frozen && d.scanning ? 1 : 0;
    st.sweepAmp += (wantSweep - st.sweepAmp) * (dt > 0 || still ? kSlow : 1);
    const wantAlert = frozen ? 0 : clamp(d.alert, 0, 1);
    st.tension += (wantAlert - st.tension) * (dt > 0 || still ? kFast : 1);
    if (frozen) {
      st.sweepAmp = 0;
      st.tension = 0;
    }

    // ── gaze: cursor while hovered, slow drift otherwise ──────────────────
    let tx = 0;
    let ty = 0;
    if (!frozen) {
      if (d.hover) {
        tx = clamp(d.px, -1, 1) * 0.30;
        ty = clamp(d.py, -1, 1) * 0.16;
      } else {
        tx = 0.09 * Math.sin(t * 0.23) + 0.05 * Math.sin(t * 0.41 + 1.3);
        ty = 0.05 * Math.sin(t * 0.19 + 0.7) + 0.03 * Math.sin(t * 0.37 + 2.1);
      }
    }
    const kGaze = dt > 0 ? 1 - Math.exp(-dt * 5) : 1;
    st.gx += (tx - st.gx) * kGaze;
    st.gy += (ty - st.gy) * kGaze;
    if (gaze.current) gaze.current.position.set(st.gx, st.gy, 0);
    if (root.current) {
      // a whisper of parallax so the eye reads as a solid object, not a decal
      root.current.rotation.y = st.gx * 0.30;
      root.current.rotation.x = -st.gy * 0.34;
    }

    // ── pupil: breathing dilation; a finding constricts it ────────────────
    const dil = frozen
      ? 1
      : 1 + 0.05 * Math.sin(t * 0.62) + 0.03 * Math.sin(t * 1.31 + 1.1) - 0.16 * st.tension;
    const pr = PUPIL_R * dil;
    if (pupil.current) pupil.current.scale.set(dil, dil, dil * 0.62);
    if (glowMat.current) {
      glowMat.current.opacity = frozen
        ? 0.08
        : 0.1 + 0.05 * Math.sin(t * 0.9) + st.tension * 0.26;
      tmpC.copy(AMBER).lerp(CRIMSON, frozen ? 0.5 : 0.5 + 0.5 * Math.sin(t * 0.35));
      glowMat.current.color.copy(tmpC);
    }
    if (catchRef.current) {
      catchRef.current.position.set(-0.17, 0.18, IRIS_Z + 0.24);
      catchRef.current.scale.setScalar(0.055);
    }

    // ── iris ──────────────────────────────────────────────────────────────
    st.scanPhase = (st.scanPhase + dt * 0.95 * (d.scanning && !frozen ? 1 : 0)) % TAU;
    if (irisMat.current) {
      const u = irisMat.current.uniforms;
      u.uTime.value = t;
      u.uScan.value = st.scanPhase;
      u.uPupil.value = pr;
      u.uTension.value = st.tension;
      u.uSweep.value = st.sweepAmp;
    }
    if (blades.current) {
      for (let i = 0; i < N_BLADES; i++) {
        const ang = bladeSpec[i * 4];
        const mix = bladeSpec[i * 4 + 3];
        let dd = (((ang - st.scanPhase + Math.PI) % TAU) + TAU) % TAU - Math.PI;
        const lead = Math.exp(-((dd / 0.22) * (dd / 0.22)));
        const trail = dd < 0.02 ? Math.exp(Math.max(-7, dd * 2.4)) : 0;
        const boost = 1 + (lead * 2.6 + trail * 0.9) * st.sweepAmp;
        tmpC.copy(CRIMSON).lerp(AMBER, mix);
        tmpC.multiplyScalar((frozen ? 0.42 : 0.4 + 0.16 * Math.sin(t * 1.1 + mix * 6.0)) * boost);
        if (st.tension > 0.02) tmpC.lerp(WHITE, st.tension * 0.22);
        blades.current.setColorAt(i, tmpC);
      }
      if (blades.current.instanceColor) blades.current.instanceColor.needsUpdate = true;
    }

    // ── scan blade — present ONLY while a scan is actually running ────────
    const amp = st.sweepAmp;
    if (sweep.current) {
      sweep.current.rotation.z = st.scanPhase;
      sweep.current.visible = amp > 0.01;
    }
    if (sweepBar.current) {
      const mid = (pr + 0.06 + IRIS_OUT) * 0.5;
      sweepBar.current.position.set(mid, 0, IRIS_Z + 0.075);
      sweepBar.current.scale.set(Math.max(0.02, IRIS_OUT - pr - 0.06), 0.05, 0.012);
      (sweepBar.current.material as THREE.MeshBasicMaterial).opacity = 0.85 * amp;
    }
    if (sweepTip.current) {
      sweepTip.current.position.set(IRIS_OUT - 0.02, 0, IRIS_Z + 0.08);
      sweepTip.current.scale.setScalar(0.07 * (0.4 + 0.6 * amp));
      (sweepTip.current.material as THREE.MeshBasicMaterial).opacity = 0.95 * amp;
    }

    // ── severity pulse — amplitude AND rate follow the reported severity ──
    if (haloRef.current && haloMat.current) {
      const a = st.tension;
      if (a < 0.01) {
        haloRef.current.visible = false;
        haloMat.current.opacity = 0;
      } else {
        const beat = 0.5 + 0.5 * Math.sin(t * (3.0 + a * 2.6));
        haloRef.current.visible = true;
        haloRef.current.scale.setScalar(1 + a * 0.08 * beat);
        haloMat.current.opacity = a * (0.34 + 0.46 * beat);
      }
    }
    if (rimMat.current) {
      tmpC.copy(CRIMSON).lerp(AMBER, frozen ? 0.3 : 0.35 + 0.25 * Math.sin(t * 0.4));
      rimMat.current.color.copy(tmpC).multiplyScalar(1.5 + st.tension * 1.1);
    }
  });

  return (
    <group ref={root}>
      <points geometry={starGeo}>
        <pointsMaterial size={0.055} color="#9fb6ff" transparent opacity={0.55} sizeAttenuation />
      </points>

      {/* dark sclera backing — the almond silhouette against the starfield */}
      <mesh geometry={scleraGeo} position={[0, 0, -0.35]}>
        <meshBasicMaterial color="#0a0410" transparent opacity={0.78} depthWrite={false} />
      </mesh>

      {/* glowing lid outline (procedural arcs → tube) */}
      <mesh geometry={rimGeo}>
        <meshBasicMaterial
          ref={rimMat}
          color={CRIMSON}
          toneMapped={false}
          transparent
          opacity={0.95}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>
      <mesh geometry={rimGeo2}>
        <meshBasicMaterial
          color={AMBER}
          toneMapped={false}
          transparent
          opacity={0.32}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
        />
      </mesh>

      <group ref={gaze}>
        {/* iris body — the family's fibre shader, sweep switchable */}
        <mesh position={[0, 0, IRIS_Z]}>
          <ringGeometry args={[IRIS_IN, IRIS_OUT, 72, 1]} />
          <shaderMaterial
            ref={irisMat}
            vertexShader={IRIS_VERT}
            fragmentShader={IRIS_FRAG}
            uniforms={irisUniforms}
            transparent
            blending={THREE.AdditiveBlending}
            depthWrite={false}
            toneMapped={false}
            side={THREE.DoubleSide}
          />
        </mesh>

        <instancedMesh
          ref={blades as never}
          args={[undefined as never, undefined as never, N_BLADES]}
          frustumCulled={false}
        >
          <boxGeometry args={[1, 1, 1]} />
          <meshBasicMaterial
            vertexColors
            toneMapped={false}
            transparent
            opacity={0.9}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </instancedMesh>

        {/* Severity pulse — a limbal RING, not a disc. A wide filled halo at this
            thumbnail size swallowed the almond silhouette, and the silhouette is
            the thing that says "MOMUS" at a glance. */}
        <mesh ref={haloRef} position={[0, 0, IRIS_Z - 0.02]} visible={false}>
          <ringGeometry args={[1.28, 1.52, 64, 1]} />
          <meshBasicMaterial
            ref={haloMat}
            color={CRIMSON}
            toneMapped={false}
            transparent
            opacity={0}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
            side={THREE.DoubleSide}
          />
        </mesh>

        {/* scan blade */}
        <group ref={sweep} visible={false}>
          <mesh ref={sweepBar}>
            <boxGeometry args={[1, 1, 1]} />
            <meshBasicMaterial
              color="#fff0f2"
              toneMapped={false}
              transparent
              opacity={0}
              blending={THREE.AdditiveBlending}
              depthWrite={false}
            />
          </mesh>
          <mesh ref={sweepTip}>
            <sphereGeometry args={[1, 10, 8]} />
            <meshBasicMaterial
              color="#ffd9c9"
              toneMapped={false}
              transparent
              opacity={0}
              blending={THREE.AdditiveBlending}
              depthWrite={false}
            />
          </mesh>
        </group>

        {/* pupil dome + inner glow + catchlight */}
        <mesh ref={pupil} position={[0, 0, IRIS_Z]}>
          <sphereGeometry args={[PUPIL_R, 28, 20]} />
          <meshBasicMaterial color="#0b0208" toneMapped={false} />
        </mesh>
        <mesh position={[0, 0, IRIS_Z]}>
          <sphereGeometry args={[PUPIL_R * 1.24, 18, 14]} />
          <meshBasicMaterial
            ref={glowMat}
            color={AMBER}
            toneMapped={false}
            transparent
            opacity={0.14}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
            side={THREE.BackSide}
          />
        </mesh>
        <mesh ref={catchRef}>
          <sphereGeometry args={[1, 10, 8]} />
          <meshBasicMaterial
            color="#fff6f8"
            toneMapped={false}
            transparent
            opacity={0.9}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
          />
        </mesh>
      </group>
    </group>
  );
}

export interface MomusEyeCanvasProps {
  drive: MutableRefObject<EyeDrive>;
  /** False → one frame, then complete stop (off-screen, hidden tab, stale, reduced motion). */
  running: boolean;
  /** Frame-rate cap while running. */
  fps?: number;
  dpr?: [number, number];
}

export default function MomusEyeCanvas({ drive, running, fps = 24, dpr = [1, 1.5] }: MomusEyeCanvasProps) {
  const rootRef = useRef<THREE.Group>(null);
  return (
    <Canvas
      className="absolute inset-0"
      style={{ pointerEvents: 'none' }}
      frameloop="demand"
      dpr={dpr}
      camera={{ position: [0, 0, 6], fov: 42, near: 0.1, far: 60 }}
      gl={{
        antialias: true,
        alpha: false,
        // The frozen state relies on the last frame staying on screen after we
        // stop drawing — keep the buffer rather than trusting the compositor.
        preserveDrawingBuffer: true,
        powerPreference: 'low-power',
        failIfMajorPerformanceCaveat: false,
      }}
    >
      <color attach="background" args={['#04030f']} />
      <group ref={rootRef}>
        <EyeScene drive={drive} still={!running} />
      </group>
      <FitToBox target={rootRef} />
      <FrameDriver running={running} fps={fps} />
    </Canvas>
  );
}
