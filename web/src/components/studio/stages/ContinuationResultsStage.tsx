// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Check, RefreshCw, Upload, Info, ChevronDown, ChevronRight, Loader2, Settings, MessageSquarePlus } from 'lucide-react'
import { NwButton } from '@/components/ui/nw-button'
import { PlainTextContent, type TextAnnotation } from '@/components/ui/plain-text-content'
import { FeedbackForm, type FeedbackAnswers } from '@/components/feedback/FeedbackForm'
import { DriftWarningPopover } from '@/components/generation/DriftWarningPopover'
import { ProseWarningsPanel } from '@/components/generation/ProseWarningsPanel'
import { getWhitelist, addToWhitelist } from '@/lib/postcheckWhitelistStorage'
import { setActiveWarnings } from '@/lib/postcheckActiveWarningsStorage'
import { getLlmApiErrorMessage } from '@/lib/llmErrorMessages'
import { readGenerationResultsDebug, readGenerationResultsWarnings, saveGenerationResultsDebug } from '@/lib/generationResultsDebugStorage'
import { useCreateChapter } from '@/hooks/novel/useCreateChapter'
import {
  setResultsProvenanceSearchParams,
} from '@/components/novel-shell/NovelShellRouteState'
import { api, streamContinuation, ApiError } from '@/services/api'
import { useAuth } from '@/contexts/AuthContext'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { downloadTextFile } from '@/lib/downloadTextFile'
import { cn } from '@/lib/utils'
import type { ContinueDebugSummary, ContinueRequest, ContinueResponse, Continuation, PostcheckWarning, ProseWarning } from '@/types/api'

interface VariantState {
  content: string
  continuationId: number | null
  isStreaming: boolean
  error: string | null
}

export function ContinuationResultsStage({
  novelId,
  activeChapterNum,
  activeChapterReference,
  showInjectionSummaryRail,
  onToggleInjectionSummaryRail,
  onDebugChange,
}: {
  novelId: number
  activeChapterNum: number | null
  activeChapterReference?: string | null
  showInjectionSummaryRail: boolean
  onToggleInjectionSummaryRail: () => void
  onDebugChange: (debug: ContinueDebugSummary | null) => void
}) {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, refreshQuota } = useAuth()
  const { t } = useUiLocale()
  const state = location.state as {
    streamParams?: ContinueRequest
    novelId?: number
    response?: ContinueResponse
    studioResultsDebug?: ContinueDebugSummary | null
  } | null

  const legacyResponse = state?.response
  const legacyVersions: Continuation[] = legacyResponse?.continuations ?? []

  const searchParams = new URLSearchParams(location.search)
  const persisted = searchParams.get('continuations')
  const [persistedVersions, setPersistedVersions] = useState<Continuation[] | null>(null)
  const [persistedDebug, setPersistedDebug] = useState<ContinueDebugSummary | null>(null)
  const [persistedError, setPersistedError] = useState<string | null>(null)
  const [reloadAttempt, setReloadAttempt] = useState(0)

  const initialStreamRef = useRef<
    | {
        novelId: number
        params: ContinueRequest
      }
    | null
    | undefined
  >(undefined)
  if (initialStreamRef.current === undefined) {
    initialStreamRef.current =
      !persisted && state?.streamParams && state?.novelId
        ? { novelId: state.novelId, params: state.streamParams }
        : null
  }
  const streamCtx = initialStreamRef.current

  const [variants, setVariants] = useState<VariantState[]>([])
  const [activeTab, setActiveTab] = useState(0)
  const [isDone, setIsDone] = useState(false)
  const [streamError, setStreamError] = useState<string | null>(null)
  const [isQuotaExhausted, setIsQuotaExhausted] = useState(false)
  const [showFeedbackForm, setShowFeedbackForm] = useState(false)
  const [feedbackSubmitting, setFeedbackSubmitting] = useState(false)
  const [streamDebug, setStreamDebug] = useState<ContinueDebugSummary | null>(null)
  const [streamAttempt, setStreamAttempt] = useState(0)
  const abortRef = useRef(false)
  const abortCtrlRef = useRef<AbortController | null>(null)
  const continuationMapRef = useRef<Map<number, number>>(new Map())
  const totalVariantsRef = useRef<number>(0)
  const latestLocationRef = useRef({ pathname: location.pathname, search: location.search })
  latestLocationRef.current = { pathname: location.pathname, search: location.search }

  const isStreamMode = streamCtx != null
  const nonStreamVersions = persistedVersions ?? legacyVersions
  const isLegacyMode = !isStreamMode && nonStreamVersions.length > 0
  const isReloadMode = !isStreamMode && legacyVersions.length === 0 && !!persisted

  const [reloadedWarnings, setReloadedWarnings] = useState<PostcheckWarning[]>([])
  const [whitelist, setWhitelist] = useState<string[]>(() => getWhitelist(novelId))
  const createChapter = useCreateChapter(novelId)

  const handleDismissTerm = useCallback((term: string) => {
    addToWhitelist(novelId, term)
    setWhitelist((prev) => [...prev, term])
  }, [novelId])

  const driftAnnotations: TextAnnotation[] = useMemo(() => {
    let warnings: PostcheckWarning[] | undefined
    if (isStreamMode) {
      if (!isDone) return []
      warnings = streamDebug?.drift_warnings
    } else if (legacyResponse?.debug?.drift_warnings?.length) {
      warnings = legacyResponse.debug.drift_warnings
    } else if (reloadedWarnings.length > 0) {
      warnings = reloadedWarnings
    }
    if (!warnings?.length) return []

    const targetVersion = activeTab + 1
    return warnings
      .filter((warning) => (warning.version == null || warning.version === targetVersion) && !whitelist.includes(warning.term))
      .map((warning) => ({
        id: `drift-${warning.code}-${warning.term}`,
        term: warning.term,
        className: 'nw-drift-highlight',
        renderPopover: ({ onClose }: { onClose: () => void }) => (
          <DriftWarningPopover
            code={warning.code}
            term={warning.term}
            onDismiss={() => {
              handleDismissTerm(warning.term)
              onClose()
            }}
          />
        ),
      }))
  }, [activeTab, handleDismissTerm, isDone, isStreamMode, legacyResponse?.debug, reloadedWarnings, streamDebug, whitelist])

  useEffect(() => {
    if (!streamCtx) return

    abortRef.current = false
    abortCtrlRef.current?.abort()
    const ctrl = new AbortController()
    abortCtrlRef.current = ctrl

    continuationMapRef.current = new Map()
    totalVariantsRef.current = 0
    setVariants([])
    setActiveTab(0)
    setIsDone(false)
    setStreamError(null)
    setStreamDebug(null)
    setIsQuotaExhausted(false)
    setShowFeedbackForm(false)

    const consume = async () => {
      try {
        for await (const event of streamContinuation(streamCtx.novelId, streamCtx.params, { signal: ctrl.signal })) {
          if (abortRef.current || ctrl.signal.aborted) break

          switch (event.type) {
            case 'start':
              totalVariantsRef.current = event.total_variants
              if ('debug' in event) setStreamDebug((event as { debug: ContinueDebugSummary }).debug)
              setVariants(
                Array.from({ length: event.total_variants }, () => ({
                  content: '',
                  continuationId: null,
                  isStreaming: true,
                  error: null,
                })),
              )
              break
            case 'token':
              setVariants((prev) => prev.map((variant, index) => (
                index === event.variant
                  ? { ...variant, content: variant.content + event.content }
                  : variant
              )))
              break
            case 'variant_done':
              continuationMapRef.current.set(event.variant, event.continuation_id)
              setVariants((prev) => prev.map((variant, index) => (
                index === event.variant
                  ? {
                      ...variant,
                      content: event.content ?? variant.content,
                      continuationId: event.continuation_id,
                      isStreaming: false,
                      error: null,
                    }
                  : variant
              )))
              break
            case 'done': {
              setIsDone(true)
              const doneDebug = 'debug' in event ? (event as { debug: ContinueDebugSummary }).debug : null
              if (doneDebug) setStreamDebug(doneDebug)

              const total = totalVariantsRef.current
              const entries = Array.from(continuationMapRef.current.entries()).sort((a, b) => a[0] - b[0])
              const mapping = entries.map(([variant, id]) => `${variant}:${id}`).join(',')

              if (mapping && total && activeChapterNum !== null) {
                if (doneDebug) saveGenerationResultsDebug(mapping, doneDebug)

                const currentSearchParams = new URLSearchParams(latestLocationRef.current.search)
                const currentStage = currentSearchParams.get('stage')
                let nextSearchParams = new URLSearchParams(currentSearchParams)

                if (currentStage === 'results' || currentStage == null) {
                  nextSearchParams = setResultsProvenanceSearchParams(nextSearchParams, null)
                  nextSearchParams.set('continuations', mapping)
                  nextSearchParams.set('total_variants', String(total))
                } else {
                  nextSearchParams = setResultsProvenanceSearchParams(nextSearchParams, {
                    chapterNum: activeChapterNum,
                    continuations: mapping,
                    totalVariants: total,
                  })
                }
                navigate(
                  {
                    pathname: latestLocationRef.current.pathname,
                    search: nextSearchParams.toString(),
                  },
                  { replace: true, state: null },
                )
              }
              break
            }
            case 'error':
              if (event.variant != null) {
                setVariants((prev) => prev.map((variant, index) => (
                  index === event.variant
                    ? { ...variant, error: event.message, isStreaming: false }
                    : variant
                )))
              } else {
                setStreamError(event.message)
              }
              break
          }
        }
      } catch (err) {
        if (abortRef.current || ctrl.signal.aborted) return
        if (err instanceof ApiError && err.status === 429) {
          setIsQuotaExhausted(true)
          setStreamError(t('continuation.results.quotaExhausted'))
        } else if (err instanceof ApiError) {
          const llmMessage = getLlmApiErrorMessage(err)
          if (llmMessage) {
            setStreamError(llmMessage)
          } else if (err.status === 503) {
            setStreamError(t('continuation.results.serviceBusy'))
          } else {
            setStreamError(t('continuation.results.requestFailed', { status: err.status }))
          }
        } else {
          setStreamError(err instanceof Error ? err.message : 'Stream failed')
        }
      }
    }

    void consume()
    return () => {
      abortRef.current = true
      ctrl.abort()
    }
  }, [activeChapterNum, navigate, streamAttempt, streamCtx, t])

  useEffect(() => {
    if (!isReloadMode || !persisted) return

    const storedDebug = readGenerationResultsDebug(persisted)
    setPersistedDebug(storedDebug)
    setReloadedWarnings(readGenerationResultsWarnings(persisted))

    const ids = persisted
      .split(',')
      .map((pair) => pair.trim())
      .filter(Boolean)
      .map((pair) => {
        const [, idRaw] = pair.split(':')
        return Number.parseInt((idRaw ?? '').trim(), 10)
      })
      .filter((id) => Number.isFinite(id))

    if (ids.length === 0) {
      setPersistedError('Invalid continuation link')
      return
    }

    setPersistedVersions(null)
    setPersistedError(null)
    api.getContinuations(novelId, ids)
      .then(setPersistedVersions)
      .catch((err) => setPersistedError(err instanceof Error ? err.message : 'Failed to load continuations'))
  }, [isReloadMode, novelId, persisted, reloadAttempt])

  const currentVariant = isStreamMode ? variants[activeTab] : undefined
  const currentLegacyVersion = isLegacyMode ? nonStreamVersions[activeTab] : undefined
  const currentContent = currentVariant?.content ?? currentLegacyVersion?.content ?? ''
  const allDone = isLegacyMode || isDone
  const tabCount = isStreamMode ? variants.length : nonStreamVersions.length

  const debug = isStreamMode ? streamDebug : legacyResponse?.debug ?? persistedDebug ?? state?.studioResultsDebug ?? null
  const summary = debug
    ? {
        entities: debug.injected_entities.length,
        relationships: debug.injected_relationships.length,
        systems: debug.injected_systems.length,
      }
    : null

  useEffect(() => {
    onDebugChange(debug)
  }, [debug, onDebugChange])

  const handleAdopt = useCallback(() => {
    if (!currentContent) return
    createChapter.mutate(
      { content: currentContent },
      {
        onSuccess: (chapter) => {
      const currentDebug = isStreamMode ? streamDebug : legacyResponse?.debug ?? persistedDebug ?? state?.studioResultsDebug ?? null
      const allWarnings = currentDebug?.drift_warnings ?? (reloadedWarnings.length > 0 ? reloadedWarnings : undefined)
      if (allWarnings?.length) {
        const targetVersion = activeTab + 1
        const activeWarnings = allWarnings.filter(
          (warning) => (warning.version == null || warning.version === targetVersion) && !whitelist.includes(warning.term),
        )
        if (activeWarnings.length > 0) {
          setActiveWarnings(novelId, chapter.chapter_number, activeWarnings, chapter.created_at)
        }
      }
      navigate(`/novel/${novelId}?chapter=${chapter.chapter_number}`, { state: null })
        },
      },
    )
  }, [
    activeTab,
    createChapter,
    currentContent,
    isStreamMode,
    legacyResponse?.debug,
    navigate,
    novelId,
    persistedDebug,
    reloadedWarnings,
    state?.studioResultsDebug,
    streamDebug,
    whitelist,
  ])

  const handleExportAll = () => {
    const versions = isStreamMode ? variants : nonStreamVersions
    if (versions.length === 0) return
    const content = versions
      .map((variant, index) => `${t('continuation.results.exportVersionHeader', { n: index + 1 })}\n\n${variant.content}\n`)
      .join('\n\n')
    downloadTextFile(`continuation_versions_${new Date().toISOString().slice(0, 10)}.txt`, content)
  }

  const handleFeedbackSubmit = async (answers: FeedbackAnswers) => {
    setFeedbackSubmitting(true)
    try {
      await api.submitFeedback(answers)
      await refreshQuota()
      setShowFeedbackForm(false)
      setIsQuotaExhausted(false)
      setStreamError(null)
      setStreamAttempt((value) => value + 1)
    } finally {
      setFeedbackSubmitting(false)
    }
  }

  if (!isStreamMode && !isLegacyMode) {
    if (isReloadMode && !persistedError && !persistedVersions) {
      return (
        <div className="flex flex-1 items-center justify-center flex-col gap-4">
          <Loader2 size={24} className="animate-spin text-muted-foreground" />
          <span className="text-sm text-muted-foreground">{t('continuation.results.loading')}</span>
        </div>
      )
    }

    if (isReloadMode && persistedError) {
      return (
        <div className="flex flex-1 items-center justify-center flex-col gap-4">
          <span className="text-sm text-destructive">{persistedError}</span>
          <div className="flex items-center gap-3">
            <NwButton
              onClick={() => setReloadAttempt((value) => value + 1)}
              variant="accent"
              className="rounded-[10px] px-5 py-2.5 text-sm font-semibold shadow-[0_0_18px_hsl(var(--accent)/0.25)]"
            >
              {t('continuation.results.retry')}
            </NwButton>
            <NwButton
              onClick={() => navigate(`/novel/${novelId}`, { state: null })}
              variant="glass"
              className="rounded-[10px] px-5 py-2.5 text-sm font-semibold"
            >
              {t('continuation.results.back')}
            </NwButton>
          </div>
        </div>
      )
    }

    return (
      <div className="flex flex-1 items-center justify-center flex-col gap-4">
        <span className="text-sm text-muted-foreground">{t('continuation.results.noResults')}</span>
        <NwButton
          onClick={() => navigate(`/novel/${novelId}`, { state: null })}
          variant="accent"
          className="rounded-[10px] px-5 py-2.5 text-sm font-semibold shadow-[0_0_18px_hsl(var(--accent)/0.25)]"
        >
          {t('continuation.results.returnToWorkspace')}
        </NwButton>
      </div>
    )
  }

  if (streamError) {
    return (
      <>
        <div className="flex flex-1 items-center justify-center flex-col gap-5">
          <span className="text-base font-semibold text-destructive">{streamError}</span>

          {isQuotaExhausted && !user?.feedback_submitted ? (
            <div className="flex flex-col items-center gap-3 max-w-md text-center">
              <p className="text-sm text-muted-foreground">{t('continuation.results.quotaFeedback')}</p>
              <NwButton
                onClick={() => setShowFeedbackForm(true)}
                variant="accent"
                className="rounded-[10px] px-6 py-2.5 text-sm font-semibold shadow-[0_0_18px_hsl(var(--accent)/0.25)]"
              >
                <MessageSquarePlus size={16} />
                {t('continuation.results.submitFeedbackUnlock')}
              </NwButton>
            </div>
          ) : null}

          {isQuotaExhausted && user?.feedback_submitted ? (
            <div className="flex flex-col items-center gap-3 max-w-md text-center">
              <p className="text-sm text-muted-foreground">{t('continuation.results.feedbackAlreadyClaimed')}</p>
              <NwButton
                onClick={() => navigate('/settings')}
                variant="accent"
                className="rounded-[10px] px-6 py-2.5 text-sm font-semibold shadow-[0_0_18px_hsl(var(--accent)/0.25)]"
              >
                <Settings size={16} />
                {t('continuation.results.goToSettings')}
              </NwButton>
            </div>
          ) : null}

          {!isQuotaExhausted ? (
            <div className="flex items-center gap-3">
              <NwButton
                onClick={() => setStreamAttempt((value) => value + 1)}
                variant="accent"
                className="rounded-[10px] px-5 py-2.5 text-sm font-semibold shadow-[0_0_18px_hsl(var(--accent)/0.25)]"
              >
                {t('continuation.results.retry')}
              </NwButton>
              <NwButton
                onClick={() => navigate(`/novel/${novelId}?stage=write`, { state: null })}
                variant="glass"
                className="rounded-[10px] px-5 py-2.5 text-sm font-semibold"
              >
                {t('continuation.results.back')}
              </NwButton>
            </div>
          ) : null}

          {isQuotaExhausted ? (
            <NwButton
              onClick={() => navigate(`/novel/${novelId}`, { state: null })}
              variant="glass"
              className="rounded-[10px] px-5 py-2.5 text-sm font-semibold"
            >
              {t('continuation.results.returnToWorkspace')}
            </NwButton>
          ) : null}
        </div>

        {showFeedbackForm ? (
          <FeedbackForm
            onSubmit={handleFeedbackSubmit}
            onCancel={() => setShowFeedbackForm(false)}
            submitting={feedbackSubmitting}
          />
        ) : null}
      </>
    )
  }

  return (
    <>
      <div className="flex-1 min-w-0 flex flex-col gap-5 px-8 py-6 lg:px-12 overflow-hidden">
        <div className="shrink-0 border-b border-[var(--nw-glass-border)] pb-4">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
            <div className="min-w-0 space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center rounded-full border border-[var(--nw-glass-border)] bg-background/20 px-2.5 py-1 text-[11px] font-medium text-foreground/88">
                  {t('continuation.results.badge')}
                </span>
                {activeChapterNum !== null ? (
                <span className="inline-flex items-center rounded-full border border-[var(--nw-glass-border)] bg-background/20 px-2.5 py-1 text-[11px] text-muted-foreground">
                    {t('continuation.results.continuationOf', { chapter: activeChapterReference ?? `Ch. ${activeChapterNum}` })}
                  </span>
                ) : null}
                {isStreamMode && !isDone ? (
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-[hsl(var(--accent)/0.3)] bg-[hsl(var(--accent)/0.08)] px-2.5 py-1 text-[11px] text-accent">
                    <Loader2 size={10} className="animate-spin" />
                    {t('continuation.results.generating')}
                  </span>
                ) : null}
              </div>
            </div>

            <div className="flex items-center gap-2.5 flex-wrap justify-end">
              <NwButton
                data-testid="results-adopt-button"
                onClick={handleAdopt}
                disabled={createChapter.isPending || !currentContent || !allDone}
                variant="accent"
                className="rounded-[10px] px-5 py-2.5 text-sm font-semibold shadow-[0_0_18px_hsl(var(--accent)/0.25)] disabled:cursor-default"
              >
                <Check size={16} />
                {t('continuation.results.adopt')}
              </NwButton>

              <NwButton
                onClick={() => navigate(`/novel/${novelId}?stage=write`, { state: null })}
                variant="glass"
                className="rounded-[10px] px-4 py-2 text-sm font-medium"
              >
                <RefreshCw size={14} />
                {t('continuation.results.regenerate')}
              </NwButton>

              <NwButton
                onClick={handleExportAll}
                disabled={!allDone}
                variant="glass"
                className="rounded-[10px] px-4 py-2 text-sm font-medium"
              >
                <Upload size={14} />
                {t('continuation.results.exportAll')}
              </NwButton>
            </div>
          </div>
        </div>

        {tabCount > 0 ? (
          <div className="shrink-0 flex items-center">
            {Array.from({ length: tabCount }, (_, index) => {
              const variant = isStreamMode ? variants[index] : undefined
              const isActive = index === activeTab
              const isVariantStreaming = variant?.isStreaming
              const isVariantDone = isLegacyMode || variant?.continuationId != null
              const hasError = variant?.error

              return (
                <button
                  key={index}
                  type="button"
                  onClick={() => setActiveTab(index)}
                  className={cn(
                    'px-6 py-2.5 text-sm border-b-2 transition-colors flex items-center gap-2',
                    isActive
                      ? 'border-b-accent text-foreground font-semibold'
                      : 'border-b-transparent text-muted-foreground hover:text-foreground',
                  )}
                >
                  {t('continuation.results.version', { n: index + 1 })}
                  {isVariantStreaming ? <Loader2 size={14} className="animate-spin" /> : null}
                  {hasError ? <span className="text-destructive text-xs">!</span> : null}
                  {isVariantDone && !isVariantStreaming && !hasError && isStreamMode ? (
                    <Check size={14} className="text-green-500" />
                  ) : null}
                </button>
              )
            })}
          </div>
        ) : null}

        {isStreamMode ? (
          !currentVariant ? (
            <div className="flex-1 min-h-0 flex items-center justify-center">
              <Loader2 size={24} className="animate-spin text-muted-foreground" />
            </div>
          ) : currentVariant.error ? (
            <div className="flex-1 min-h-0 flex items-center justify-center">
              <div className="flex flex-col items-center gap-3">
                <span className="text-sm text-destructive">{currentVariant.error}</span>
                <NwButton
                  onClick={() => setStreamAttempt((value) => value + 1)}
                  variant="accent"
                  className="rounded-[10px] px-5 py-2.5 text-sm font-semibold shadow-[0_0_18px_hsl(var(--accent)/0.25)]"
                >
                  {t('continuation.results.retry')}
                </NwButton>
              </div>
            </div>
          ) : currentVariant.content ? (
            <PlainTextContent
              content={currentVariant.content}
              className="flex-1 min-h-0 overflow-y-auto nw-scrollbar-thin"
              emptyLabel={t('continuation.results.emptyContent')}
              annotations={driftAnnotations}
            />
          ) : currentVariant.isStreaming || !currentVariant.continuationId ? (
            <div className="flex-1 min-h-0 flex items-center justify-center">
              <Loader2 size={24} className="animate-spin text-muted-foreground" />
            </div>
          ) : (
            <PlainTextContent
              content=""
              className="flex-1 min-h-0 overflow-y-auto nw-scrollbar-thin"
              emptyLabel={t('continuation.results.emptyContent')}
            />
          )
        ) : (
          <PlainTextContent
            content={currentLegacyVersion?.content}
            className="flex-1 min-h-0 overflow-y-auto nw-scrollbar-thin"
            emptyLabel={t('continuation.results.emptyContent')}
            annotations={driftAnnotations}
          />
        )}

        {summary ? (
          <button
            type="button"
            onClick={onToggleInjectionSummaryRail}
            className={cn(
              'shrink-0 rounded-[10px] border px-4 py-3 flex items-center justify-between gap-3 text-left transition-colors',
              showInjectionSummaryRail
                ? 'border-[hsl(var(--accent)/0.3)] bg-[hsl(var(--accent)/0.06)]'
                : 'border-[var(--nw-glass-border)] bg-[hsl(var(--background)/0.35)] hover:bg-[hsl(var(--background)/0.45)]',
            )}
          >
            <div className="flex items-center gap-2 min-w-0">
              <Info size={14} className={showInjectionSummaryRail ? 'text-accent' : 'text-muted-foreground'} />
              <span className={cn('text-xs truncate', showInjectionSummaryRail ? 'text-accent' : 'text-muted-foreground')}>
                {t('continuation.results.injectionSummary', { entities: summary.entities, relationships: summary.relationships, systems: summary.systems })}
              </span>
            </div>
            {showInjectionSummaryRail ? (
              <ChevronDown size={14} className="text-accent shrink-0" />
            ) : (
              <ChevronRight size={14} className="text-muted-foreground shrink-0" />
            )}
          </button>
        ) : null}

        {(() => {
          const proseWarnings: ProseWarning[] | undefined = isStreamMode
            ? (isDone ? streamDebug?.prose_warnings : undefined)
            : (legacyResponse?.debug?.prose_warnings ?? persistedDebug?.prose_warnings ?? state?.studioResultsDebug?.prose_warnings)
          const targetVersion = activeTab + 1
          const filtered = proseWarnings?.filter((w) => w.version == null || w.version === targetVersion) ?? []
          if (filtered.length === 0) return null
          return (
            <ProseWarningsPanel warnings={filtered} />
          )
        })()}
      </div>

      {showFeedbackForm ? (
        <FeedbackForm
          onSubmit={handleFeedbackSubmit}
          onCancel={() => setShowFeedbackForm(false)}
          submitting={feedbackSubmitting}
        />
      ) : null}
    </>
  )
}
