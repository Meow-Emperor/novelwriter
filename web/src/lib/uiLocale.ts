import type { UiLocale } from '@/lib/uiMessages'

export const DEFAULT_UI_LOCALE: UiLocale = 'zh'
export const UI_LOCALE_STORAGE_KEY = 'novwr_ui_locale'

export function parseUiLocale(value: string | null | undefined): UiLocale | null {
  const normalized = (value ?? '').trim().toLowerCase()
  if (!normalized) return null
  const base = normalized.split(/[-_]/)[0]?.trim()
  if (base === 'zh' || base === 'en') return base
  return null
}

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
  root.lang = locale === 'en' ? 'en' : 'zh-CN'
  root.dataset.uiLocale = locale
}
