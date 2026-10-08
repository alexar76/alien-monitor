/**
 * docs/localization-glossary.md as an executable contract.
 *
 * The glossary is the ecosystem's terminology source of truth, and until now it
 * was an agreement nobody could check: the monitor's Spanish said "saldo escrow"
 * where the glossary says «depósito en garantía», its Russian said "trust-скор"
 * where the glossary says «оценка доверия», and its Chinese said 回执 where the
 * glossary row for a signed receipt says 收据. Each on its own is small; together
 * they are five locales drifting apart one string at a time.
 *
 * This test pins the terms that actually appear in the UI. A deliberate change to
 * terminology means editing the glossary AND the expectation below — which is the
 * point: the decision becomes visible in review instead of arriving as a typo.
 */

import { describe, expect, it } from 'vitest';

import en from '../i18n/locales/en.json';
import ru from '../i18n/locales/ru.json';
import es from '../i18n/locales/es.json';
import fr from '../i18n/locales/fr.json';
import zh from '../i18n/locales/zh.json';

type Dict = Record<string, unknown>;
const LOCALES: Record<string, Dict> = { en, ru, es, fr, zh };

function flatten(obj: Dict, prefix = ''): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      Object.assign(out, flatten(v as Dict, key));
    } else {
      out[key] = String(v);
    }
  }
  return out;
}

const FLAT: Record<string, Record<string, string>> = Object.fromEntries(
  Object.entries(LOCALES).map(([loc, d]) => [loc, flatten(d)]),
);

/**
 * One row per term the UI uses, with the glossary form each locale must carry.
 * `forbid` lists the wording this replaced, so a revert fails loudly rather than
 * silently reintroducing the drift.
 */
const GLOSSARY_TERMS: Array<{
  term: string;
  keys: string[];
  require: Partial<Record<'ru' | 'es' | 'fr' | 'zh', string>>;
  forbid?: Partial<Record<'ru' | 'es' | 'fr' | 'zh', string>>;
}> = [
  {
    term: 'escrow',
    keys: ['nodeDetail.metricKeys.escrow_balance'],
    require: { es: 'depósito en garantía', fr: 'séquestre', ru: 'эскроу', zh: '托管' },
    forbid: { es: 'saldo escrow' },
  },
  {
    term: 'receipt (signed receipt of an invoke)',
    keys: ['bridges.counter.receipts_issued', 'bridges.role'],
    require: { ru: 'квитанц', es: 'recibo', fr: 'reçu', zh: '收据' },
    forbid: { zh: '回执' },
  },
  {
    term: 'payment channel',
    keys: ['ai.suggestions.channels'],
    require: { ru: 'платёжны', es: 'canales de pago', fr: 'canaux de paiement', zh: '支付通道' },
  },
  {
    term: 'on-chain',
    keys: ['monitor.prometheusDegraded'],
    require: { ru: 'ончейн', zh: '链上' },
    forbid: { ru: 'on-chain' },
  },
  {
    term: 'wallet',
    keys: ['argus.roster.search'],
    require: { ru: 'кошел', es: 'cartera', fr: 'portefeuille', zh: '钱包' },
  },
  {
    term: 'trust score',
    keys: ['reputation.realTrust'],
    require: { ru: 'оценка доверия', es: 'confianza', fr: 'confiance', zh: '信任分' },
    forbid: { ru: 'trust-скор' },
  },
  {
    term: 'self-hosted',
    keys: ['nodeDetail.desc.skopos'],
    require: { ru: 'на своём сервере', es: 'autoalojad', zh: '自托管' },
    forbid: { ru: 'self-hosted', es: 'self-hosted' },
  },
];

describe('glossary compliance (docs/localization-glossary.md)', () => {
  for (const { term, keys, require: req, forbid } of GLOSSARY_TERMS) {
    for (const [loc, expected] of Object.entries(req)) {
      it(`${loc}: "${term}" uses the glossary form`, () => {
        const haystack = keys.map((k) => FLAT[loc][k] ?? '').join(' ').toLowerCase();
        expect(haystack, `keys ${keys.join(', ')} missing in ${loc}`).not.toBe('');
        expect(haystack).toContain(expected.toLowerCase());
      });
    }
    for (const [loc, banned] of Object.entries(forbid ?? {})) {
      it(`${loc}: "${term}" no longer uses "${banned}"`, () => {
        const haystack = keys.map((k) => FLAT[loc][k] ?? '').join(' ').toLowerCase();
        expect(haystack).not.toContain(banned.toLowerCase());
      });
    }
  }
});

describe('five locales stay in step', () => {
  const enKeys = Object.keys(FLAT.en).sort();

  for (const loc of ['ru', 'es', 'fr', 'zh'] as const) {
    it(`${loc} carries every key and no extras`, () => {
      expect(Object.keys(FLAT[loc]).sort()).toEqual(enKeys);
    });

    it(`${loc} leaves nothing empty`, () => {
      const blank = enKeys.filter((k) => !FLAT[loc][k]?.trim());
      expect(blank, `empty strings in ${loc}`).toEqual([]);
    });

    it(`${loc} is actually translated, not copied from English`, () => {
      // Product names, identifiers and numbers are legitimately identical, so this
      // measures the bulk: a locale that is mostly a copy of en is not a locale.
      const long = enKeys.filter((k) => (FLAT.en[k] ?? '').length > 40);
      const identical = long.filter((k) => FLAT[loc][k] === FLAT.en[k]);
      expect(
        identical.length / Math.max(long.length, 1),
        `${identical.length}/${long.length} long strings in ${loc} are identical to en`,
      ).toBeLessThan(0.1);
    });
  }
});
