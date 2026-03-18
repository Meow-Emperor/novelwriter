import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { ToastProvider } from '@/components/world-model/shared/Toast'
import { WorldBuildPanel } from '@/components/world-model/shared/WorldBuildPanel'
import type { BootstrapJobResponse, WindowIndexState } from '@/types/api'

const mockUseBootstrapStatus = vi.fn()
const mockUseTriggerBootstrap = vi.fn()
const mockUseNovelWindowIndex = vi.fn()
const mockUseWorldEntities = vi.fn()
const mockUseWorldRelationships = vi.fn()
const mockUseWorldSystems = vi.fn()
const mockUseCreateEntity = vi.fn()
const mockUseUpdateEntity = vi.fn()
const mockUseCreateRelationship = vi.fn()
const mockUseUpdateRelationship = vi.fn()
const mockUseCreateSystem = vi.fn()
const mockUseUpdateSystem = vi.fn()

vi.mock('@/hooks/world/useBootstrap', () => ({
  useBootstrapStatus: (...args: unknown[]) => mockUseBootstrapStatus(...args),
  useTriggerBootstrap: (...args: unknown[]) => mockUseTriggerBootstrap(...args),
}))

vi.mock('@/hooks/novel/useNovelWindowIndex', () => ({
  useNovelWindowIndex: (...args: unknown[]) => mockUseNovelWindowIndex(...args),
}))

vi.mock('@/hooks/world/useEntities', () => ({
  useWorldEntities: (...args: unknown[]) => mockUseWorldEntities(...args),
  useCreateEntity: (...args: unknown[]) => mockUseCreateEntity(...args),
  useUpdateEntity: (...args: unknown[]) => mockUseUpdateEntity(...args),
}))

vi.mock('@/hooks/world/useRelationships', () => ({
  useWorldRelationships: (...args: unknown[]) => mockUseWorldRelationships(...args),
  useCreateRelationship: (...args: unknown[]) => mockUseCreateRelationship(...args),
  useUpdateRelationship: (...args: unknown[]) => mockUseUpdateRelationship(...args),
}))

vi.mock('@/hooks/world/useSystems', () => ({
  useWorldSystems: (...args: unknown[]) => mockUseWorldSystems(...args),
  useCreateSystem: (...args: unknown[]) => mockUseCreateSystem(...args),
  useUpdateSystem: (...args: unknown[]) => mockUseUpdateSystem(...args),
}))

const baseJob: BootstrapJobResponse = {
  job_id: 1,
  novel_id: 1,
  mode: 'index_refresh',
  initialized: true,
  status: 'completed',
  progress: { step: 5, detail: 'Done' },
  result: { entities_found: 10, relationships_found: 5, index_refresh_only: false },
  error: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

const freshIndexState: WindowIndexState = {
  status: 'fresh',
  revision: 2,
  built_revision: 2,
  error: null,
  job: null,
}

function renderSection() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    createElement(
      MemoryRouter,
      null,
      createElement(
        QueryClientProvider,
        { client: qc },
        createElement(ToastProvider, null, createElement(WorldBuildPanel, { novelId: 1 }))
      )
    )
  )
}

describe('WorldBuildPanel', () => {
  const mutateFn = vi.fn()

  beforeEach(() => {
    vi.restoreAllMocks()
    mockUseTriggerBootstrap.mockReturnValue({ mutate: mutateFn, isPending: false })
    mockUseNovelWindowIndex.mockReturnValue({
      data: { status: 'missing', revision: 0, built_revision: null, error: null, job: null },
    })
    const mutateAsync = vi.fn().mockResolvedValue({})
    mockUseWorldEntities.mockReturnValue({ data: [] })
    mockUseWorldRelationships.mockReturnValue({ data: [] })
    mockUseWorldSystems.mockReturnValue({ data: [] })
    mockUseCreateEntity.mockReturnValue({ mutateAsync })
    mockUseUpdateEntity.mockReturnValue({ mutateAsync })
    mockUseCreateRelationship.mockReturnValue({ mutateAsync })
    mockUseUpdateRelationship.mockReturnValue({ mutateAsync })
    mockUseCreateSystem.mockReturnValue({ mutateAsync })
    mockUseUpdateSystem.mockReturnValue({ mutateAsync })
  })

  it('renders generation entry + bootstrap action rows', async () => {
    mockUseBootstrapStatus.mockReturnValue({ data: null, isLoading: false })
    const { rerender } = renderSection()

    expect(screen.getByText('AI 工具')).toBeTruthy()
    expect(screen.getByText(/从设定文本生成/)).toBeTruthy()
    expect(screen.getByText('从章节提取')).toBeTruthy()
    expect(screen.getByTestId('novel-copilot-trigger')).toBeTruthy()
    expect(screen.getByText('从全书视角检索设定缺口、潜在线索与值得进一步研究的世界锚点。')).toBeTruthy()
    expect(screen.getByText('检索索引尚未就绪；当前会先回退到最近章节。')).toBeTruthy()

    // Running
    mockUseBootstrapStatus.mockReturnValue({
      data: { ...baseJob, status: 'extracting' as const, progress: { step: 2, detail: 'Extracting...' } },
      isLoading: false,
    })
    rerender(
      createElement(
        MemoryRouter,
        null,
        createElement(
          QueryClientProvider,
          { client: new QueryClient({ defaultOptions: { queries: { retry: false } } }) },
          createElement(ToastProvider, null, createElement(WorldBuildPanel, { novelId: 1 }))
        )
      )
    )
    expect(screen.getByText('提取候选词')).toBeTruthy()

    // Completed
    mockUseBootstrapStatus.mockReturnValue({ data: baseJob, isLoading: false })
    mockUseNovelWindowIndex.mockReturnValue({ data: freshIndexState })
    rerender(
      createElement(
        MemoryRouter,
        null,
        createElement(
          QueryClientProvider,
          { client: new QueryClient({ defaultOptions: { queries: { retry: false } } }) },
          createElement(ToastProvider, null, createElement(WorldBuildPanel, { novelId: 1 }))
        )
      )
    )
    expect(screen.getByText('从章节提取')).toBeTruthy()
    expect(screen.getByText('10 实体 · 5 关系')).toBeTruthy()
  })

  it('opens the whole-book research workbench without an external provider', async () => {
    mockUseBootstrapStatus.mockReturnValue({ data: null, isLoading: false })
    const user = userEvent.setup()

    renderSection()
    expect(screen.queryByTestId('novel-copilot-drawer')).toBeNull()

    await user.click(screen.getByTestId('novel-copilot-trigger'))

    expect(screen.getByTestId('novel-copilot-drawer')).toHaveAttribute('data-state', 'open')
    expect(screen.getAllByText('全书研究').length).toBeGreaterThan(0)
    expect(screen.getAllByText('研究工作台').length).toBeGreaterThan(0)
    expect(screen.getByText('盘点设定缺口')).toBeTruthy()
  })
})
