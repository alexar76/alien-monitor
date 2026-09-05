export type MonitorMode = 'test' | 'real' | 'universe';

export type RealmLinks = {
  realm: 'uni' | 'live';
  hub_url?: string;
  other?: { realm: 'uni' | 'live'; map_url: string };
};

/** Paint LIVE/UNI from the process you are on, not from a client toggle. */
export function paintedMonitorMode(mode: MonitorMode, links: RealmLinks | null): MonitorMode {
  if (mode === 'test') return 'test';
  if (links?.realm === 'live') return 'real';
  if (links?.realm === 'uni') return 'universe';
  return mode;
}

/** Cross-realm LIVE/UNI is the other map, not a paint job on this backend. */
export function otherRealmMapUrl(requested: MonitorMode, links: RealmLinks | null): string | null {
  if (!links?.other?.map_url) return null;
  if (requested === 'real' && links.realm === 'uni' && links.other.realm === 'live') {
    return links.other.map_url;
  }
  if (requested === 'universe' && links.realm === 'live' && links.other.realm === 'uni') {
    return links.other.map_url;
  }
  return null;
}
