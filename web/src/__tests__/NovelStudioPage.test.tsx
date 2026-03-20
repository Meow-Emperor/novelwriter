import type { ReactNode } from 'react'
import { describe, expect, it, beforeEach, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import { QueryClientProvider } from '@tanstack/react-query'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { NovelShell } from '@/components/novel-shell/NovelShell'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import { NovelStudioPage } from '@/pages/NovelStudioPage'
import { createTestQueryClient } from './helpers'

const mockUseUpdateChapter = vi.fn()
const mockUseCreateChapter = vi.fn()
const mockUseDeleteChapter = vi.fn()
const mockUseWorldEntities = vi.fn()
const mockUseWorldSystems = vi.fn()
const mockUseBootstrapStatus = vi.fn()
const mockUseTriggerBootstrap = vi.fn()
const mockUseDebouncedAutoSave = vi.fn()
const mockUseContinuationSetupState = vi.fn()
const mockReadGenerationResultsDebug = vi.fn()

vi.mock('@/components/layout/PageShell', () => ({
  PageShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/novel-shell/NovelShellLayout', () => ({
  NovelShellLayout: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/novel-shell/NovelShellRail', () => ({
  NovelShellRail: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/novel-shell/ArtifactStage', () => ({
  ArtifactStage: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/detail/ChapterContent', () => ({
  ChapterContent: ({
    content,
    isLoading,
  }: {
    content: string | null
    isLoading: boolean
  }) => <div>{isLoading ? '加载章节中' : content}</div>,
}))

vi.mock('@/components/detail/ChapterEditor', () => ({
  ChapterEditor: () => <div data-testid="chapter-editor" />,
}))

vi.mock('@/components/detail/EmptyWorldOnboarding', () => ({
  EmptyWorldOnboarding: () => <div data-testid="world-onboarding" />,
}))

vi.mock('@/components/world-model/shared/WorldGenerationDialog', () => ({
  WorldGenerationDialog: () => null,
}))

vi.mock('@/components/ui/glass-surface', () => ({
  GlassSurface: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/generation/DriftWarningPopover', () => ({
  DriftWarningPopover: () => null,
}))

vi.mock('@/components/studio/StudioAssistantPanel', () => ({
  StudioAssistantPanel: () => <div data-testid="studio-assistant" />,
}))

vi.mock('@/components/studio/panels/InjectionSummaryPanel', () => ({
  InjectionSummaryPanel: () => <div data-testid="injection-summary-panel" />,
}))

vi.mock('@/components/studio/stages/ContinuationSetupStage', () => ({
  ContinuationSetupStage: () => <div data-testid="continuation-setup" />,
}))

vi.mock('@/components/studio/stages/StudioEntityStage', () => ({
  StudioEntityStage: () => <div data-testid="studio-entity-stage" />,
}))

vi.mock('@/components/studio/stages/StudioDraftReviewStage', () => ({
  StudioDraftReviewStage: () => <div data-testid="studio-review-stage" />,
}))

vi.mock('@/components/studio/stages/StudioRelationshipStage', () => ({
  StudioRelationshipStage: () => <div data-testid="studio-relationship-stage" />,
}))

vi.mock('@/components/studio/stages/StudioSystemStage', () => ({
  StudioSystemStage: () => <div data-testid="studio-system-stage" />,
}))

vi.mock('@/components/studio/stages/ContinuationResultsStage', () => ({
  ContinuationResultsStage: () => <div data-testid="continuation-results-stage" />,
}))

vi.mock('@/components/novel-copilot/NovelCopilotDrawer', () => ({
  NovelCopilotDrawer: () => <div data-testid="novel-copilot-drawer" />,
}))

vi.mock('@/hooks/novel/useUpdateChapter', () => ({
  useUpdateChapter: (...args: unknown[]) => mockUseUpdateChapter(...args),
}))

vi.mock('@/hooks/novel/useCreateChapter', () => ({
  useCreateChapter: (...args: unknown[]) => mockUseCreateChapter(...args),
}))

vi.mock('@/hooks/novel/useDeleteChapter', () => ({
  useDeleteChapter: (...args: unknown[]) => mockUseDeleteChapter(...args),
}))

vi.mock('@/hooks/world/useEntities', () => ({
  useWorldEntities: (...args: unknown[]) => mockUseWorldEntities(...args),
}))

vi.mock('@/hooks/world/useSystems', () => ({
  useWorldSystems: (...args: unknown[]) => mockUseWorldSystems(...args),
}))

vi.mock('@/hooks/world/useBootstrap', () => ({
  useBootstrapStatus: (...args: unknown[]) => mockUseBootstrapStatus(...args),
  useTriggerBootstrap: (...args: unknown[]) => mockUseTriggerBootstrap(...args),
}))

vi.mock('@/hooks/useDebouncedAutoSave', () => ({
  useDebouncedAutoSave: (...args: unknown[]) => mockUseDebouncedAutoSave(...args),
}))

vi.mock('@/hooks/novel/useContinuationSetupState', () => ({
  useContinuationSetupState: (...args: unknown[]) => mockUseContinuationSetupState(...args),
}))

vi.mock('@/lib/generationResultsDebugStorage', () => ({
  readGenerationResultsDebug: (...args: unknown[]) => mockReadGenerationResultsDebug(...args),
}))

vi.mock('@/services/api', () => ({
  api: {
    getNovel: vi.fn(),
    listChaptersMeta: vi.fn(),
    getChapter: vi.fn(),
    listChapters: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    code?: string
  },
}))

import { api } from '@/services/api'

const mockGetNovel = api.getNovel as ReturnType<typeof vi.fn>
const mockListChaptersMeta = api.listChaptersMeta as ReturnType<typeof vi.fn>
const mockGetChapter = api.getChapter as ReturnType<typeof vi.fn>

function LocationProbe() {
  const location = useLocation()
  return (
    <>
      <div data-testid="location-path">{location.pathname}</div>
      <div data-testid="location-search">{location.search}</div>
    </>
  )
}

function renderWithStudioShell(initialEntry: string, routes?: ReactNode) {
  const queryClient = createTestQueryClient()

  return render(
    <QueryClientProvider client={queryClient}>
      <UiLocaleProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          {routes ?? (
            <Routes>
              <Route element={<NovelShell />}>
                <Route path="/novel/:novelId" element={<NovelStudioPage />} />
              </Route>
            </Routes>
          )}
        </MemoryRouter>
      </UiLocaleProvider>
    </QueryClientProvider>,
  )
}

describe('NovelStudioPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()

    mockUseUpdateChapter.mockReturnValue({
      mutate: vi.fn(),
      mutateAsync: vi.fn().mockResolvedValue(undefined),
    })
    mockUseCreateChapter.mockReturnValue({
      isPending: false,
      mutate: vi.fn(),
    })
    mockUseDeleteChapter.mockReturnValue({
      mutate: vi.fn(),
    })
    mockUseWorldEntities.mockReturnValue({
      data: [{ id: 1, name: '主角' }],
      isLoading: false,
    })
    mockUseWorldSystems.mockReturnValue({
      data: [],
      isLoading: false,
    })
    mockUseBootstrapStatus.mockReturnValue({
      data: null,
      isLoading: false,
    })
    mockUseTriggerBootstrap.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    })
    mockUseDebouncedAutoSave.mockReturnValue({
      status: 'idle',
      schedule: vi.fn(),
      flush: vi.fn().mockResolvedValue(undefined),
      saveNow: vi.fn().mockResolvedValue(undefined),
      cancel: vi.fn(),
    })
    mockUseContinuationSetupState.mockReturnValue({
      instruction: '',
      setInstruction: vi.fn(),
      selectedLength: 'medium',
      setSelectedLength: vi.fn(),
      advancedOpen: false,
      setAdvancedOpen: vi.fn(),
      contextChapters: 3,
      setContextChapters: vi.fn(),
      numVersions: 2,
      setNumVersions: vi.fn(),
      temperature: 0.7,
      setTemperature: vi.fn(),
      handleGenerate: vi.fn(),
    })

    mockGetNovel.mockResolvedValue({
      id: 7,
      title: '测试小说',
      created_at: '2026-03-01T00:00:00Z',
    })
    mockListChaptersMeta.mockResolvedValue([
      {
        id: 11,
        novel_id: 7,
        chapter_number: 1,
        title: '开端',
        source_chapter_label: '第一章 开端',
        source_chapter_number: 1,
        created_at: '2026-03-01T00:00:00Z',
      },
      {
        id: 13,
        novel_id: 7,
        chapter_number: 3,
        title: '归来',
        source_chapter_label: '第844章 归来',
        source_chapter_number: 844,
        created_at: '2026-03-03T00:00:00Z',
      },
    ])
    mockGetChapter.mockImplementation(async (_novelId: number, chapterNum: number) => ({
      id: chapterNum,
      novel_id: 7,
      chapter_number: chapterNum,
      title: chapterNum === 3 ? '归来' : '开端',
      source_chapter_label: chapterNum === 3 ? '第844章 归来' : '第一章 开端',
      source_chapter_number: chapterNum === 3 ? 844 : 1,
      content: chapterNum === 3 ? '第三章内容' : '第一章内容',
      created_at: '2026-03-03T00:00:00Z',
      updated_at: null,
    }))
    mockReadGenerationResultsDebug.mockReturnValue(null)
  })

  it('uses the requested chapter from the studio URL instead of falling back to chapter one', async () => {
    renderWithStudioShell('/novel/7?chapter=3')

    await waitFor(() => {
      expect(screen.getByText('第三章内容')).toBeInTheDocument()
    })

    expect(screen.getByText('第 3 章')).toBeInTheDocument()
    expect(screen.getByText('归来')).toBeInTheDocument()
    expect(screen.queryByText('第一章内容')).not.toBeInTheDocument()
    expect(mockGetChapter).toHaveBeenCalledWith(7, 3)
  })

  it('renders the in-shell entity inspection stage when the studio route requests an entity target', async () => {
    renderWithStudioShell('/novel/7?stage=entity&entity=1&chapter=3')

    await waitFor(() => {
      expect(screen.getByTestId('studio-entity-stage')).toBeInTheDocument()
    })
  })

  it('renders the in-shell review stage when the studio route requests review mode', async () => {
    renderWithStudioShell('/novel/7?stage=review&reviewKind=relationships&chapter=3')

    await waitFor(() => {
      expect(screen.getByTestId('studio-review-stage')).toBeInTheDocument()
    })
  })

  it('renders the in-shell relationship stage when the studio route requests relationship mode', async () => {
    renderWithStudioShell('/novel/7?stage=relationship&entity=1&chapter=3')

    await waitFor(() => {
      expect(screen.getByTestId('studio-relationship-stage')).toBeInTheDocument()
    })
  })

  it('renders the in-shell system stage when the studio route requests system mode', async () => {
    renderWithStudioShell('/novel/7?stage=system&system=1&chapter=3')

    await waitFor(() => {
      expect(screen.getByTestId('studio-system-stage')).toBeInTheDocument()
    })
  })

  it('renders the in-shell results stage from the studio host route', async () => {
    renderWithStudioShell('/novel/7?stage=results&chapter=3')

    await waitFor(() => {
      expect(screen.getByTestId('continuation-results-stage')).toBeInTheDocument()
    })
  })

  it('searches chapters by exact internal chapter numbers and titles', async () => {
    mockListChaptersMeta.mockResolvedValue([
      {
        id: 17,
        novel_id: 7,
        chapter_number: 17,
        title: '正主',
        source_chapter_label: '第十七章 正主',
        source_chapter_number: 17,
        created_at: '2026-03-01T00:00:00Z',
      },
      {
        id: 417,
        novel_id: 7,
        chapter_number: 417,
        title: '可真够懒的',
        source_chapter_label: null,
        source_chapter_number: null,
        created_at: '2026-03-01T00:00:00Z',
      },
      {
        id: 420,
        novel_id: 7,
        chapter_number: 420,
        title: '放一块',
        source_chapter_label: '第420章 放一块',
        source_chapter_number: 420,
        created_at: '2026-03-01T00:00:00Z',
      },
      {
        id: 84,
        novel_id: 7,
        chapter_number: 84,
        title: '无奈之举',
        source_chapter_label: '第八十四章 无奈之举',
        source_chapter_number: 84,
        created_at: '2026-03-01T00:00:00Z',
      },
      {
        id: 844,
        novel_id: 7,
        chapter_number: 544,
        title: '还是搬而泣之的好',
        source_chapter_label: '第844章 还是搬而泣之的好',
        source_chapter_number: 844,
        created_at: '2026-03-02T00:00:00Z',
      },
    ])
    mockGetChapter.mockImplementation(async (_novelId: number, chapterNum: number) => ({
      id: chapterNum,
      novel_id: 7,
      chapter_number: chapterNum,
      title: {
        17: '正主',
        84: '第八十四章 无奈之举',
        417: '可真够懒的',
        420: '放一块',
        544: '还是搬而泣之的好',
      }[chapterNum] ?? '未知章节',
      source_chapter_label: {
        17: '第十七章 正主',
        84: '第八十四章 无奈之举',
        420: '第420章 放一块',
        544: '第844章 还是搬而泣之的好',
      }[chapterNum] ?? null,
      source_chapter_number: {
        17: 17,
        84: 84,
        420: 420,
        544: 844,
      }[chapterNum] ?? null,
      content: `第${chapterNum}章内容`,
      created_at: '2026-03-03T00:00:00Z',
      updated_at: null,
    }))

    const user = userEvent.setup()
    renderWithStudioShell('/novel/7?chapter=84')

    await waitFor(() => {
      expect(screen.getByText('第84章内容')).toBeInTheDocument()
    })

    const searchInput = screen.getByTestId('studio-rail-search')
    const chapterRail = within(screen.getByTestId('studio-rail-chapters'))

    await user.type(searchInput, '17')

    expect(chapterRail.getByRole('button', { name: '第 17 章 · 正主' })).toBeInTheDocument()
    expect(chapterRail.queryByRole('button', { name: '第 417 章 · 可真够懒的' })).not.toBeInTheDocument()
    expect(chapterRail.queryByRole('button', { name: '第 420 章 · 放一块' })).not.toBeInTheDocument()

    await user.clear(searchInput)
    await user.type(searchInput, '544')

    expect(chapterRail.getByRole('button', { name: '第 544 章 · 还是搬而泣之的好' })).toBeInTheDocument()
    expect(chapterRail.queryByRole('button', { name: '第 84 章 · 无奈之举' })).not.toBeInTheDocument()

    await user.clear(searchInput)
    await user.type(searchInput, '84')

    expect(chapterRail.getByRole('button', { name: '第 84 章 · 无奈之举' })).toBeInTheDocument()
    expect(chapterRail.queryByRole('button', { name: '第 544 章 · 还是搬而泣之的好' })).not.toBeInTheDocument()

    await user.clear(searchInput)
    await user.type(searchInput, '无奈')

    expect(chapterRail.getByRole('button', { name: '第 84 章 · 无奈之举' })).toBeInTheDocument()
    expect(chapterRail.queryByRole('button', { name: '第 544 章 · 还是搬而泣之的好' })).not.toBeInTheDocument()
  })

  it('keeps the injection summary rail visible during results-derived studio inspection', async () => {
    mockReadGenerationResultsDebug.mockReturnValue({
      context_chapters: 3,
      injected_entities: ['主角'],
      injected_relationships: [],
      injected_systems: [],
      relevant_entity_ids: [1],
      ambiguous_keywords_disabled: [],
      drift_warnings: [],
      prose_warnings: [],
    })

    renderWithStudioShell('/novel/7?stage=entity&entity=1&chapter=3&resultsChapter=3&resultsContinuations=0:101&resultsTotalVariants=1&artifactPanel=injection_summary&summaryCategory=entities')

    await waitFor(() => {
      expect(screen.getByTestId('studio-entity-stage')).toBeInTheDocument()
    })

    expect(screen.getByTestId('injection-summary-panel')).toBeInTheDocument()
    expect(screen.queryByTestId('studio-assistant')).not.toBeInTheDocument()
  })

  it('waits for chapter save success before navigating from studio to atlas', async () => {
    let resolveSave: (() => void) | null = null
    const saveNow = vi.fn().mockImplementation(() => new Promise<void>((resolve) => {
      resolveSave = resolve
    }))
    mockUseDebouncedAutoSave.mockReturnValue({
      status: 'unsaved',
      schedule: vi.fn(),
      flush: vi.fn().mockResolvedValue(undefined),
      saveNow,
      cancel: vi.fn(),
    })

    const user = userEvent.setup()
    renderWithStudioShell(
      '/novel/7?chapter=3',
      (
        <Routes>
          <Route element={<NovelShell />}>
            <Route
              path="/novel/:novelId"
              element={(
                <>
                  <NovelStudioPage />
                  <LocationProbe />
                </>
              )}
            />
            <Route path="/world/:novelId" element={<LocationProbe />} />
          </Route>
        </Routes>
      ),
    )

    await waitFor(() => {
      expect(screen.getByText('第三章内容')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: '编辑' }))
    expect(screen.getByTestId('chapter-editor')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Atlas 世界模型/ }))

    expect(saveNow).toHaveBeenCalledWith('第三章内容')
    expect(screen.getByTestId('location-path')).toHaveTextContent('/novel/7')
    expect(screen.getByTestId('location-search')).toHaveTextContent('chapter=3')

    resolveSave?.()

    await waitFor(() => {
      expect(screen.getByTestId('location-path')).toHaveTextContent('/world/7')
    })
    expect(screen.getByTestId('location-search')).toHaveTextContent('originStage=chapter')
    expect(screen.getByTestId('location-search')).toHaveTextContent('originChapter=3')
  })

  it('stays in studio when chapter save fails before atlas navigation', async () => {
    const saveNow = vi.fn().mockRejectedValue(new Error('save failed'))
    mockUseDebouncedAutoSave.mockReturnValue({
      status: 'unsaved',
      schedule: vi.fn(),
      flush: vi.fn().mockResolvedValue(undefined),
      saveNow,
      cancel: vi.fn(),
    })

    const user = userEvent.setup()
    renderWithStudioShell(
      '/novel/7?chapter=3',
      (
        <Routes>
          <Route element={<NovelShell />}>
            <Route
              path="/novel/:novelId"
              element={(
                <>
                  <NovelStudioPage />
                  <LocationProbe />
                </>
              )}
            />
            <Route path="/world/:novelId" element={<LocationProbe />} />
          </Route>
        </Routes>
      ),
    )

    await waitFor(() => {
      expect(screen.getByText('第三章内容')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: '编辑' }))
    await user.click(screen.getByRole('button', { name: /Atlas 世界模型/ }))

    await waitFor(() => {
      expect(saveNow).toHaveBeenCalledWith('第三章内容')
    })
    expect(screen.getByTestId('location-path')).toHaveTextContent('/novel/7')
    expect(screen.getByTestId('location-search')).toHaveTextContent('chapter=3')
    expect(screen.getByTestId('chapter-editor')).toBeInTheDocument()
  })

  it('renders the studio rail in English when the UI locale is en', async () => {
    localStorage.setItem('novwr_ui_locale', 'en')
    document.documentElement.lang = 'en'

    renderWithStudioShell('/novel/7?chapter=3')

    expect(await screen.findByPlaceholderText('Search chapters...')).toBeInTheDocument()
    expect(screen.getByText('Workspace')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Atlas world model/i })).toBeInTheDocument()
    expect(screen.getByText('Chapters')).toBeInTheDocument()
  })
})
