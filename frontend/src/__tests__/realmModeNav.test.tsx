import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { I18nProvider } from '../i18n';
import ControlBar from '../components/ControlBar';
import { otherRealmMapUrl, paintedMonitorMode } from '../lib/realmModeNav';

const uniLinks = {
  realm: 'uni' as const,
  hub_url: 'https://uni.modelmarket.dev',
  other: { realm: 'live' as const, map_url: '/monitor-live/' },
};

const liveLinks = {
  realm: 'live' as const,
  other: { realm: 'uni' as const, map_url: '/monitor/' },
};

describe('paintedMonitorMode', () => {
  it('does not paint LIVE on the universe process', () => {
    expect(paintedMonitorMode('real', uniLinks)).toBe('universe');
    expect(paintedMonitorMode('universe', uniLinks)).toBe('universe');
  });

  it('keeps TEST as a local overlay', () => {
    expect(paintedMonitorMode('test', uniLinks)).toBe('test');
    expect(paintedMonitorMode('test', liveLinks)).toBe('test');
  });
});

describe('otherRealmMapUrl', () => {
  it('sends LIVE off the universe map', () => {
    expect(otherRealmMapUrl('real', uniLinks)).toBe('/monitor-live/');
    expect(otherRealmMapUrl('universe', uniLinks)).toBeNull();
  });

  it('sends UNI off the live map', () => {
    expect(otherRealmMapUrl('universe', liveLinks)).toBe('/monitor/');
    expect(otherRealmMapUrl('real', liveLinks)).toBeNull();
  });
});

const barProps = {
  theme: 'cyan' as const,
  onThemeChange: () => {},
  showAI: false,
  onToggleAI: () => {},
  showReputation: false,
  onToggleReputation: () => {},
  showTx: false,
  onToggleTx: () => {},
  showKnocking: false,
  onToggleKnocking: () => {},
  knockingCount: 0,
  pulseIntensity: 1,
  onPulseChange: () => {},
  themeColor: '#00f0ff',
};

describe('ControlBar LIVE/UNI on the universe map', () => {
  it('LIVE is a link to the live map, not a paint job', () => {
    render(
      <I18nProvider>
        <ControlBar
          mode="universe"
          onModeChange={() => {}}
          realmLinks={uniLinks}
          {...barProps}
        />
      </I18nProvider>,
    );
    const live = screen.getByRole('link', { name: 'LIVE' });
    expect(live.getAttribute('href')).toBe('/monitor-live/');
    expect(screen.queryByRole('button', { name: 'LIVE' })).toBeNull();
    expect(screen.getByRole('button', { name: 'UNI' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'KNOCKS' })).toBeTruthy();
  });
});
