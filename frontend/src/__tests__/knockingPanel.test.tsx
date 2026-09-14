import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { I18nProvider } from '../i18n';
import KnockingPanel from '../components/KnockingPanel';
import type { EcoNode } from '../App';

function node(partial: Pick<EcoNode, 'id' | 'label' | 'group'> & Partial<EcoNode>): EcoNode {
  return {
    icon: '',
    description: '',
    metrics: {},
    status: 'pending',
    position: { x: 0, y: 0, z: 0 },
    ...partial,
  };
}

describe('KnockingPanel', () => {
  it('lists asking-in hubs on the live map', () => {
    const stranger = node({
      id: 'pending:https://stranger.example',
      label: 'Stranger Hub',
      group: 'pending_hub',
      url: 'https://stranger.example',
      metrics: { preview_capabilities: 4 },
      detail: { discoverer: 'announce', first_seen: '2026-08-30T12:00:00Z', note: 'Unapproved hub.' },
    });
    render(
      <I18nProvider>
        <KnockingPanel
          nodes={[stranger]}
          live
          themeColor="#00f0ff"
          onClose={() => {}}
          onFocus={() => {}}
        />
      </I18nProvider>,
    );
    expect(screen.getByText('Stranger Hub')).toBeTruthy();
    expect(screen.getByText('https://stranger.example')).toBeTruthy();
    expect(screen.getByRole('button', { name: /show on map/i })).toBeTruthy();
  });

  it('does not invent UNI strangers', () => {
    const stranger = node({
      id: 'pending:https://stranger.example',
      label: 'Stranger Hub',
      group: 'pending_hub',
    });
    render(
      <I18nProvider>
        <KnockingPanel
          nodes={[stranger]}
          live={false}
          themeColor="#00f0ff"
          onClose={() => {}}
          onFocus={() => {}}
        />
      </I18nProvider>,
    );
    expect(screen.queryByText('Stranger Hub')).toBeNull();
    expect(screen.getAllByText(/UNI is sealed/i).length).toBeGreaterThan(0);
  });

  it('focuses the selected knocking hub', () => {
    const stranger = node({
      id: 'pending:https://stranger.example',
      label: 'Stranger Hub',
      group: 'pending_hub',
    });
    const onFocus = vi.fn();
    render(
      <I18nProvider>
        <KnockingPanel
          nodes={[stranger]}
          live
          themeColor="#00f0ff"
          onClose={() => {}}
          onFocus={onFocus}
        />
      </I18nProvider>,
    );
    screen.getByRole('button', { name: /show on map/i }).click();
    expect(onFocus).toHaveBeenCalledWith(stranger);
  });
});
