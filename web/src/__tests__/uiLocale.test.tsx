import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { UiLocaleProvider, useUiLocale } from '@/contexts/UiLocaleContext'
import {
  getUiLocaleFallbackChain,
  parseUiLocale,
  resolveInitialUiLocale,
  UI_LOCALE_STORAGE_KEY,
} from '@/lib/uiLocale'
import { translateUiMessage, uiMessages, type UiMessageKey } from '@/lib/uiMessages'

function LocaleProbe() {
  const { locale, setLocale, t } = useUiLocale()

  return (
    <div>
      <div data-testid="locale">{locale}</div>
      <div data-testid="title">{t('settings.title')}</div>
      <button type="button" onClick={() => setLocale('en')}>
        switch-en
      </button>
      <button type="button" onClick={() => setLocale('zh')}>
        switch-zh
      </button>
    </div>
  )
}

describe('ui locale foundation', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.lang = 'zh-CN'
    delete document.documentElement.dataset.uiLocale
    vi.restoreAllMocks()
  })

  it('defaults to the existing document locale when no preference is saved', () => {
    expect(resolveInitialUiLocale()).toBe('zh')
  })

  it('prefers the saved locale preference', () => {
    localStorage.setItem(UI_LOCALE_STORAGE_KEY, 'en')
    expect(resolveInitialUiLocale()).toBe('en')
  })

  it('normalizes browser locale tags through the shared locale manifest', () => {
    expect(parseUiLocale('en-US')).toBe('en')
    expect(parseUiLocale('zh_Hans')).toBe('zh')
    expect(parseUiLocale('fr-FR')).toBeNull()
  })

  it('uses the locale manifest fallback chain for translations', () => {
    expect(getUiLocaleFallbackChain('en')).toEqual(['en', 'zh'])
    expect(getUiLocaleFallbackChain('zh')).toEqual(['zh'])
  })

  it('falls back to zh when localStorage.getItem throws', () => {
    document.documentElement.lang = ''
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError')
    })

    expect(resolveInitialUiLocale()).toBe('zh')
  })

  it('syncs document.lang and persists the selected locale across remounts', async () => {
    const user = userEvent.setup()

    const firstRender = render(
      <UiLocaleProvider>
        <LocaleProbe />
      </UiLocaleProvider>,
    )

    expect(screen.getByTestId('locale')).toHaveTextContent('zh')
    expect(screen.getByTestId('title')).toHaveTextContent('设置')
    expect(document.documentElement.lang).toBe('zh-CN')

    await user.click(screen.getByRole('button', { name: 'switch-en' }))

    expect(screen.getByTestId('locale')).toHaveTextContent('en')
    expect(screen.getByTestId('title')).toHaveTextContent('Settings')
    expect(document.documentElement.lang).toBe('en')
    expect(document.documentElement.dataset.uiLocale).toBe('en')
    expect(localStorage.getItem(UI_LOCALE_STORAGE_KEY)).toBe('en')

    firstRender.unmount()

    render(
      <UiLocaleProvider>
        <LocaleProbe />
      </UiLocaleProvider>,
    )

    expect(screen.getByTestId('locale')).toHaveTextContent('en')
    expect(screen.getByTestId('title')).toHaveTextContent('Settings')
  })

  it('falls back to the zh catalog when an en translation is missing', () => {
    const original = uiMessages.en['settings.title']
    delete uiMessages.en['settings.title']

    try {
      expect(translateUiMessage('en', 'settings.title')).toBe('设置')
    } finally {
      uiMessages.en['settings.title'] = original
    }
  })

  it('returns a predictable marker for missing keys', () => {
    expect(translateUiMessage('en', 'missing.demo' as UiMessageKey)).toBe('[missing:missing.demo]')
  })
})
