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

/** Can this deployment offer that mode at all?
 *
 * LIVE and UNI are separate PROCESSES: the only way into the other realm is navigating to
 * its map, so a realm with no map is a realm this monitor cannot offer. The ControlBar used
 * to fall back to a plain button in that case, and `handleModeChange` refuses cross-realm
 * switches in-process — so the button was rendered, clicked, and did nothing at all
 * (independentai.network's live map, whose UNI subdomain has no process behind it).
 *
 * TEST is different and stays available everywhere: a test-mode process has no realm of its
 * own (`realm_links` tells it nothing), and its LIVE/UNI toggles are in-process overlays
 * rather than doors to another map.
 */
export function realmModeAvailable(target: MonitorMode, links: RealmLinks | null): boolean {
  if (target === 'test') return true;
  const realm = links?.realm;
  if (!realm) return true;
  const own: MonitorMode = realm === 'live' ? 'real' : 'universe';
  if (target === own) return true;
  return Boolean(otherRealmMapUrl(target, links));
}
