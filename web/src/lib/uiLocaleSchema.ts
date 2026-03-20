export const SUPPORTED_UI_LOCALES = ['zh', 'en'] as const

export type UiLocale = (typeof SUPPORTED_UI_LOCALES)[number]

export const DEFAULT_UI_LOCALE: UiLocale = 'zh'

type UiLocaleDefinition = {
  aliases: readonly string[]
  documentLang: string
  intlLocale: string
  fallbackChain: readonly UiLocale[]
}

const UI_LOCALE_DEFINITIONS = {
  zh: {
    aliases: ['zh', 'zh-cn', 'zh-hans', 'zh-sg'],
    documentLang: 'zh-CN',
    intlLocale: 'zh-CN',
    fallbackChain: ['zh'],
  },
  en: {
    aliases: ['en', 'en-us', 'en-gb', 'en-ca', 'en-au'],
    documentLang: 'en',
    intlLocale: 'en-US',
    fallbackChain: ['en', 'zh'],
  },
} as const satisfies Record<UiLocale, UiLocaleDefinition>

const UI_LOCALE_ALIAS_MAP = Object.entries(UI_LOCALE_DEFINITIONS).reduce<Record<string, UiLocale>>(
  (acc, [locale, definition]) => {
    const supportedLocale = locale as UiLocale
    for (const alias of definition.aliases) {
      acc[alias] = supportedLocale
    }
    acc[supportedLocale] = supportedLocale
    return acc
  },
  {},
)

function normalizeUiLocaleTag(value: string | null | undefined): string | null {
  const normalized = (value ?? '').trim().toLowerCase().replace(/_/g, '-')
  return normalized || null
}

export function parseUiLocale(value: string | null | undefined): UiLocale | null {
  const normalized = normalizeUiLocaleTag(value)
  if (!normalized) return null

  const exactMatch = UI_LOCALE_ALIAS_MAP[normalized]
  if (exactMatch) return exactMatch

  const base = normalized.split('-', 1)[0]?.trim()
  if (!base) return null
  return UI_LOCALE_ALIAS_MAP[base] ?? null
}

export function getUiLocaleDocumentLang(locale: UiLocale): string {
  return UI_LOCALE_DEFINITIONS[locale].documentLang
}

export function getUiLocaleIntlLocale(locale: UiLocale): string {
  return UI_LOCALE_DEFINITIONS[locale].intlLocale
}

export function getUiLocaleFallbackChain(locale: UiLocale): readonly UiLocale[] {
  const chain = [...UI_LOCALE_DEFINITIONS[locale].fallbackChain, DEFAULT_UI_LOCALE]
  return [...new Set(chain)]
}
