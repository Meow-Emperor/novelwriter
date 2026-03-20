import { describe, expect, it, vi } from 'vitest'

describe('route-scoped ui message packs', () => {
  it('does not eagerly register legal copy through the root locale provider module', async () => {
    vi.resetModules()

    await import('@/contexts/UiLocaleContext')
    const { translateUiMessage } = await import('@/lib/uiMessages')

    const termsTitleKey = 'terms.title' as Parameters<typeof translateUiMessage>[1]

    expect(translateUiMessage('en', termsTitleKey)).toBe('[missing:terms.title]')

    await import('@/lib/uiMessagePacks/legal')

    expect(translateUiMessage('en', termsTitleKey)).toBe('Terms of use')
  })
})
