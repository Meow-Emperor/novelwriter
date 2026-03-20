import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement } from 'react'
import { RelationshipSidebarPanel } from '@/components/atlas/relationships/RelationshipSidebarPanel'
import { NovelCopilotProvider } from '@/components/novel-copilot/NovelCopilotProvider'
import { NovelCopilotDrawer } from '@/components/novel-copilot/NovelCopilotDrawer'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import { ToastProvider } from '@/components/world-model/shared/Toast'

const mockUseWorldRelationships = vi.fn()
const mockUseConfirmRelationships = vi.fn()
const mockUseRejectRelationships = vi.fn()
const mockUseWorldEntities = vi.fn()
const mockUseWorldSystems = vi.fn()
const mockUseCreateEntity = vi.fn()
const mockUseUpdateEntity = vi.fn()
const mockUseCreateRelationship = vi.fn()
const mockUseUpdateRelationship = vi.fn()
const mockUseCreateSystem = vi.fn()
const mockUseUpdateSystem = vi.fn()

vi.mock('@/hooks/world/useEntities', () => ({
  useWorldEntities: (...args: unknown[]) => mockUseWorldEntities(...args),
  useCreateEntity: (...args: unknown[]) => mockUseCreateEntity(...args),
  useUpdateEntity: (...args: unknown[]) => mockUseUpdateEntity(...args),
}))

vi.mock('@/hooks/world/useRelationships', () => ({
  useWorldRelationships: (...args: unknown[]) => mockUseWorldRelationships(...args),
  useConfirmRelationships: (...args: unknown[]) => mockUseConfirmRelationships(...args),
  useRejectRelationships: (...args: unknown[]) => mockUseRejectRelationships(...args),
  useCreateRelationship: (...args: unknown[]) => mockUseCreateRelationship(...args),
  useUpdateRelationship: (...args: unknown[]) => mockUseUpdateRelationship(...args),
}))

vi.mock('@/hooks/world/useSystems', () => ({
  useWorldSystems: (...args: unknown[]) => mockUseWorldSystems(...args),
  useCreateSystem: (...args: unknown[]) => mockUseCreateSystem(...args),
  useUpdateSystem: (...args: unknown[]) => mockUseUpdateSystem(...args),
}))

function renderSection() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    createElement(
      QueryClientProvider,
      { client: queryClient },
      createElement(
        UiLocaleProvider,
        null,
        createElement(
          ToastProvider,
          null,
          createElement(
            NovelCopilotProvider,
            { novelId: 1, interactionLocale: 'zh' },
            createElement(RelationshipSidebarPanel, {
              novelId: 1,
              selectedEntityId: 101,
              selectedEntityName: '苏瑶',
              onRequestNewRelationship: vi.fn(),
              onOpenDraftReview: vi.fn(),
            }),
            createElement(NovelCopilotDrawer, { novelId: 1 }),
          ),
        ),
      ),
    ),
  )
}

describe('RelationshipSidebarPanel', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    mockUseWorldRelationships.mockReturnValue({ data: [], isLoading: false })
    mockUseConfirmRelationships.mockReturnValue({ mutate: vi.fn(), isPending: false })
    mockUseRejectRelationships.mockReturnValue({ mutate: vi.fn(), isPending: false })
    const mutateAsync = vi.fn().mockResolvedValue({})
    mockUseWorldEntities.mockReturnValue({ data: [] })
    mockUseWorldSystems.mockReturnValue({ data: [] })
    mockUseCreateEntity.mockReturnValue({ mutateAsync })
    mockUseUpdateEntity.mockReturnValue({ mutateAsync })
    mockUseCreateRelationship.mockReturnValue({ mutateAsync })
    mockUseUpdateRelationship.mockReturnValue({ mutateAsync })
    mockUseCreateSystem.mockReturnValue({ mutateAsync })
    mockUseUpdateSystem.mockReturnValue({ mutateAsync })
  })

  it('opens a relationship session with an explicit two-party title', async () => {
    const user = userEvent.setup()
    renderSection()

    await user.click(screen.getByRole('button', { name: /AI 建议/ }))

    expect(screen.getAllByText('苏瑶 ↔ 相关实体').length).toBeGreaterThan(0)
    expect(screen.getAllByText('关系上下文').length).toBeGreaterThan(0)
  })
})
