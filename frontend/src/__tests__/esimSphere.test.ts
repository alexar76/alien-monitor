import { describe, expect, it } from 'vitest';
import type { EcoNode } from '../App';
import { esimSphere } from '../lib/esimOperator';

const op = (esim: EcoNode['esim'], metrics: Record<string, number> = {}): EcoNode => ({
  id: 'x', label: 'x', group: 'esim_operator', icon: 'esim', description: '', metrics, status: 'active',
  position: { x: 0, y: 0, z: 0 }, esim,
});

describe('an eSIM operator sphere is its own', () => {
  it('grows with the reach of its catalogue, gently, and never past the cap', () => {
    const small = esimSphere(op({ countries: 10 })).size;
    const big = esimSphere(op({ countries: 205 })).size;
    expect(big).toBeGreaterThan(small);
    expect(big).toBeLessThanOrEqual(0.58);
    expect(esimSphere(op({ countries: 100000 })).size).toBe(0.58);
    expect(esimSphere(op({}, { countries: 205 })).size).toBe(big);
  });

  it('a seller shines, a demo is dimmed, a silent node sits between', () => {
    const selling = esimSphere(op({ demo: false }));
    const demo = esimSphere(op({ demo: true }));
    const silent = esimSphere(op({}));
    expect(selling.mode).toBe('selling');
    expect(demo.mode).toBe('demo');
    expect(silent.mode).toBe('unknown');
    expect(selling.glow).toBe(1);
    expect(demo.glow).toBeLessThan(silent.glow);
    expect(silent.glow).toBeLessThan(selling.glow);
  });

  it('an unknown reach is not drawn as no reach', () => {
    expect(esimSphere(op({ countries: null })).size).toBe(0.3);
    expect(esimSphere(op({ countries: Number.NaN })).size).toBe(0.3);
  });
});
