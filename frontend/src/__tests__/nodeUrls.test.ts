import { describe, expect, it } from 'vitest';
import { classifyNodeUrl, isOpenableUrl, openableFor } from '../lib/nodeUrls';

describe('classifyNodeUrl', () => {
  it('knows an invoke endpoint is not a page', () => {
    // The live case: the Signal Hunt provider card offered this as "open ↗" and the
    // browser answered {"detail":"Not Found"}.
    const info = classifyNodeUrl('https://hunt.modelmarket.dev/provider/invoke');
    expect(info).toEqual({
      kind: 'endpoint',
      href: 'https://hunt.modelmarket.dev/provider/invoke',
      origin: 'https://hunt.modelmarket.dev',
    });
    expect(isOpenableUrl('https://hunt.modelmarket.dev/provider/invoke')).toBe(false);
  });

  it.each([
    'https://x.example/ai-market/v2/manifest',
    'https://x.example/.well-known/ai-market.json',
    'https://x.example/api/health',
    'https://x.example/mcp',
    'https://x.example/invoke',
    'https://x.example/manifest',
    'https://x.example/prices.json',
  ])('treats %s as a machine surface', (url) => {
    expect(isOpenableUrl(url)).toBe(false);
  });

  it.each([
    'https://hunt.modelmarket.dev',
    'https://independentai.network/hub',
    'https://oracles.modelmarket.dev/family',
    'https://magic-ai-factory.com/agents',
    'https://modelmarket.dev/studio',
  ])('leaves %s openable', (url) => {
    expect(isOpenableUrl(url)).toBe(true);
  });

  it('offers the site behind an endpoint, never the endpoint', () => {
    expect(openableFor('https://hunt.modelmarket.dev/provider/invoke')).toBe(
      'https://hunt.modelmarket.dev',
    );
    expect(openableFor('https://x.example/ai-market/v2/invoke')).toBe('https://x.example');
  });

  it('passes a page through unchanged', () => {
    expect(openableFor('https://hunt.modelmarket.dev')).toBe('https://hunt.modelmarket.dev');
  });

  it('never invites you to open something it cannot parse', () => {
    // A relative path, a mailto:, an empty string — copyable at most.
    for (const raw of ['/provider/invoke', 'mailto:a@b.example', 'not a url', '']) {
      expect(isOpenableUrl(raw)).toBe(false);
      expect(openableFor(raw)).toBe('');
    }
    expect(classifyNodeUrl(null)).toBeNull();
    expect(classifyNodeUrl(undefined)).toBeNull();
  });

  it('reads a trailing slash the same as none', () => {
    expect(isOpenableUrl('https://hunt.modelmarket.dev/provider/invoke/')).toBe(false);
    expect(isOpenableUrl('https://hunt.modelmarket.dev/')).toBe(true);
  });
});
