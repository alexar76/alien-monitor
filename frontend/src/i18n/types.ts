export const LOCALES = ['en', 'ru', 'es', 'fr', 'zh'] as const;
export type Locale = (typeof LOCALES)[number];

export const LOCALE_LABELS: Record<Locale, string> = {
  en: 'EN',
  ru: 'RU',
  es: 'ES',
  fr: 'FR',
  zh: '中文',
};

export type TranslationDict = Record<string, unknown>;
