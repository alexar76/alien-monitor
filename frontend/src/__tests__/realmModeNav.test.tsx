import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { I18nProvider } from '../i18n';
import ControlBar from '../components/ControlBar';
import { otherRealmMapUrl, paintedMonitorMode, realmModeAvailable } from '../lib/realmModeNav';

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
  showScanner: false,
  onToggleScanner: () => {},
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

const liveOnlyLinks = { realm: 'live' as const };          // no bubble on this deployment
const uniOnlyLinks = { realm: 'uni' as const };            // no live map on this one

describe('realmModeAvailable', () => {
  it('offers the realm you are standing in, and the one you can navigate to', () => {
    expect(realmModeAvailable('universe', liveLinks)).toBe(true);
    expect(realmModeAvailable('real', liveLinks)).toBe(true);
    expect(realmModeAvailable('real', uniLinks)).toBe(true);
    expect(realmModeAvailable('universe', uniLinks)).toBe(true);
  });

  it('refuses a realm this deployment does not run', () => {
    expect(realmModeAvailable('universe', liveOnlyLinks)).toBe(false);
    expect(realmModeAvailable('real', liveOnlyLinks)).toBe(true);
    expect(realmModeAvailable('real', uniOnlyLinks)).toBe(false);
    expect(realmModeAvailable('universe', uniOnlyLinks)).toBe(true);
  });

  it('leaves a TEST-mode process both toggles — they are in-process there', () => {
    expect(realmModeAvailable('real', null)).toBe(true);
    expect(realmModeAvailable('universe', null)).toBe(true);
    expect(realmModeAvailable('test', liveOnlyLinks)).toBe(true);
  });
});

describe('ControlBar on a deployment with only one realm', () => {
  const paint = (links: Parameters<typeof realmModeAvailable>[1], mode: 'real' | 'universe') =>
    render(
      <I18nProvider>
        <ControlBar mode={mode} onModeChange={() => {}} realmLinks={links} {...barProps} />
      </I18nProvider>,
    );

  it('does not draw a UNI button when there is no UNI map to reach', () => {
    // The live case: independentai.network's monitor drew UNI, and clicking it did nothing —
    // `handleModeChange` refuses cross-realm switches in-process, so the button could only
    // ever disappoint.
    paint(liveOnlyLinks, 'real');
    expect(screen.queryByTestId('mode-uni')).toBeNull();
    expect(screen.getByTestId('mode-live')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'TEST' })).toBeTruthy();
  });

  it('hides LIVE on a bubble-only deployment, symmetrically', () => {
    paint(uniOnlyLinks, 'universe');
    expect(screen.queryByTestId('mode-live')).toBeNull();
    expect(screen.getByTestId('mode-uni')).toBeTruthy();
  });

  it('still draws both when the other map exists', () => {
    paint(liveLinks, 'real');
    expect(screen.getByTestId('mode-uni').getAttribute('href')).toBe('/monitor/');
    expect(screen.getByTestId('mode-live')).toBeTruthy();
  });
});
