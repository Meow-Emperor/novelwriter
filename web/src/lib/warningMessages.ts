import '@/lib/uiMessagePacks/novel'
import { readDocumentUiLocale } from '@/lib/uiLocale'
import { translateUiMessage, type UiLocale, type UiMessageKey } from '@/lib/uiMessages'

type WarningLike = {
  message: string
  message_key?: string | null
  message_params?: Record<string, string | number | boolean | null> | null
}

function isMissingTranslation(value: string): boolean {
  return value.startsWith('[missing:')
}

export function renderWarningMessage(
  warning: WarningLike,
  locale: UiLocale = readDocumentUiLocale() ?? 'zh',
): string {
  const key = typeof warning.message_key === 'string' ? warning.message_key.trim() : ''
  if (key) {
    const translated = translateUiMessage(
      locale,
      key as UiMessageKey,
      warning.message_params ?? undefined,
    )
    if (!isMissingTranslation(translated)) return translated
  }
  return warning.message
}
