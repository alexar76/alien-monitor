/**
 * What a node's URL actually is, and therefore what a card may offer to do with it.
 *
 * A node's `url` is whatever the thing published about itself, and for a provider that is
 * its INVOKE endpoint — `https://hunt.modelmarket.dev/provider/invoke`. The card offered it
 * as "open ↗", and clicking it in a browser returns `{"detail":"Not Found"}`, because a POST
 * endpoint is not a page. An address you can copy into an agent and an address you can open
 * in a tab are different things, and the card has to stop conflating them.
 */

export type NodeUrlKind = 'page' | 'endpoint';

export interface NodeUrlInfo {
  kind: NodeUrlKind;
  /** The address itself, as published. */
  href: string;
  /** Scheme + host (+ port) — the part a human can actually open. */
  origin: string;
}

/**
 * Paths that are machine surfaces. Matched on the path only: the host says nothing about
 * whether a URL renders (`hunt.modelmarket.dev` serves both a landing page and an API).
 */
const ENDPOINT_PATTERNS: RegExp[] = [
  /(^|\/)invoke\/?$/i,
  /(^|\/)ai-market(\/|$)/i,
  /(^|\/)\.well-known(\/|$)/i,
  /(^|\/)api(\/|$)/i,
  /(^|\/)mcp\/?$/i,
  /(^|\/)manifest\/?$/i,
  /\.json$/i,
];

export function classifyNodeUrl(raw: string | null | undefined): NodeUrlInfo | null {
  const text = String(raw ?? '').trim();
  if (!text) return null;
  let parsed: URL;
  try {
    parsed = new URL(text);
  } catch {
    // Not an absolute URL — nothing safe to derive an origin from, so treat it as opaque
    // text the reader may copy but must not be invited to open.
    return { kind: 'endpoint', href: text, origin: '' };
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    return { kind: 'endpoint', href: text, origin: '' };
  }
  const path = parsed.pathname.replace(/\/+$/, '');
  const isEndpoint = ENDPOINT_PATTERNS.some((re) => re.test(path));
  return {
    kind: isEndpoint ? 'endpoint' : 'page',
    href: text,
    origin: parsed.origin,
  };
}

/** Is this address something a card may offer to open in a browser tab? */
export function isOpenableUrl(raw: string | null | undefined): boolean {
  return classifyNodeUrl(raw)?.kind === 'page';
}

/**
 * The address a reader can actually open for this node, or '' when there is none.
 *
 * For an endpoint that is the site behind it — the operator's page at that host — and never
 * the endpoint itself. An origin equal to the endpoint means the URL was already a bare
 * host and the classification above found an endpoint path on it, which cannot happen; the
 * guard is there so a future pattern change cannot start handing back a 404 again.
 */
export function openableFor(raw: string | null | undefined): string {
  const info = classifyNodeUrl(raw);
  if (!info) return '';
  if (info.kind === 'page') return info.href;
  if (!info.origin) return '';
  return info.origin === info.href.replace(/\/+$/, '') ? '' : info.origin;
}
