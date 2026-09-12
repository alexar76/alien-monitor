/**
 * UNI fixtures — what the panel PUTS ON SCREEN for a hub the scenario invented.
 *
 * The backend test (alien-monitor/tests/test_universe_hub_spawner.py) proves the spawner stops
 * handing out a loopback address and two literal metrics. This proves the panel cannot put them
 * back: the badge is painted, and an address on a simulated node is refused even if some other
 * producer hands one over. A reader believes pixels, not JSON.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { EcoNode } from '../App';
import { I18nProvider } from '../i18n';
import NodeDetail from '../components/NodeDetail';

vi.mock('../components/OraclePrimitive3D', () => ({ default: () => null }));
vi.mock('../components/MetisChat', () => ({ default: () => null }));

function hubNode(extra: Partial<EcoNode> = {}): EcoNode {
  return {
    id: 'federated_quantum_bridge',
    label: 'Quantum Bridge',
    group: 'network',
    icon: 'globe',
    description: 'Federated hub: 3 capabilities',
    metrics: { capabilities: 3 },
    status: 'active',
    position: { x: 1, y: 2, z: 3 },
    ...extra,
  } as EcoNode;
}

function paint(node: EcoNode) {
  return render(
    <I18nProvider>
      <NodeDetail node={node} onClose={() => {}} themeColor="#00f0ff" />
    </I18nProvider>,
  );
}

describe('a simulated node in the panel', () => {
  it('is labelled, with the reason', () => {
    paint(hubNode({ simulated: true, simulated_note: 'UNI scenario fixture — no service answers' }));
    expect(screen.getByTestId('node-simulated-badge').textContent).toMatch(/simulated/i);
    expect(screen.getByTestId('node-simulated-note').textContent).toBeTruthy();
  });

  it('never shows an address, even when one is handed to it', () => {
    // The live case: `internal address http://127.0.0.1:9088`, a port nothing listens on.
    paint(
      hubNode({
        simulated: true,
        url_internal: 'http://127.0.0.1:9088',
        source_url: 'http://127.0.0.1:9088',
      }),
    );
    expect(screen.queryByTestId('node-internal-address')).toBeNull();
    expect(screen.queryByTestId('node-source-address')).toBeNull();
    expect(screen.queryByText(/127\.0\.0\.1:9088/)).toBeNull();
  });

  it('leaves a polled node alone — no badge, address intact', () => {
    paint(hubNode({ url_internal: 'http://127.0.0.1:9083' }));
    expect(screen.queryByTestId('node-simulated-badge')).toBeNull();
    expect(screen.queryByTestId('node-simulated-note')).toBeNull();
    expect(screen.getByTestId('node-internal-address').textContent).toMatch(/127\.0\.0\.1:9083/);
  });
});
