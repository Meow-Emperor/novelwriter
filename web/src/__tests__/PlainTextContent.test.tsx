import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import { PlainTextContent } from '@/components/ui/plain-text-content'
import { UI_LOCALE_STORAGE_KEY } from '@/lib/uiLocale'

function renderWithProvider(element: ReactNode) {
  return render(
    <UiLocaleProvider>
      {element}
    </UiLocaleProvider>,
  )
}

describe('PlainTextContent locale defaults', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.lang = 'zh-CN'
    delete document.documentElement.dataset.uiLocale
  })

  it('uses shared English defaults for loading and empty states', () => {
    localStorage.setItem(UI_LOCALE_STORAGE_KEY, 'en')
    document.documentElement.lang = 'en'

    const { rerender } = renderWithProvider(
      <PlainTextContent isLoading content="" />,
    )

    expect(screen.getByText('Loading...')).toBeInTheDocument()

    rerender(
      <UiLocaleProvider>
        <PlainTextContent content="" />
      </UiLocaleProvider>,
    )

    expect(screen.getByText('No content yet')).toBeInTheDocument()
  })

  it('lets explicit labels override shared locale defaults', () => {
    localStorage.setItem(UI_LOCALE_STORAGE_KEY, 'en')
    document.documentElement.lang = 'en'

    renderWithProvider(
      <PlainTextContent isLoading content="" loadingLabel="Custom loading" emptyLabel="Custom empty" />,
    )

    expect(screen.getByText('Custom loading')).toBeInTheDocument()
  })
})
