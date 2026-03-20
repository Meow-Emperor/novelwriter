import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import { WorldGenerationDialog } from '@/components/world-model/shared/WorldGenerationDialog'
import { ApiError } from '@/services/api'

const mockUseGenerateWorld = vi.fn()
const mockUseImportWorldpack = vi.fn()
const navigateMock = vi.fn()

vi.mock('@/hooks/world/useWorldGeneration', () => ({
  useGenerateWorld: (...args: unknown[]) => mockUseGenerateWorld(...args),
}))

vi.mock('@/hooks/world/useWorldpack', () => ({
  useImportWorldpack: (...args: unknown[]) => mockUseImportWorldpack(...args),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => navigateMock,
  }
})

function renderDialog() {
  return render(
    <MemoryRouter>
      <UiLocaleProvider>
        <WorldGenerationDialog novelId={7} open onOpenChange={vi.fn()} />
      </UiLocaleProvider>
    </MemoryRouter>,
  )
}

describe('WorldGenerationDialog', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
    document.documentElement.lang = 'zh-CN'
    mockUseGenerateWorld.mockReturnValue({ mutate: vi.fn(), isPending: false })
    mockUseImportWorldpack.mockReturnValue({ mutate: vi.fn(), isPending: false })
    navigateMock.mockReset()
  })

  it('renders LLM failures in English when the UI locale is en', async () => {
    localStorage.setItem('novwr_ui_locale', 'en')
    document.documentElement.lang = 'en'
    const mutate = vi.fn((_payload, options) => {
      options?.onError?.(
        new ApiError(503, 'HTTP 503', {
          code: 'world_generate_llm_unavailable',
          detail: { code: 'world_generate_llm_unavailable' },
        }),
      )
    })
    mockUseGenerateWorld.mockReturnValue({ mutate, isPending: false })

    renderDialog()

    await userEvent.type(screen.getByTestId('world-gen-text'), 'Enough setting text to trigger world generation.')
    await userEvent.click(screen.getByTestId('world-gen-submit'))

    expect(await screen.findByTestId('world-gen-error')).toHaveTextContent(
      'The current model is unavailable. Check that Base URL, API Key, and Model match and that the endpoint supports JSON mode.',
    )
  })

  it('uses worldpack-specific failure copy for import request errors', async () => {
    localStorage.setItem('novwr_ui_locale', 'en')
    document.documentElement.lang = 'en'
    const mutate = vi.fn((_payload, options) => {
      options?.onError?.(new Error('import failed'))
    })
    mockUseImportWorldpack.mockReturnValue({ mutate, isPending: false })

    const { container } = renderDialog()
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement | null
    expect(fileInput).not.toBeNull()

    const file = new File(
      [JSON.stringify({ schema_version: 'worldpack.v1', pack_name: 'Atlas seed' })],
      'worldpack.json',
      { type: 'application/json' },
    )
    Object.defineProperty(file, 'text', {
      configurable: true,
      value: vi.fn().mockResolvedValue(JSON.stringify({ schema_version: 'worldpack.v1', pack_name: 'Atlas seed' })),
    })

    await userEvent.upload(fileInput!, file)

    await waitFor(() => {
      expect(screen.getByText('Worldpack import failed. Please try again.')).toBeTruthy()
    })
  })
})
