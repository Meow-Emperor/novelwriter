import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import { ProseWarningsPanel } from '@/components/generation/ProseWarningsPanel'
import type { ProseWarning } from '@/types/api'

function renderPanel(warnings: ProseWarning[]) {
  return render(
    <UiLocaleProvider>
      <ProseWarningsPanel warnings={warnings} />
    </UiLocaleProvider>,
  )
}

describe('ProseWarningsPanel', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.lang = 'zh-CN'
    delete document.documentElement.dataset.uiLocale
  })

  it('stays hidden when there are no warnings', () => {
    const { container } = renderPanel([])
    expect(container).toBeEmptyDOMElement()
  })

  it('renders grouped warnings with translated messages and version badges', async () => {
    const user = userEvent.setup()
    const warnings: ProseWarning[] = [
      {
        code: 'repeated_ngram',
        message: 'fallback repeated',
        message_key: 'continuation.prosecheck.warning.repeated_ngram',
        message_params: { phrase: '雾气翻涌', count: 3 },
        version: 1,
        evidence: '雾气翻涌，雾气翻涌，雾气翻涌。',
      },
      {
        code: 'repeated_ngram',
        message: 'fallback repeated second',
        message_key: 'continuation.prosecheck.warning.repeated_ngram',
        message_params: { phrase: '剑光如雪', count: 3 },
        version: 2,
        evidence: '剑光如雪，剑光如雪，剑光如雪。',
      },
      {
        code: 'summary_tone',
        message: 'fallback summary',
        message_key: 'continuation.prosecheck.warning.summary_tone',
        message_params: { phrase: '总之' },
        version: 2,
        evidence: '总之，这一战到此为止。',
      },
    ]

    renderPanel(warnings)

    expect(screen.getByRole('button', { name: '文本质量检查（3 项提示）' })).toBeInTheDocument()
    expect(screen.queryByText('检测到重复短语“雾气翻涌”（出现 3 次）')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '文本质量检查（3 项提示）' }))

    expect(screen.getByText('重复短语')).toBeInTheDocument()
    expect(screen.getByText('总结式语气')).toBeInTheDocument()
    expect(screen.getByText('检测到重复短语“雾气翻涌”（出现 3 次）')).toBeInTheDocument()
    expect(screen.getByText('检测到总结/分析式表达“总之”，可能不适合正文叙事')).toBeInTheDocument()
    expect(screen.getByText('候选 1')).toBeInTheDocument()
    expect(screen.getAllByText('候选 2')).toHaveLength(2)
    expect(screen.getByText('雾气翻涌，雾气翻涌，雾气翻涌。')).toBeInTheDocument()
  })

  it('renders descriptor-first warning copy in English when the UI locale is en', async () => {
    const user = userEvent.setup()
    localStorage.setItem('novwr_ui_locale', 'en')
    document.documentElement.lang = 'en'

    const warnings: ProseWarning[] = [
      {
        code: 'repeated_ngram',
        message: 'fallback repeated',
        message_key: 'continuation.prosecheck.warning.repeated_ngram',
        message_params: { phrase: 'silver rain', count: 2 },
        version: 1,
        evidence: 'silver rain, silver rain',
      },
    ]

    renderPanel(warnings)

    await user.click(screen.getByRole('button', { name: 'Prose quality check (1 issue)' }))

    expect(screen.getByText('Repeated phrase')).toBeInTheDocument()
    expect(screen.getByText('Repeated phrase "silver rain" detected (2 times)')).toBeInTheDocument()
    expect(screen.getByText('Candidate 1')).toBeInTheDocument()
  })

})
