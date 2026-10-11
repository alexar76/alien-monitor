import { useEffect, useRef } from 'react';
import * as THREE from 'three';

/**
 * Signal Hunt thumbnail — compact port of signal-hunt/FederationField.tsx
 * (icosa core + orbital rings + peer nodes + pulses). Same visual language as
 * hunt.modelmarket.dev, sized for the monitor card slot.
 */

type Peer = { id: string; caps: number; hue: number };

const DEFAULT_PEERS: Peer[] = [
  { id: 'primary', caps: 53, hue: 190 },
  { id: 'lab', caps: 53, hue: 28 },
  { id: 'hunt', caps: 58, hue: 320 },
  { id: 'oracles', caps: 42, hue: 265 },
];

function glowTexture(inner: string, middle: string): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = 128;
  canvas.height = 128;
  const ctx = canvas.getContext('2d')!;
  const g = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
  g.addColorStop(0, inner);
  g.addColorStop(0.2, middle);
  g.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 128, 128);
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

export default function SignalHuntField({
  accent = '#ff5ec8',
  mobile = false,
}: {
  accent?: string;
  mobile?: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x03040a, 0.06);
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 40);
    camera.position.set(0, 0.35, mobile ? 9.2 : 8.2);
    camera.lookAt(0, 0, 0);

    const renderer = new THREE.WebGLRenderer({
      antialias: !mobile,
      alpha: true,
      powerPreference: 'high-performance',
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, mobile ? 1.25 : 1.75));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.domElement.style.width = '100%';
    renderer.domElement.style.height = '100%';
    renderer.domElement.style.display = 'block';
    el.appendChild(renderer.domElement);

    const world = new THREE.Group();
    scene.add(world);
    scene.add(new THREE.AmbientLight(0x304068, 1.1));
    const accentCol = new THREE.Color(accent);
    const accentLight = new THREE.PointLight(accentCol.getHex(), 28, 20, 1.4);
    accentLight.position.set(2.4, 2.8, 3.5);
    scene.add(accentLight);
    const cyanLight = new THREE.PointLight(0x35e7ff, 22, 18, 1.5);
    cyanLight.position.set(-3.5, -1.5, 1.5);
    scene.add(cyanLight);

    const cyanGlow = glowTexture('rgba(255,255,255,1)', 'rgba(38,236,255,.86)');
    const roseGlow = glowTexture('rgba(255,255,255,.9)', 'rgba(255,70,200,.7)');

    const core = new THREE.Group();
    world.add(core);
    core.add(
      new THREE.Mesh(
        new THREE.IcosahedronGeometry(0.85, 3),
        new THREE.MeshStandardMaterial({
          color: 0x075b86,
          emissive: 0x0acfee,
          emissiveIntensity: 1.6,
          roughness: 0.25,
          metalness: 0.35,
          transparent: true,
          opacity: 0.85,
        }),
      ),
    );
    core.add(
      new THREE.Mesh(
        new THREE.IcosahedronGeometry(1.05, 1),
        new THREE.MeshBasicMaterial({
          color: 0x86f8ff,
          wireframe: true,
          transparent: true,
          opacity: 0.55,
          blending: THREE.AdditiveBlending,
        }),
      ),
    );
    const aura = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: cyanGlow,
        transparent: true,
        opacity: 0.7,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    );
    aura.scale.set(3.8, 3.8, 1);
    core.add(aura);

    const rings: THREE.Mesh[] = [];
    [1.4, 1.95, 2.55].forEach((r, i) => {
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(r, i === 0 ? 0.012 : 0.007, 6, 96),
        new THREE.MeshBasicMaterial({
          color: i % 2 ? accentCol.getHex() : 0x41eaff,
          transparent: true,
          opacity: 0.28 + i * 0.04,
          blending: THREE.AdditiveBlending,
        }),
      );
      ring.rotation.set(0.55 + i * 0.3, 0.2 + i * 0.25, i * 0.6);
      rings.push(ring);
      world.add(ring);
    });

    const peers = DEFAULT_PEERS;
    const nodes: { group: THREE.Group; base: THREE.Vector3; phase: number }[] = [];
    peers.forEach((p, index) => {
      const phase = (index / peers.length) * Math.PI * 2 + 0.4;
      const radius = 2.55 + (index % 2) * 0.35;
      const base = new THREE.Vector3(
        Math.cos(phase) * radius,
        Math.sin(phase * 1.4) * 1.1,
        Math.sin(phase) * radius * 0.45,
      );
      const size = 0.18 + Math.sqrt(p.caps) * 0.035;
      const color = new THREE.Color().setHSL(p.hue / 360, 0.88, 0.58);
      const g = new THREE.Group();
      g.position.copy(base);
      world.add(g);
      g.add(
        new THREE.Mesh(
          new THREE.IcosahedronGeometry(size, 1),
          new THREE.MeshStandardMaterial({
            color,
            emissive: color,
            emissiveIntensity: 1.0,
            roughness: 0.3,
            metalness: 0.25,
          }),
        ),
      );
      g.add(
        new THREE.Mesh(
          new THREE.IcosahedronGeometry(size * 1.15, 0),
          new THREE.MeshBasicMaterial({ color, wireframe: true, transparent: true, opacity: 0.65 }),
        ),
      );
      const glow = new THREE.Sprite(
        new THREE.SpriteMaterial({
          map: roseGlow,
          color,
          transparent: true,
          opacity: 0.55,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
        }),
      );
      glow.scale.set(size * 4.2, size * 4.2, 1);
      g.add(glow);
      nodes.push({ group: g, base, phase });

      const bend = base.clone().multiplyScalar(0.5);
      bend.y += index % 2 ? 0.7 : -0.7;
      const curve = new THREE.CatmullRomCurve3([base, bend, new THREE.Vector3()]);
      world.add(
        new THREE.Line(
          new THREE.BufferGeometry().setFromPoints(curve.getPoints(48)),
          new THREE.LineBasicMaterial({
            color,
            transparent: true,
            opacity: 0.28,
            blending: THREE.AdditiveBlending,
          }),
        ),
      );
    });

    const starCount = mobile ? 280 : 480;
    const starPos = new Float32Array(starCount * 3);
    for (let i = 0; i < starCount; i++) {
      const r = 5 + ((i * 47) % 120) / 10;
      const a = i * 2.399963;
      starPos[i * 3] = Math.cos(a) * r;
      starPos[i * 3 + 1] = (((i * 83) % 200) / 100 - 1) * 5;
      starPos[i * 3 + 2] = Math.sin(a) * r;
    }
    const stars = new THREE.Points(
      new THREE.BufferGeometry().setAttribute('position', new THREE.BufferAttribute(starPos, 3)),
      new THREE.PointsMaterial({
        color: 0xa6eaff,
        size: 0.028,
        transparent: true,
        opacity: 0.7,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    );
    scene.add(stars);

    const resize = () => {
      const w = el.clientWidth || 1;
      const h = el.clientHeight || 1;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h, false);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);

    let raf = 0;
    const t0 = performance.now();
    const tick = () => {
      const t = (performance.now() - t0) / 1000;
      if (!reduced) {
        world.rotation.y = t * 0.12;
        core.rotation.y = t * 0.35;
        core.rotation.x = Math.sin(t * 0.4) * 0.08;
        rings.forEach((ring, i) => {
          ring.rotation.z += 0.002 + i * 0.0008;
        });
        nodes.forEach((n, i) => {
          const bob = Math.sin(t * 1.2 + n.phase) * 0.08;
          n.group.position.set(n.base.x, n.base.y + bob, n.base.z);
          n.group.rotation.y = t * (0.4 + i * 0.05);
        });
        stars.rotation.y = t * 0.02;
      }
      renderer.render(scene, camera);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer.dispose();
      if (renderer.domElement.parentNode === el) el.removeChild(renderer.domElement);
      cyanGlow.dispose();
      roseGlow.dispose();
    };
  }, [accent, mobile]);

  return <div ref={host} className="absolute inset-0" />;
}
