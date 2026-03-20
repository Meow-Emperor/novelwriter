// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { useParams, useNavigate, useLocation, useSearchParams } from 'react-router-dom'
import '@/lib/uiMessagePacks/novel'
import { useQuery } from '@tanstack/react-query'
import { MoreHorizontal, Pencil, Trash2, Upload } from 'lucide-react'
import { ChapterContent } from '@/components/detail/ChapterContent'
import { ChapterEditor } from '@/components/detail/ChapterEditor'
import { EmptyWorldOnboarding } from '@/components/detail/EmptyWorldOnboarding'
import { PageShell } from '@/components/layout/PageShell'
import { NwButton } from '@/components/ui/nw-button'
import { GlassSurface } from '@/components/ui/glass-surface'
import { getLlmApiErrorMessage } from '@/lib/llmErrorMessages'
import { api, ApiError } from '@/services/api'
import { novelKeys } from '@/hooks/novel/keys'
import { useUpdateChapter } from '@/hooks/novel/useUpdateChapter'
import { useCreateChapter } from '@/hooks/novel/useCreateChapter'
import { useDeleteChapter } from '@/hooks/novel/useDeleteChapter'
import { useWorldEntities } from '@/hooks/world/useEntities'
import { useWorldSystems } from '@/hooks/world/useSystems'
import { useBootstrapStatus, useTriggerBootstrap } from '@/hooks/world/useBootstrap'
import { WorldGenerationDialog } from '@/components/world-model/shared/WorldGenerationDialog'
import { LABELS } from '@/constants/labels'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { formatRelativeTime } from '@/lib/formatRelativeTime'
import { downloadTextFile } from '@/lib/downloadTextFile'
import {
  formatChapterBadgeLabel,
  formatChapterLabel,
  getChapterDisplayTitle,
  matchesChapterSearch,
  serializeChaptersToPlainText,
} from '@/lib/chaptersPlainText'
import { useDebouncedAutoSave } from '@/hooks/useDebouncedAutoSave'
import { useContinuationSetupState } from '@/hooks/novel/useContinuationSetupState'
import { dismissWorldOnboarding, isWorldOnboardingDismissed } from '@/lib/worldOnboardingStorage'
import { getActiveWarnings, setActiveWarnings } from '@/lib/postcheckActiveWarningsStorage'
import { getWhitelist, addToWhitelist } from '@/lib/postcheckWhitelistStorage'
import { DriftWarningPopover } from '@/components/generation/DriftWarningPopover'
import { NovelShellLayout } from '@/components/novel-shell/NovelShellLayout'
import { NovelShellRail } from '@/components/novel-shell/NovelShellRail'
import { ArtifactStage } from '@/components/novel-shell/ArtifactStage'
import { StudioAssistantPanel } from '@/components/studio/StudioAssistantPanel'
import { InjectionSummaryPanel } from '@/components/studio/panels/InjectionSummaryPanel'
import { StudioNavigationRail } from '@/components/studio/rail/StudioNavigationRail'
import { ContinuationSetupStage } from '@/components/studio/stages/ContinuationSetupStage'
import { StudioEntityStage } from '@/components/studio/stages/StudioEntityStage'
import { StudioDraftReviewStage } from '@/components/studio/stages/StudioDraftReviewStage'
import { StudioRelationshipStage } from '@/components/studio/stages/StudioRelationshipStage'
import { StudioSystemStage } from '@/components/studio/stages/StudioSystemStage'
import { ContinuationResultsStage } from '@/components/studio/stages/ContinuationResultsStage'
import { useNovelShell } from '@/components/novel-shell/NovelShellContext'
import {
  readNovelShellArtifactPanelSearchParams,
  readResultsProvenanceSearchParams,
  setAtlasStudioOriginSearchParams,
  setNovelShellArtifactPanelSearchParams,
  setAtlasReviewKindSearchParams,
  setResultsProvenanceSearchParams,
  setAtlasSuggestionTargetSearchParams,
  setAtlasTabSearchParams,
  setStudioChapterSearchParams,
  setStudioEntityStageSearchParams,
  setStudioRelationshipStageSearchParams,
  setStudioResultsStageSearchParams,
  setStudioSystemStageSearchParams,
  setStudioReviewKindSearchParams,
  setStudioStageSearchParams,
} from '@/components/novel-shell/NovelShellRouteState'
import { useNovelCopilot } from '@/components/novel-copilot/NovelCopilotContext'
import { NovelCopilotDrawer } from '@/components/novel-copilot/NovelCopilotDrawer'
import {
  buildCurrentEntityCopilotLaunchArgs,
  buildRelationshipResearchCopilotLaunchArgs,
} from '@/components/novel-copilot/novelCopilotLauncher'
import { useStudioCopilotTargetNavigation } from '@/components/novel-copilot/useCopilotTargetNavigation'
import type { TextAnnotation } from '@/components/ui/plain-text-content'
import type { BootstrapStatus, ContinueDebugSummary } from '@/types/api'
import {
  pickInitialInjectionSummaryCategory,
  resolveInjectionSummaryNavigationTarget,
  type InjectionSummaryCategory,
} from '@/lib/injectionSummaryNavigation'
import { readGenerationResultsDebug } from '@/lib/generationResultsDebugStorage'

function countWords(text: string): number {
  return text.replace(/\s/g, '').length
}

const AUTO_SAVE_DELAY = 3000
const BOOTSTRAP_RUNNING_STATUSES: BootstrapStatus[] = [
  'pending',
  'tokenizing',
  'extracting',
  'windowing',
  'refining',
]

export function NovelStudioPage() {
  const { novelId: novelIdParam } = useParams<{ novelId: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const locationState = location.state as {
    streamParams?: unknown
    novelId?: number
    studioResultsDebug?: ContinueDebugSummary | null
  } | null
  const novelId = Number(novelIdParam)
  const { locale, t } = useUiLocale()
  const { routeState } = useNovelShell()
  const { isOpen: isWorkbenchOpen, focusedSessionId, openDrawer } = useNovelCopilot()
  const activeStage = routeState.stage ?? 'chapter'
  const showWorkbenchRail = isWorkbenchOpen && focusedSessionId !== null

  const [editMode, setEditMode] = useState(false)
  const [editingTitle, setEditingTitle] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [liveResultsDebugState, setLiveResultsDebugState] = useState<{
    key: string | null
    value: ContinueDebugSummary | null
  }>({
    key: null,
    value: null,
  })
  const [editorContent, setEditorContent] = useState('')
  const [showMoreActions, setShowMoreActions] = useState(false)

  const [worldGenOpen, setWorldGenOpen] = useState(false)
  const [bootstrapError, setBootstrapError] = useState<string | null>(null)

  const { data: worldEntities = [], isLoading: worldEntitiesLoading } = useWorldEntities(novelId)
  const { data: worldSystems = [], isLoading: worldSystemsLoading } = useWorldSystems(novelId)
  const { data: bootstrapJob, isLoading: bootstrapLoading } = useBootstrapStatus(novelId)
  const triggerBootstrap = useTriggerBootstrap(novelId)
  const selectedStudioEntityStillExists = (
    routeState.entityId !== null && worldEntities.some((entity) => entity.id === routeState.entityId)
  )
  const effectiveStudioEntityId = routeState.entityId === null
    ? (worldEntities[0]?.id ?? null)
    : selectedStudioEntityStillExists ? routeState.entityId : (worldEntities[0]?.id ?? null)
  const effectiveStudioEntityName = effectiveStudioEntityId === null
    ? null
    : worldEntities.find((entity) => entity.id === effectiveStudioEntityId)?.name ?? null
  const selectedStudioSystemStillExists = (
    routeState.systemId !== null && worldSystems.some((system) => system.id === routeState.systemId)
  )
  const effectiveStudioSystemId = routeState.systemId === null
    ? (worldSystems[0]?.id ?? null)
    : selectedStudioSystemStillExists ? routeState.systemId : (worldSystems[0]?.id ?? null)
  const effectiveStudioSystemName = effectiveStudioSystemId === null
    ? null
    : worldSystems.find((system) => system.id === effectiveStudioSystemId)?.name ?? null

  const { data: novel, isLoading: novelLoading } = useQuery({
    queryKey: novelKeys.detail(novelId), queryFn: () => api.getNovel(novelId), enabled: !!novelIdParam,
  })
  // Empty-world onboarding (per novel instance, persisted).
  //
  // We include novel.created_at in the key to avoid collisions when SQLite reuses ids after deletes.
  const worldOnboardingDismissed = useMemo(() => (
    isWorldOnboardingDismissed(novelId, novel?.created_at)
  ), [novelId, novel?.created_at])
  const { data: chaptersMeta = [] } = useQuery({
    queryKey: novelKeys.chaptersMeta(novelId), queryFn: () => api.listChaptersMeta(novelId), enabled: !!novelIdParam,
  })
  const activeChapterNum = useMemo(() => {
    if (
      routeState.chapterNum !== null
      && chaptersMeta.some((chapterMeta) => chapterMeta.chapter_number === routeState.chapterNum)
    ) {
      return routeState.chapterNum
    }
    return chaptersMeta[0]?.chapter_number ?? null
  }, [chaptersMeta, routeState.chapterNum])
  const latestChapterNum = chaptersMeta.length > 0 ? chaptersMeta[chaptersMeta.length - 1].chapter_number : null
  const latestChapterMeta = chaptersMeta.length > 0 ? chaptersMeta[chaptersMeta.length - 1] : null
  const latestChapterReference = latestChapterMeta ? formatChapterBadgeLabel(latestChapterMeta) : null

  // Continuation setup state hoisted at page level so it survives stage mount/unmount.
  const continuationState = useContinuationSetupState(novelId, latestChapterNum)

  const updateChapter = useUpdateChapter(novelId, activeChapterNum ?? 0)
  const createChapter = useCreateChapter(novelId)
  const deleteChapter = useDeleteChapter(novelId)
  const {
    status: autoSaveStatus,
    schedule: scheduleAutoSave,
    saveNow: saveNowAutoSave,
    cancel: cancelAutoSave,
  } = useDebouncedAutoSave<string>({
    delayMs: AUTO_SAVE_DELAY,
    save: async (content) => {
      if (activeChapterNum === null) return
      await updateChapter.mutateAsync({ content })
    },
  })

  const { data: chapter, isLoading: chapterLoading } = useQuery({
    queryKey: novelKeys.chapter(novelId, activeChapterNum ?? 0),
    queryFn: () => {
      if (activeChapterNum === null) {
        // Guard for type safety; `enabled` prevents this from running in practice.
        throw new Error('Missing active chapter number')
      }
      return api.getChapter(novelId, activeChapterNum)
    },
    enabled: !!novelIdParam && activeChapterNum !== null,
  })

  const currentMeta = chaptersMeta.find(c => c.chapter_number === activeChapterNum)

  // ── Postcheck drift annotations (carried over from generation results) ──
  const [driftWhitelist, setDriftWhitelist] = useState<string[]>(() => getWhitelist(novelId))

  const handleDismissDriftTerm = useCallback((term: string) => {
    addToWhitelist(novelId, term)
    setDriftWhitelist(prev => [...prev, term])
  }, [novelId])

  // Active warnings for this chapter (used in both read and edit mode)
  const activeChapterWarnings = (() => {
    if (activeChapterNum === null) return []
    return getActiveWarnings(novelId, activeChapterNum, currentMeta?.created_at)
      .filter(w => !driftWhitelist.includes(w.term))
  })()

  // Read-mode: full annotations with popovers
  const chapterDriftAnnotations: TextAnnotation[] = (() => {
    if (editMode || activeChapterWarnings.length === 0) return []
    return activeChapterWarnings.map(w => ({
      id: `drift-${w.code}-${w.term}`,
      term: w.term,
      className: 'nw-drift-highlight',
      renderPopover: ({ onClose }: { onClose: () => void }) => (
        <DriftWarningPopover
          code={w.code}
          term={w.term}
          onDismiss={() => {
            handleDismissDriftTerm(w.term)
            onClose()
          }}
        />
      ),
    }))
  })()

  // Edit-mode: compact term list for the editor banner
  const editorWarningTerms = editMode && activeChapterWarnings.length > 0
    ? activeChapterWarnings.map(w => ({ code: w.code, term: w.term }))
    : undefined

  const filteredChapters = (() => {
    if (!searchQuery.trim()) return chaptersMeta
    return chaptersMeta.filter((chapterMeta) => matchesChapterSearch(chapterMeta, searchQuery))
  })()

  useEffect(() => {
    // Prevent autosave timers from leaking across chapter switches.
    cancelAutoSave()
  }, [activeChapterNum, cancelAutoSave])

  const handleEditorChange = (val: string) => {
    setEditorContent(val)
    scheduleAutoSave(val)
  }
  const handleSave = () => {
    if (activeChapterNum === null) return
    void saveNowAutoSave(editorContent)
      .then(() => setEditMode(false))
      .catch(() => {
        // Keep the editor open; user can retry.
      })
  }
  const handleCancelEdit = () => {
    cancelAutoSave()
    setEditorContent(chapter?.content ?? '')
    setEditMode(false)
  }
  const handleExportAll = async () => {
    try {
      const allChapters = await api.listChapters(novelId)
      const content = serializeChaptersToPlainText(allChapters)
      downloadTextFile(
        `${novel?.title ?? 'novel'}_all_chapters_${new Date().toISOString().slice(0, 10)}.txt`,
        content
      )
    } catch { /* ignore */ }
  }
  const handleCreateChapter = () => {
    createChapter.mutate({ title: '', content: '' }, {
      onSuccess: (nc) => {
        cancelAutoSave()
        setEditorContent('')
        setEditingTitle(false)
        setEditMode(true)
        setShowMoreActions(false)
        navigateToChapterStage(nc.chapter_number)
      },
    })
  }
  const handleTitleSave = () => {
    setEditingTitle(false)
    if (activeChapterNum === null || !currentMeta) return
    const newTitle = titleDraft.trim()
    if (newTitle === (currentMeta.title || '')) return
    updateChapter.mutate({ title: newTitle })
  }

  const handleDeleteChapter = () => {
    if (activeChapterNum === null) return
    if (!window.confirm(t('studio.chapter.deleteConfirm', { chapter: activeChapterReference ?? `Ch. ${activeChapterNum}` }))) return
    deleteChapter.mutate(activeChapterNum, {
      onSuccess: () => {
        cancelAutoSave()
        // Clean up persisted drift warnings for the deleted chapter
        setActiveWarnings(novelId, activeChapterNum, [])
        const idx = chaptersMeta.findIndex(c => c.chapter_number === activeChapterNum)
        const next = chaptersMeta[idx + 1] ?? chaptersMeta[idx - 1]
        setEditorContent('')
        setEditMode(false)
        setEditingTitle(false)
        setShowMoreActions(false)
        navigateToChapterStage(next?.chapter_number ?? null)
      },
    })
  }

  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [cursorInfo, setCursorInfo] = useState({ para: 1, col: 1 })
  const handleSelectionChange = () => {
    const ta = textareaRef.current; if (!ta) return
    const before = ta.value.slice(0, ta.selectionStart); const lines = before.split('\n')
    setCursorInfo({ para: lines.length, col: lines[lines.length - 1].length + 1 })
  }
  const handleUndo = () => { textareaRef.current?.focus(); document.execCommand('undo') }
  const handleRedo = () => { textareaRef.current?.focus(); document.execCommand('redo') }

  const worldLoading = worldEntitiesLoading || worldSystemsLoading || bootstrapLoading
  const worldEmpty = worldEntities.length === 0 && worldSystems.length === 0
  const bootstrapRunning = bootstrapJob
    ? BOOTSTRAP_RUNNING_STATUSES.includes(bootstrapJob.status)
    : false
  const showWorldOnboarding = !worldLoading && !worldOnboardingDismissed && worldEmpty && !bootstrapRunning
  const artifactPanelState = useMemo(
    () => readNovelShellArtifactPanelSearchParams(searchParams),
    [searchParams],
  )
  const resultsProvenance = useMemo(
    () => readResultsProvenanceSearchParams(searchParams),
    [searchParams],
  )
  const canonicalResultsProvenance = useMemo(() => {
    const continuations = searchParams.get('continuations')?.trim()
    if (activeStage !== 'results' || activeChapterNum === null || !continuations) return null
    const totalVariantsRaw = searchParams.get('total_variants')
    const totalVariants = totalVariantsRaw ? Number(totalVariantsRaw) : null
    return {
      chapterNum: activeChapterNum,
      continuations,
      totalVariants: totalVariants !== null && Number.isFinite(totalVariants) ? totalVariants : null,
    }
  }, [activeChapterNum, activeStage, searchParams])
  const effectiveResultsProvenance = resultsProvenance ?? canonicalResultsProvenance
  const hasEphemeralResultsContext = (
    locationState?.streamParams != null
    && locationState?.novelId === novelId
  )
  const hasResultsContext = activeStage === 'results' || resultsProvenance !== null || hasEphemeralResultsContext
  const currentResultsDebugKey = useMemo(() => {
    if (effectiveResultsProvenance) return `persisted:${effectiveResultsProvenance.continuations}`
    if (hasEphemeralResultsContext) return `ephemeral:${location.key}`
    return null
  }, [effectiveResultsProvenance, hasEphemeralResultsContext, location.key])
  const liveResultsDebug = liveResultsDebugState.key === currentResultsDebugKey
    ? liveResultsDebugState.value
    : null
  const resultsDebug = useMemo(
    () => (
      !hasResultsContext
        ? null
        : liveResultsDebug
      ?? (effectiveResultsProvenance
        ? readGenerationResultsDebug(effectiveResultsProvenance.continuations) ?? locationState?.studioResultsDebug ?? null
        : locationState?.studioResultsDebug ?? null)
    ),
    [effectiveResultsProvenance, hasResultsContext, liveResultsDebug, locationState?.studioResultsDebug],
  )
  const injectionSummaryPanelState = useMemo(() => {
    if (!resultsDebug) return null
    return {
      panel: 'injection_summary' as const,
      injectionCategory: artifactPanelState.injectionCategory ?? pickInitialInjectionSummaryCategory(resultsDebug),
    }
  }, [artifactPanelState.injectionCategory, resultsDebug])
  const showInjectionSummaryRail = artifactPanelState.panel === 'injection_summary' && injectionSummaryPanelState !== null

  const resultsNavigationState = useMemo(() => {
    if (!hasResultsContext) return null
    return {
      ...(locationState ?? {}),
      studioResultsDebug: resultsDebug ?? null,
    }
  }, [hasResultsContext, locationState, resultsDebug])
  const atlasStudioOrigin = useMemo(() => ({
    stage: activeStage,
    chapterNum: activeStage === 'results'
      ? (effectiveResultsProvenance?.chapterNum ?? activeChapterNum)
      : activeChapterNum,
    entityId: routeState.entityId,
    systemId: routeState.systemId,
    reviewKind: routeState.reviewKind,
    resultsProvenance: effectiveResultsProvenance,
    artifactPanelState: showInjectionSummaryRail ? injectionSummaryPanelState : null,
  }), [
    activeChapterNum,
    activeStage,
    effectiveResultsProvenance,
    injectionSummaryPanelState,
    routeState.entityId,
    routeState.systemId,
    routeState.reviewKind,
    showInjectionSummaryRail,
  ])

  const navigateToChapterStage = useCallback((chapterNumber: number | null = null) => {
    let nextSearchParams = setStudioChapterSearchParams(new URLSearchParams(), chapterNumber)
    nextSearchParams = setResultsProvenanceSearchParams(nextSearchParams, null)
    nextSearchParams = setNovelShellArtifactPanelSearchParams(nextSearchParams, null)
    const nextSearch = nextSearchParams.toString()
    navigate(nextSearch ? `/novel/${novelId}?${nextSearch}` : `/novel/${novelId}`, { replace: true, state: null })
  }, [navigate, novelId])
  const navigateToResultsStage = useCallback((options?: { replace?: boolean }) => {
    let nextSearchParams = setStudioResultsStageSearchParams(new URLSearchParams(), activeChapterNum)
    nextSearchParams = setResultsProvenanceSearchParams(nextSearchParams, null)
    if (effectiveResultsProvenance) {
      nextSearchParams.set('continuations', effectiveResultsProvenance.continuations)
      if (effectiveResultsProvenance.totalVariants !== null) {
        nextSearchParams.set('total_variants', String(effectiveResultsProvenance.totalVariants))
      } else {
        nextSearchParams.delete('total_variants')
      }
    } else {
      nextSearchParams.delete('continuations')
      nextSearchParams.delete('total_variants')
    }
    nextSearchParams = setNovelShellArtifactPanelSearchParams(nextSearchParams, showInjectionSummaryRail ? injectionSummaryPanelState : null)
    navigate(`/novel/${novelId}?${nextSearchParams.toString()}`, {
      replace: options?.replace ?? false,
      state: resultsNavigationState,
    })
  }, [activeChapterNum, effectiveResultsProvenance, injectionSummaryPanelState, navigate, novelId, resultsNavigationState, showInjectionSummaryRail])
  const navigateToWriteStage = useCallback(() => {
    let nextSearchParams = setStudioStageSearchParams(new URLSearchParams(), 'write')
    nextSearchParams = setResultsProvenanceSearchParams(nextSearchParams, null)
    nextSearchParams = setNovelShellArtifactPanelSearchParams(nextSearchParams, null)
    navigate(`/novel/${novelId}?${nextSearchParams.toString()}`, { replace: true, state: null })
  }, [navigate, novelId])
  const navigateToEntityStage = useCallback((entityId: number | null, options?: {
    chapterNumber?: number | null
    replace?: boolean
  }) => {
    let nextSearchParams = setStudioChapterSearchParams(new URLSearchParams(), options?.chapterNumber ?? activeChapterNum)
    nextSearchParams = setStudioEntityStageSearchParams(nextSearchParams, entityId)
    nextSearchParams = setResultsProvenanceSearchParams(nextSearchParams, effectiveResultsProvenance)
    nextSearchParams = setNovelShellArtifactPanelSearchParams(nextSearchParams, showInjectionSummaryRail ? injectionSummaryPanelState : null)
    navigate(`/novel/${novelId}?${nextSearchParams.toString()}`, { replace: options?.replace ?? false, state: resultsNavigationState })
  }, [activeChapterNum, effectiveResultsProvenance, injectionSummaryPanelState, navigate, novelId, resultsNavigationState, showInjectionSummaryRail])
  const navigateToReviewStage = useCallback((reviewKind: 'entities' | 'relationships' | 'systems', options?: {
    chapterNumber?: number | null
    replace?: boolean
  }) => {
    let nextSearchParams = setStudioChapterSearchParams(new URLSearchParams(), options?.chapterNumber ?? activeChapterNum)
    nextSearchParams = setStudioReviewKindSearchParams(nextSearchParams, reviewKind)
    nextSearchParams = setResultsProvenanceSearchParams(nextSearchParams, effectiveResultsProvenance)
    nextSearchParams = setNovelShellArtifactPanelSearchParams(nextSearchParams, showInjectionSummaryRail ? injectionSummaryPanelState : null)
    navigate(`/novel/${novelId}?${nextSearchParams.toString()}`, { replace: options?.replace ?? false, state: resultsNavigationState })
  }, [activeChapterNum, effectiveResultsProvenance, injectionSummaryPanelState, navigate, novelId, resultsNavigationState, showInjectionSummaryRail])
  const navigateToRelationshipStage = useCallback((entityId: number | null, options?: {
    chapterNumber?: number | null
    replace?: boolean
  }) => {
    let nextSearchParams = setStudioChapterSearchParams(new URLSearchParams(), options?.chapterNumber ?? activeChapterNum)
    nextSearchParams = setStudioRelationshipStageSearchParams(nextSearchParams, entityId)
    nextSearchParams = setResultsProvenanceSearchParams(nextSearchParams, effectiveResultsProvenance)
    nextSearchParams = setNovelShellArtifactPanelSearchParams(nextSearchParams, showInjectionSummaryRail ? injectionSummaryPanelState : null)
    navigate(`/novel/${novelId}?${nextSearchParams.toString()}`, { replace: options?.replace ?? false, state: resultsNavigationState })
  }, [activeChapterNum, effectiveResultsProvenance, injectionSummaryPanelState, navigate, novelId, resultsNavigationState, showInjectionSummaryRail])
  const navigateToSystemStage = useCallback((systemId: number | null, options?: {
    chapterNumber?: number | null
    replace?: boolean
  }) => {
    let nextSearchParams = setStudioChapterSearchParams(new URLSearchParams(), options?.chapterNumber ?? activeChapterNum)
    nextSearchParams = setStudioSystemStageSearchParams(nextSearchParams, systemId)
    nextSearchParams = setResultsProvenanceSearchParams(nextSearchParams, effectiveResultsProvenance)
    nextSearchParams = setNovelShellArtifactPanelSearchParams(nextSearchParams, showInjectionSummaryRail ? injectionSummaryPanelState : null)
    navigate(`/novel/${novelId}?${nextSearchParams.toString()}`, { replace: options?.replace ?? false, state: resultsNavigationState })
  }, [activeChapterNum, effectiveResultsProvenance, injectionSummaryPanelState, navigate, novelId, resultsNavigationState, showInjectionSummaryRail])
  const navigateToAtlas = useCallback((params?: URLSearchParams) => {
    const commitNavigation = () => {
      const nextParams = setAtlasStudioOriginSearchParams(params ?? new URLSearchParams(), atlasStudioOrigin)
      const nextSearch = nextParams.toString()
      navigate(nextSearch ? `/world/${novelId}?${nextSearch}` : `/world/${novelId}`)
    }

    if (editMode) {
      void saveNowAutoSave(editorContent)
        .then(() => {
          setEditMode(false)
          commitNavigation()
        })
        .catch(() => {
          // Save failed — stay on the current Studio stage so the user can retry.
        })
      return
    }

    commitNavigation()
  }, [atlasStudioOrigin, editMode, editorContent, navigate, novelId, saveNowAutoSave])
  const handleReturnToArtifact = () => {
    if (hasResultsContext) {
      navigateToResultsStage()
      return
    }
    navigateToChapterStage(activeChapterNum)
  }
  const handleResultsDebugChange = useCallback((debug: ContinueDebugSummary | null) => {
    setLiveResultsDebugState({
      key: currentResultsDebugKey,
      value: debug,
    })
  }, [currentResultsDebugKey])
  const handleStudioLocateTarget = useStudioCopilotTargetNavigation({
    navigateToReviewStage,
    navigateToEntityStage: (entityId) => navigateToEntityStage(entityId),
    navigateToRelationshipStage: (entityId) => navigateToRelationshipStage(entityId),
    navigateToSystemStage: (systemId) => navigateToSystemStage(systemId),
    navigateToAtlas,
  })
  const setInjectionSummaryCategory = useCallback((category: InjectionSummaryCategory) => {
    const nextSearchParams = setNovelShellArtifactPanelSearchParams(new URLSearchParams(location.search), {
      panel: 'injection_summary',
      injectionCategory: category,
    })
    navigate(
      { pathname: location.pathname, search: nextSearchParams.toString() },
      { replace: true, state: resultsNavigationState },
    )
  }, [location.pathname, location.search, navigate, resultsNavigationState])
  const handleOpenInjectionCategory = useCallback((tab: InjectionSummaryCategory) => {
    navigateToAtlas(setAtlasTabSearchParams(new URLSearchParams(), tab))
  }, [navigateToAtlas])
  const handleOpenInjectionItem = useCallback((category: InjectionSummaryCategory, label: string) => {
    const target = resolveInjectionSummaryNavigationTarget({
      category,
      label,
      entities: worldEntities,
      systems: worldSystems,
    })

    if (target.kind === 'studio_entity') {
      navigateToEntityStage(target.entityId, { replace: true })
      return
    }

    if (target.kind === 'studio_relationship') {
      navigateToRelationshipStage(target.entityId, { replace: true })
      return
    }

    if (target.kind === 'studio_system') {
      navigateToSystemStage(target.systemId, { replace: true })
      return
    }

    navigateToAtlas(setAtlasTabSearchParams(new URLSearchParams(), target.tab))
  }, [navigateToAtlas, navigateToEntityStage, navigateToRelationshipStage, navigateToSystemStage, worldEntities, worldSystems])
  const openEntityCopilot = useCallback(() => {
    if (effectiveStudioEntityId === null) return
    openDrawer(...buildCurrentEntityCopilotLaunchArgs({
      entityId: effectiveStudioEntityId,
      entityName: effectiveStudioEntityName,
      surface: 'studio',
      stage: 'entity',
    }))
  }, [effectiveStudioEntityId, effectiveStudioEntityName, openDrawer])
  const openRelationshipCopilot = useCallback(() => {
    if (effectiveStudioEntityId === null) return
    openDrawer(...buildRelationshipResearchCopilotLaunchArgs({
      entityId: effectiveStudioEntityId,
      entityName: effectiveStudioEntityName,
      surface: 'studio',
      stage: 'relationship',
    }))
  }, [effectiveStudioEntityId, effectiveStudioEntityName, openDrawer])
  const contextualCopilotAction = useMemo(() => {
    if (activeStage === 'entity' && effectiveStudioEntityId !== null) {
      return {
        title: '实体补完',
        description: effectiveStudioEntityName
          ? `围绕「${effectiveStudioEntityName}」继续补全设定、核查依据与属性。`
          : '继续补全当前实体的设定与属性。',
        onClick: openEntityCopilot,
      }
    }
    if (activeStage === 'relationship' && effectiveStudioEntityId !== null) {
      return {
        title: '关系补完',
        description: effectiveStudioEntityName
          ? `围绕「${effectiveStudioEntityName}」的关系网络继续核查与补完。`
          : '继续核查当前实体相关的关系线索。',
        onClick: openRelationshipCopilot,
      }
    }
    return undefined
  }, [activeStage, effectiveStudioEntityId, effectiveStudioEntityName, openEntityCopilot, openRelationshipCopilot])

  const handleDismissWorldOnboarding = () => {
    dismissWorldOnboarding(novelId, novel?.created_at)
    navigate(`/world/${novelId}`)
  }

  const handleTriggerBootstrap = () => {
    setBootstrapError(null)
    triggerBootstrap.mutate(
      { mode: 'initial' },
      {
        onError: (err) => {
          if (err instanceof ApiError) {
            const llmMessage = getLlmApiErrorMessage(err, locale)
            if (llmMessage) {
              setBootstrapError(llmMessage)
              return
            }
            if (err.code === 'bootstrap_already_running') {
              setBootstrapError(LABELS.BOOTSTRAP_SCANNING)
              return
            }
            if (err.code === 'bootstrap_no_text') {
              setBootstrapError(LABELS.BOOTSTRAP_NO_TEXT)
              return
            }
          }
          setBootstrapError(LABELS.ERROR_BOOTSTRAP_TRIGGER_FAILED)
        },
      },
    )
  }

  if (novelLoading) {
    return (
      <PageShell showNavbar={false} className="h-screen" mainClassName="items-center justify-center">
        <span className="text-sm text-muted-foreground">{t('studio.loading')}</span>
      </PageShell>
    )
  }
  if (!novel) {
    return (
      <PageShell showNavbar={false} className="h-screen" mainClassName="items-center justify-center">
        <span className="text-sm text-[hsl(var(--color-warning))]">{t('studio.novelNotFound')}</span>
      </PageShell>
    )
  }

  const wordCount = countWords(editMode ? editorContent : (chapter?.content ?? ''))
  const currentChapterIdentity = chapter ?? currentMeta ?? null
  const displayTitle = currentChapterIdentity ? getChapterDisplayTitle(currentChapterIdentity.title) : ''
  const activeChapterReference = currentChapterIdentity ? formatChapterBadgeLabel(currentChapterIdentity) : null

  return (
    <PageShell className="h-screen" navbarProps={{ position: 'static' }} mainClassName="min-h-0 flex-1 overflow-hidden">
      {showWorldOnboarding ? (
        <>
          <EmptyWorldOnboarding
            onGenerate={() => setWorldGenOpen(true)}
            onBootstrap={handleTriggerBootstrap}
            onDismiss={handleDismissWorldOnboarding}
            bootstrapPending={triggerBootstrap.isPending}
            bootstrapError={bootstrapError}
          />
          <WorldGenerationDialog novelId={novelId} open={worldGenOpen} onOpenChange={setWorldGenOpen} />
        </>
      ) : (
        <NovelShellLayout className="flex-1 min-h-0 p-3 gap-3 overflow-hidden">
          <NovelShellRail className="w-[280px] shrink-0 flex flex-col min-h-0 h-full rounded-[16px] border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-[24px] shadow-[var(--nw-copilot-panel-shadow)] overflow-hidden">
            <StudioNavigationRail
              novelTitle={novel.title}
              searchQuery={searchQuery}
              onSearchQueryChange={setSearchQuery}
              chapters={filteredChapters.map(c => ({
                chapterNumber: c.chapter_number,
                label: formatChapterLabel(c),
              }))}
              selectedChapterNumber={activeChapterNum}
              onSelectChapter={(chapterNumber) => {
                cancelAutoSave()
                setEditingTitle(false)
                setEditorContent('')
                setEditMode(false)
                setShowMoreActions(false)
                navigateToChapterStage(chapterNumber)
              }}
              chapterCount={chaptersMeta.length}
              onCreateChapter={handleCreateChapter}
              isCreating={createChapter.isPending}
              latestChapterReference={latestChapterReference}
              onContinuation={() => {
                // Save-first: if editing, flush autosave before switching stage
                if (editMode) {
                  saveNowAutoSave(editorContent)
                    .then(() => {
                      setEditMode(false)
                      navigateToWriteStage()
                    })
                    .catch(() => {
                      // Save failed — stay on chapter stage, user can retry
                    })
                } else {
                  navigateToWriteStage()
                }
              }}
              onOpenAtlas={() => {
                setShowMoreActions(false)
                navigateToAtlas()
              }}
              activeStage={activeStage}
            />
          </NovelShellRail>

          {/* ── Content Area ── */}
          <ArtifactStage className="flex-1 min-w-0 flex flex-col rounded-[16px] border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-[24px] shadow-[var(--nw-copilot-panel-shadow)] overflow-hidden">
            {hasResultsContext ? (
              <div className={activeStage === 'results' ? 'flex min-h-0 flex-1 flex-col' : 'hidden'}>
              <ContinuationResultsStage
                novelId={novelId}
                activeChapterNum={activeChapterNum}
                activeChapterReference={activeChapterReference}
                showInjectionSummaryRail={showInjectionSummaryRail}
                onToggleInjectionSummaryRail={() => {
                    const nextSearchParams = setNovelShellArtifactPanelSearchParams(
                      new URLSearchParams(location.search),
                      showInjectionSummaryRail ? null : injectionSummaryPanelState,
                    )
                    navigate(
                      { pathname: location.pathname, search: nextSearchParams.toString() },
                      { replace: true, state: resultsNavigationState },
                    )
                  }}
                  onDebugChange={handleResultsDebugChange}
                />
              </div>
            ) : null}

            {activeStage === 'results' ? null : activeStage === 'write' && latestChapterNum !== null ? (
              /* ── Write Stage ── */
              <ContinuationSetupStage
                novelId={novelId}
                chapterNum={latestChapterNum}
                chapterReference={latestChapterReference}
                instruction={continuationState.instruction}
                onInstructionChange={continuationState.setInstruction}
                selectedLength={continuationState.selectedLength}
                onSelectedLengthChange={continuationState.setSelectedLength}
                advancedOpen={continuationState.advancedOpen}
                onAdvancedOpenChange={continuationState.setAdvancedOpen}
                contextChapters={continuationState.contextChapters}
                onContextChaptersChange={continuationState.setContextChapters}
                numVersions={continuationState.numVersions}
                onNumVersionsChange={continuationState.setNumVersions}
                temperature={continuationState.temperature}
                onTemperatureChange={continuationState.setTemperature}
                onGenerate={continuationState.handleGenerate}
              />
            ) : activeStage === 'entity' ? (
              <StudioEntityStage
                novelId={novelId}
                entityId={effectiveStudioEntityId}
                onReturnToArtifact={hasResultsContext ? handleReturnToArtifact : undefined}
                onOpenCopilot={openEntityCopilot}
                onOpenAtlas={() => {
                  const nextParams = setAtlasSuggestionTargetSearchParams(new URLSearchParams(), {
                    resource: 'entity',
                    resource_id: effectiveStudioEntityId,
                    label: 'entity',
                    tab: 'entities',
                  })
                  navigateToAtlas(nextParams)
                }}
              />
            ) : activeStage === 'relationship' ? (
              <StudioRelationshipStage
                novelId={novelId}
                entityId={effectiveStudioEntityId}
                onReturnToArtifact={hasResultsContext ? handleReturnToArtifact : undefined}
                onOpenCopilot={openRelationshipCopilot}
                onOpenAtlas={() => {
                  const nextParams = setAtlasSuggestionTargetSearchParams(new URLSearchParams(), {
                    resource: 'relationship',
                    resource_id: effectiveStudioEntityId,
                    label: 'relationship',
                    tab: 'relationships',
                    entity_id: effectiveStudioEntityId,
                  })
                  navigateToAtlas(nextParams)
                }}
              />
            ) : activeStage === 'review' ? (
              <StudioDraftReviewStage
                novelId={novelId}
                reviewKind={routeState.reviewKind ?? 'entities'}
                onReviewKindChange={(kind) => navigateToReviewStage(kind, { replace: true })}
                onOpenEntity={(entityId) => navigateToEntityStage(entityId, { replace: true })}
                onOpenRelationships={(entityId) => navigateToRelationshipStage(entityId, { replace: true })}
                onOpenSystem={(systemId) => navigateToSystemStage(systemId, { replace: true })}
                onOpenAtlas={() => {
                  const nextParams = setAtlasReviewKindSearchParams(new URLSearchParams(), routeState.reviewKind ?? 'entities')
                  navigateToAtlas(nextParams)
                }}
                onReturnToArtifact={hasResultsContext ? handleReturnToArtifact : undefined}
              />
            ) : activeStage === 'system' ? (
              <StudioSystemStage
                novelId={novelId}
                systemId={effectiveStudioSystemId}
                onSelectSystem={(systemId) => navigateToSystemStage(systemId, { replace: true })}
                onOpenAtlas={() => {
                  const nextParams = setAtlasSuggestionTargetSearchParams(new URLSearchParams(), {
                    resource: 'system',
                    resource_id: effectiveStudioSystemId,
                    label: effectiveStudioSystemName ?? 'system',
                    tab: 'systems',
                  })
                  navigateToAtlas(nextParams)
                }}
                onReturnToArtifact={hasResultsContext ? handleReturnToArtifact : undefined}
              />
            ) : (
              /* ── Chapter Stage ── */
              <div className="flex-1 min-w-0 flex flex-col gap-6 px-8 py-8 lg:px-16 overflow-hidden">
                {/* Action Bar */}
                <div className="shrink-0 border-b border-[var(--nw-glass-border)] pb-5">
                  <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                    <div className="min-w-0 flex-1 space-y-3">
                      {currentMeta ? (
                        <>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="inline-flex items-center rounded-full border border-[var(--nw-glass-border)] bg-background/20 px-2.5 py-1 text-[11px] font-medium text-foreground/88">
                              {formatChapterBadgeLabel(currentChapterIdentity ?? currentMeta)}
                            </span>
                            <span className="inline-flex items-center rounded-full border border-[var(--nw-glass-border)] bg-background/20 px-2.5 py-1 text-[11px] text-muted-foreground">
                              {editMode ? t('studio.chapter.editing') : t('studio.chapter.reading')}
                            </span>
                          </div>

                          <div className="min-w-0">
                            {editingTitle ? (
                              <input
                                autoFocus
                                value={titleDraft}
                                onChange={e => setTitleDraft(e.target.value)}
                                onBlur={() => { handleTitleSave() }}
                                onKeyDown={e => { if (e.key === 'Enter') handleTitleSave(); if (e.key === 'Escape') setEditingTitle(false) }}
                                className="w-full max-w-[720px] font-mono text-[22px] font-semibold text-foreground bg-[var(--nw-glass-bg)] border border-[hsl(var(--accent)/0.35)] rounded-md px-2 py-1 outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-0"
                                placeholder={t('studio.chapter.titlePlaceholder')}
                              />
                            ) : (
                              <div
                                onDoubleClick={() => { setTitleDraft(displayTitle); setEditingTitle(true) }}
                                title={t('studio.chapter.titleEditHint')}
                                className="cursor-text"
                              >
                                {displayTitle ? (
                                  <h1 className="font-mono text-[24px] font-semibold leading-tight text-foreground break-words">
                                    {displayTitle}
                                  </h1>
                                ) : (
                                  <span className="text-[22px] text-muted-foreground italic">{t('studio.chapter.titleAddHint')}</span>
                                )}
                              </div>
                            )}
                          </div>

                          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
                            <span>{t('studio.chapter.charCount', { count: wordCount.toLocaleString() })}</span>
                            {currentMeta.created_at ? (
                              <span>{t('studio.chapter.updated', { time: formatRelativeTime(currentMeta.created_at) })}</span>
                            ) : null}
                          </div>
                        </>
                      ) : (
                        <div className="space-y-2">
                          <span className="inline-flex items-center rounded-full border border-[var(--nw-glass-border)] bg-background/20 px-2.5 py-1 text-[11px] text-muted-foreground">
                            {t('studio.header.workspace')}
                          </span>
                          <h1 className="font-mono text-[24px] font-semibold leading-tight text-foreground">
                            {t('studio.header.selectChapter')}
                          </h1>
                        </div>
                      )}
                    </div>

                    <div className="flex w-full flex-col gap-2.5 xl:w-auto xl:max-w-[520px] xl:items-end">
                      <div className="flex flex-wrap gap-2">
                        <NwButton
                          onClick={() => {
                            if (activeChapterNum === null) return
                            if (!editMode) {
                              setEditorContent(chapter?.content ?? '')
                              cancelAutoSave()
                            } else {
                              cancelAutoSave()
                            }
                            setEditMode(!editMode)
                          }}
                          disabled={activeChapterNum === null}
                          variant="accentOutline"
                          className="rounded-[10px] px-4 py-2 text-sm font-medium disabled:cursor-not-allowed"
                        >
                          <Pencil size={14} />
                          {t('studio.chapter.edit')}
                        </NwButton>

                        <div className="relative">
                          <NwButton
                            onClick={() => setShowMoreActions((prev) => !prev)}
                            variant="glass"
                            className="h-10 w-10 rounded-[10px] p-0 text-sm font-medium"
                            aria-haspopup="menu"
                            aria-expanded={showMoreActions}
                            aria-label={t('studio.actions.moreActions')}
                            title={t('studio.actions.moreActions')}
                          >
                            <MoreHorizontal size={14} />
                          </NwButton>

                          {showMoreActions ? (
                            <>
                              <div
                                className="fixed inset-0 z-10"
                                onClick={() => setShowMoreActions(false)}
                              />
                              <GlassSurface
                                variant="floating"
                                className="absolute right-0 top-[calc(100%+8px)] z-20 min-w-[188px] rounded-[16px] p-1.5"
                              >
                                <button
                                  type="button"
                                  onClick={() => {
                                    setShowMoreActions(false)
                                    handleExportAll()
                                  }}
                                  className="flex w-full items-center gap-2.5 rounded-[12px] px-3 py-2.5 text-left text-sm text-foreground transition-colors hover:bg-[var(--nw-glass-bg-hover)]"
                                >
                                  <Upload size={14} className="text-muted-foreground" />
                                  <span>{t('studio.actions.exportAllChapters')}</span>
                                </button>

                                {activeChapterNum !== null && chaptersMeta.length > 1 ? (
                                  <>
                                    <div className="mx-2 my-1 h-px bg-[var(--nw-glass-border)]" />
                                    <button
                                      type="button"
                                      onClick={() => {
                                        setShowMoreActions(false)
                                        handleDeleteChapter()
                                      }}
                                      className="flex w-full items-center gap-2.5 rounded-[12px] px-3 py-2.5 text-left text-sm text-[hsl(var(--color-danger))] transition-colors hover:bg-[hsl(var(--color-danger)/0.10)]"
                                    >
                                      <Trash2 size={14} />
                                      <span>{t('studio.chapter.delete')}</span>
                                    </button>
                                  </>
                                ) : null}
                              </GlassSurface>
                            </>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* ── Editor / Reader Area ── */}
                {editMode && activeChapterNum !== null ? (
                    <ChapterEditor
                      textareaRef={textareaRef}
                      value={editorContent}
                      onChange={handleEditorChange}
                      onSelectionChange={handleSelectionChange}
                      cursorInfo={cursorInfo}
                      autoSaveStatus={autoSaveStatus}
                      onUndo={handleUndo}
                      onRedo={handleRedo}
                      onCancel={handleCancelEdit}
                      onSave={handleSave}
                      warningTerms={editorWarningTerms}
                  />
                ) : (
                  <ChapterContent
                    isLoading={chapterLoading}
                    content={chapter?.content ?? null}
                    annotations={chapterDriftAnnotations}
                  />
                )}
              </div>
            )}
          </ArtifactStage>

          {showWorkbenchRail ? (
            <NovelCopilotDrawer novelId={novelId} onLocateTarget={handleStudioLocateTarget} />
          ) : showInjectionSummaryRail && resultsDebug ? (
            <NovelShellRail className="w-[360px] shrink-0 flex flex-col min-h-0 h-full rounded-[16px] border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-[24px] shadow-[var(--nw-copilot-panel-shadow)] overflow-hidden">
              <InjectionSummaryPanel
                debug={resultsDebug}
                activeCategory={injectionSummaryPanelState?.injectionCategory ?? undefined}
                onActiveCategoryChange={setInjectionSummaryCategory}
                onClose={() => navigate(
                  {
                    pathname: location.pathname,
                    search: setNovelShellArtifactPanelSearchParams(new URLSearchParams(location.search), null).toString(),
                  },
                  { replace: true, state: resultsNavigationState },
                )}
                onOpenAtlas={handleOpenInjectionCategory}
                onSelectItem={handleOpenInjectionItem}
              />
            </NovelShellRail>
          ) : (
            <NovelShellRail className="w-[360px] shrink-0 flex flex-col min-h-0 h-full rounded-[16px] border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-[24px] shadow-[var(--nw-copilot-panel-shadow)] overflow-hidden p-3">
              <StudioAssistantPanel
                novelId={novelId}
                activeChapterReference={activeChapterReference}
                latestChapterReference={latestChapterReference}
                chapterCount={chaptersMeta.length}
                contextualCopilotAction={contextualCopilotAction}
              />
            </NovelShellRail>
          )}
        </NovelShellLayout>
      )}
    </PageShell>
  )
}
