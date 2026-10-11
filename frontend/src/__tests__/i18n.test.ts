import { describe, it, expect } from 'vitest';
import en from '../i18n/locales/en.json';
import ru from '../i18n/locales/ru.json';
import es from '../i18n/locales/es.json';
import fr from '../i18n/locales/fr.json';
import zh from '../i18n/locales/zh.json';
import { LOCALES } from '../i18n/types';

function resolve(dict: Record<string, unknown>, path: string): string | undefined {
  const parts = path.split('.');
  let cur: unknown = dict;
  for (const part of parts) {
    if (cur == null || typeof cur !== 'object') return undefined;
    cur = (cur as Record<string, unknown>)[part];
  }
  return typeof cur === 'string' ? cur : undefined;
}

describe('i18n catalogs', () => {
  it('defines all five ecosystem locales', () => {
    // fr and zh were added to the catalogs without updating this expectation, so
    // the suite has been red since — the assertion, not the locales, was wrong.
    expect(LOCALES).toEqual(['en', 'ru', 'es', 'fr', 'zh']);
  });

  it('all locales have core UI keys', () => {
    const keys = [
      'app.title',
      'app.connecting',
      'mode.simulation',
      'controls.test',
      'ai.title',
      'ai.welcome',
      'activity.title',
      'tick',
    ];
    for (const catalog of [en, ru, es]) {
      for (const key of keys) {
        expect(resolve(catalog as Record<string, unknown>, key)).toBeTruthy();
      }
    }
  });

  it('interpolates tick counter', () => {
    const template = resolve(en as Record<string, unknown>, 'tick')!;
    const rendered = template.replace(/\{\{(\w+)\}\}/g, (_, k) => (k === 'n' ? '42' : ''));
    expect(rendered).toBe('TICK #42');
  });

  it('every locale warns that the panel is on a different chain than advertised', () => {
    // The banner and the badge are the only places a viewer learns WHICH chain's rows these
    // are, so a locale missing either key silently drops that for its readers.
    for (const catalog of [en, ru, es, fr, zh]) {
      const msg = resolve(catalog as Record<string, unknown>, 'scanner.mismatch');
      expect(msg).toBeTruthy();
      for (const v of ['{{observed}}', '{{declared}}', '{{chain}}']) {
        expect(msg).toContain(v);
      }
      expect(resolve(catalog as Record<string, unknown>, 'scanner.showing')).toBeTruthy();
      expect(resolve(catalog as Record<string, unknown>, 'scanner.uniFallback')).toBeTruthy();
    }
  });

  it('ru and es differ from en for welcome', () => {
    expect(resolve(ru as Record<string, unknown>, 'ai.welcome')).not.toBe(
      resolve(en as Record<string, unknown>, 'ai.welcome'),
    );
    expect(resolve(es as Record<string, unknown>, 'ai.welcome')).not.toBe(
      resolve(en as Record<string, unknown>, 'ai.welcome'),
    );
  });
});
