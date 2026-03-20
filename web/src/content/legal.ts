import { getUiLocaleIntlLocale } from '@/lib/uiLocale'
import type { UiLocale } from '@/lib/uiMessages'

export const LEGAL_LAST_UPDATED_AT = '2026-03-06'

const configuredEmail = (import.meta.env.VITE_LEGAL_CONTACT_EMAIL ?? '').trim()

export const LEGAL_CONTACT_EMAIL = configuredEmail

export function getLegalContactHref(): string | undefined {
  return configuredEmail ? `mailto:${configuredEmail}` : undefined
}

export function formatLegalLastUpdated(locale: UiLocale): string {
  const formatter = new Intl.DateTimeFormat(getUiLocaleIntlLocale(locale), {
    dateStyle: 'long',
    timeZone: 'UTC',
  })
  return formatter.format(new Date(`${LEGAL_LAST_UPDATED_AT}T00:00:00Z`))
}
