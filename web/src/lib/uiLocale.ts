import {
  DEFAULT_UI_LOCALE,
  getUiLocaleDocumentLang,
  getUiLocaleFallbackChain,
  getUiLocaleIntlLocale,
  parseUiLocale,
  SUPPORTED_UI_LOCALES,
  type UiLocale,
} from '@/lib/uiLocaleSchema'

export {
  DEFAULT_UI_LOCALE,
  getUiLocaleDocumentLang,
  getUiLocaleFallbackChain,
  getUiLocaleIntlLocale,
  parseUiLocale,
  SUPPORTED_UI_LOCALES,
  type UiLocale,
}

export const UI_LOCALE_STORAGE_KEY = 'novwr_ui_locale'

export function normalizeUiLocale(
  value: string | null | undefined,
  fallback: UiLocale = DEFAULT_UI_LOCALE,
): UiLocale {
  return parseUiLocale(value) ?? fallback
}

export function readStoredUiLocale(): UiLocale | null {
  if (typeof window === 'undefined') return null
  try {
    return parseUiLocale(localStorage.getItem(UI_LOCALE_STORAGE_KEY))
  } catch {
    return null
  }
}

export function readDocumentUiLocale(): UiLocale | null {
  if (typeof document === 'undefined') return null
  return parseUiLocale(document.documentElement.lang)
}

export function resolveInitialUiLocale(): UiLocale {
  return readStoredUiLocale() ?? readDocumentUiLocale() ?? DEFAULT_UI_LOCALE
}

export function resolveCurrentUiLocale(): UiLocale {
  return readDocumentUiLocale() ?? readStoredUiLocale() ?? DEFAULT_UI_LOCALE
}

export function persistUiLocale(locale: UiLocale): void {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem(UI_LOCALE_STORAGE_KEY, locale)
  } catch {
    // Ignore storage-denied environments; the current tab can still use the locale.
  }
}

export function applyUiLocaleToDocument(locale: UiLocale): void {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  root.lang = getUiLocaleDocumentLang(locale)
  root.dataset.uiLocale = locale
}
