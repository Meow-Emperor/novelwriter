import type React from 'react'
import { useEffect, useState, useRef, useCallback } from 'react'
import { Bot, RotateCcw, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { getCopilotScopeLabel } from './novelCopilotHelpers'
import { useNovelCopilot } from './NovelCopilotContext'
import type { CopilotSuggestionTarget } from '@/types/copilot'
import {
  useOptionalNovelShell,
} from '@/components/novel-shell/NovelShellContext'
import {
  clampNovelShellDrawerWidth,
  DEFAULT_NOVEL_SHELL_DRAWER_WIDTH,
} from '@/components/novel-shell/novelShellChromeState'
import { NovelCopilotComposer } from './NovelCopilotComposer'
import { NovelCopilotQuickActions } from './NovelCopilotQuickActions'
import { NovelCopilotResearchProcess } from './NovelCopilotResearchProcess'
import { NovelCopilotSuggestionCard } from './NovelCopilotSuggestionCard'
import { AiStatusPill } from './AiStatusPill'
import { NovelCopilotSessionStrip } from './NovelCopilotSessionStrip'
import { getCopilotWorkbenchMeta } from './novelCopilotWorkbench'
import {
  copilotDrawerShellClassName,
  copilotHighlightLineClassName,
  copilotPanelClassName,
  copilotPanelMutedClassName,
  copilotPanelStrongClassName,
  copilotPillClassName,
  copilotPillInteractiveClassName,
} from './novelCopilotChrome'

const sectionPanelClassName =
  `${copilotPanelClassName} rounded-[24px] p-4`
const dashedPanelClassName =
  `${copilotPanelMutedClassName} rounded-[22px] border-dashed px-4 py-4 text-center text-sm text-muted-foreground`

export function NovelCopilotDrawer({
  onLocateTarget,
}: {
  novelId: number
  onLocateTarget?: (target: CopilotSuggestionTarget) => void
}) {
  const {
    isOpen,
    closeDrawer,
    sessions,
    focusedSessionId,
    focusSession,
    removeSession,
    focusedSession,
    activeRun,
    getSessionRun,
    getSessionRuns,
    submitPrompt,
    retryInterruptedRun,
    applySuggestions,
    dismissSuggestions,
  } = useNovelCopilot()
  const shell = useOptionalNovelShell()
  const focusedSessionMeta =
    focusedSessionId == null
      ? null
      : sessions.find((session) => session.sessionId === focusedSessionId) ?? null

  // Keep the drawer cold until there is an actual focused session. This avoids
  // eager world-data fanout on pages that only mount the shell-level drawer.
  if (!isOpen || !focusedSessionMeta) return null

  const activeFocusedSessionId = focusedSessionMeta.sessionId

  return (
    <ActiveNovelCopilotDrawer
      onLocateTarget={onLocateTarget}
      shell={shell}
      closeDrawer={closeDrawer}
      sessions={sessions}
      focusedSessionId={activeFocusedSessionId}
      focusSession={focusSession}
      removeSession={removeSession}
      focusedSessionMeta={focusedSessionMeta}
      focusedSession={focusedSession}
      activeRun={activeRun}
      getSessionRun={getSessionRun}
      getSessionRuns={getSessionRuns}
      submitPrompt={submitPrompt}
      retryInterruptedRun={retryInterruptedRun}
      applySuggestions={applySuggestions}
      dismissSuggestions={dismissSuggestions}
    />
  )
}

function ActiveNovelCopilotDrawer({
  onLocateTarget,
  shell,
  closeDrawer,
  sessions,
  focusedSessionId,
  focusSession,
  removeSession,
  focusedSessionMeta,
  focusedSession,
  activeRun,
  getSessionRun,
  getSessionRuns,
  submitPrompt,
  retryInterruptedRun,
  applySuggestions,
  dismissSuggestions,
}: {
  onLocateTarget?: (target: CopilotSuggestionTarget) => void
  shell: ReturnType<typeof useOptionalNovelShell>
  closeDrawer: () => void
  sessions: ReturnType<typeof useNovelCopilot>['sessions']
  focusedSessionId: string
  focusSession: ReturnType<typeof useNovelCopilot>['focusSession']
  removeSession: ReturnType<typeof useNovelCopilot>['removeSession']
  focusedSessionMeta: ReturnType<typeof useNovelCopilot>['sessions'][number]
  focusedSession: ReturnType<typeof useNovelCopilot>['focusedSession']
  activeRun: ReturnType<typeof useNovelCopilot>['activeRun']
  getSessionRun: ReturnType<typeof useNovelCopilot>['getSessionRun']
  getSessionRuns: ReturnType<typeof useNovelCopilot>['getSessionRuns']
  submitPrompt: ReturnType<typeof useNovelCopilot>['submitPrompt']
  retryInterruptedRun: ReturnType<typeof useNovelCopilot>['retryInterruptedRun']
  applySuggestions: ReturnType<typeof useNovelCopilot>['applySuggestions']
  dismissSuggestions: ReturnType<typeof useNovelCopilot>['dismissSuggestions']
}) {
  const { locale, t } = useUiLocale()
  const [fallbackDrawerWidth, setFallbackDrawerWidth] = useState(DEFAULT_NOVEL_SHELL_DRAWER_WIDTH)
  const [isDragging, setIsDragging] = useState(false)
  const [retryingRunId, setRetryingRunId] = useState<string | null>(null)
  const setFallbackDrawerWidthClamped = useCallback((nextWidth: number) => {
    setFallbackDrawerWidth(clampNovelShellDrawerWidth(nextWidth))
  }, [])
  const drawerWidth = shell?.shellState.drawerWidth ?? fallbackDrawerWidth
  const setDrawerWidth = shell?.shellState.setDrawerWidth ?? setFallbackDrawerWidthClamped
  const isDraggingRef = useRef(false)
  const startXRef = useRef(0)
  const startWidthRef = useRef(DEFAULT_NOVEL_SHELL_DRAWER_WIDTH)
  const drawerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeDrawer()
    }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [closeDrawer])

  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    e.preventDefault()
    e.stopPropagation()
    isDraggingRef.current = true
    setIsDragging(true)
    startXRef.current = e.clientX
    startWidthRef.current = drawerWidth
    document.body.style.cursor = 'ew-resize'
    document.body.style.userSelect = 'none'
  }, [drawerWidth])

  useEffect(() => {
    const handlePointerMove = (e: PointerEvent) => {
      if (!isDraggingRef.current) return
      const delta = startXRef.current - e.clientX
      let newWidth = startWidthRef.current + delta
      // Cap at 50% of parent width (atlas-design-spec §Spatial Zone Contracts)
      const parentWidth = drawerRef.current?.parentElement?.clientWidth
      if (parentWidth) newWidth = Math.min(newWidth, parentWidth * 0.5)
      setDrawerWidth(newWidth)
    }
    const handlePointerUp = () => {
      if (isDraggingRef.current) {
        isDraggingRef.current = false
        setIsDragging(false)
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
      }
    }
    document.addEventListener('pointermove', handlePointerMove)
    document.addEventListener('pointerup', handlePointerUp)
    return () => {
      document.removeEventListener('pointermove', handlePointerMove)
      document.removeEventListener('pointerup', handlePointerUp)
    }
  }, [setDrawerWidth])

  const session = focusedSession ?? focusedSessionMeta
  const workbenchMeta = getCopilotWorkbenchMeta(session.prefill, session.displayTitle, locale)
  const quickActionPrompts = Object.fromEntries(
    workbenchMeta.quickActions.map((action) => [action.id, action.prompt]),
  )

  const handleAction = (action: string) => {
    void submitPrompt(
      session.sessionId,
      quickActionPrompts[action] ?? t('copilot.drawer.fallbackPrompt'),
      session.prefill.scope,
      session.prefill.context,
      action,
    )
  }

  const handleSubmit = (prompt: string) => {
    void submitPrompt(session.sessionId, prompt, session.prefill.scope, session.prefill.context)
  }

  const scopeLabel = getCopilotScopeLabel(session.prefill, locale)
  const sessionRuns = getSessionRuns(session.sessionId)
  const focusedStatus =
    activeRun?.status === 'queued' || activeRun?.status === 'running'
      ? 'running'
      : activeRun?.status === 'error' || activeRun?.status === 'interrupted'
        ? 'error'
        : 'connected'
  const isFocusedSessionBusy = activeRun?.status === 'queued' || activeRun?.status === 'running'

  const handleRetryInterruptedRun = useCallback((runId: string) => {
    if (retryingRunId === runId || isFocusedSessionBusy) return

    setRetryingRunId(runId)
    void retryInterruptedRun(session.sessionId, runId).finally(() => {
      setRetryingRunId((current) => (current === runId ? null : current))
    })
  }, [isFocusedSessionBusy, retryInterruptedRun, retryingRunId, session.sessionId])

  return (
    <>
      <div
        ref={drawerRef}
        className={cn(
          'relative shrink-0 flex flex-col overflow-hidden transition-none border-l',
          copilotDrawerShellClassName,
          'shadow-[var(--nw-copilot-shell-shadow)]'
        )}
        style={{ width: drawerWidth, transition: isDragging ? 'none' : 'width 0.3s cubic-bezier(0.19,1,0.22,1)' }}
        data-testid="novel-copilot-drawer"
        data-state="open"
        aria-hidden={false}
      >
        <div
          className="absolute left-0 top-0 bottom-0 w-1.5 cursor-ew-resize hover:bg-[hsl(var(--accent)/0.15)] active:bg-[hsl(var(--accent)/0.3)] z-50 transition-colors"
          onPointerDown={handlePointerDown}
        />

        <div className="absolute inset-0 bg-[var(--nw-copilot-shell-bg)]" />

        <div className="relative flex h-full flex-col">
          <div className="shrink-0 border-b border-[var(--nw-copilot-border)] bg-[linear-gradient(180deg,hsl(var(--background)/0.16),transparent)]">
            <div className="relative flex items-center justify-between gap-4 px-5 py-3">
              <div className={cn('pointer-events-none absolute inset-x-5 top-0 h-px opacity-80', copilotHighlightLineClassName)} />
              <div className="min-w-0">
                <div className="flex min-w-0 items-center gap-3">
                  <div className={cn('flex h-9 w-9 shrink-0 items-center justify-center rounded-[18px] text-foreground/82', copilotPanelStrongClassName)}>
                    <Bot className="h-4 w-4" />
                  </div>
                  <div className="min-w-0">
                    <h2 className="text-sm font-medium tracking-[0.01em] text-foreground/90">Novel Copilot</h2>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5">
                      <AiStatusPill status={focusedStatus} />
                      <span className={cn('inline-flex items-center rounded-full px-2 py-0.5 text-[9px] font-medium uppercase tracking-[0.16em] text-muted-foreground/80', copilotPillClassName)}>
                        {scopeLabel}
                      </span>
                      <span className={cn('inline-flex items-center rounded-full px-2 py-0.5 text-[10px] text-muted-foreground/75', copilotPillClassName)}>
                        {t('copilot.drawer.sessionsCount', { count: sessions.length })}
                      </span>
                    </div>
                    <div className="mt-1.5 truncate text-[11px] text-muted-foreground/70">
                      {t('copilot.drawer.currentWorkspace', { title: session.displayTitle })}
                    </div>
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={closeDrawer}
                className={cn(
                  'inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-[18px] text-muted-foreground hover:text-foreground',
                  copilotPillInteractiveClassName,
                )}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          <NovelCopilotSessionStrip
            sessions={sessions}
            focusedSessionId={focusedSessionId}
            getSessionStatus={(sessionId) => getSessionRun(sessionId)?.status ?? null}
            onFocusSession={focusSession}
            onRemoveSession={removeSession}
          />

          <div className="nw-scrollbar-thin flex-1 overflow-y-auto px-4 py-4">
            {sessionRuns.length === 0 && (
              <div className="animate-in fade-in duration-700">
                <div className="px-1">
                  <div className="text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground/70">
                    {workbenchMeta.introEyebrow}
                  </div>
                  <div className="mt-1 text-[11px] leading-4 text-muted-foreground/76">
                    {workbenchMeta.introTitle}
                  </div>
                </div>
                <NovelCopilotQuickActions
                  actions={workbenchMeta.quickActions}
                  onAction={handleAction}
                  compact
                  disabled={isFocusedSessionBusy}
                />
              </div>
            )}

            {sessionRuns.length > 0 && (
              <div className="animate-in flex flex-col justify-end space-y-4 fade-in slide-in-from-bottom-2 duration-500">
                {sessionRuns.map((run, index) => {
                  const isLatestRun = index === sessionRuns.length - 1
                  const pendingSuggestions = run.suggestions.filter((suggestion) => suggestion.status === 'pending')
                  const appliedSuggestions = run.suggestions.filter((suggestion) => suggestion.status === 'applied')

                  return (
                    <div key={run.run_id} className="space-y-4" data-testid={`copilot-run-${run.run_id}`}>
                      {!isLatestRun && <div className="mx-12 border-t border-[var(--nw-copilot-border)]/60" />}

                      <div className="flex justify-end">
                        <div className={cn(copilotPanelStrongClassName, 'max-w-[88%] rounded-[24px] rounded-tr-md px-4 py-3')}>
                          <div className="mb-1 text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground/70">
                            {isLatestRun ? t('copilot.drawer.currentRequest') : t('copilot.drawer.previousRequest')}
                          </div>
                          <div className="text-[13px] leading-relaxed text-foreground/95">{run.prompt}</div>
                        </div>
                      </div>

                      {run.status === 'interrupted' && (
                        <div
                          className={cn(
                            copilotPanelMutedClassName,
                            'rounded-[22px] border-[hsl(var(--color-danger)/0.22)] px-4 py-3 [background:linear-gradient(160deg,hsl(var(--color-danger)/0.08),transparent)]',
                          )}
                        >
                          <div className="flex flex-col gap-3">
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <div className="text-[10px] font-medium uppercase tracking-[0.18em] text-[hsl(var(--color-danger))]/85">
                                  {t('copilot.drawer.interrupted')}
                                </div>
                                <div className="mt-1 text-[13px] leading-relaxed text-[hsl(var(--color-danger))]">
                                  {run.error ?? t('copilot.drawer.interruptedFallback')}
                                </div>
                              </div>
                              {isLatestRun && (
                                <button
                                  type="button"
                                  onClick={() => handleRetryInterruptedRun(run.run_id)}
                                  disabled={isFocusedSessionBusy || retryingRunId === run.run_id}
                                  className={cn(
                                    'inline-flex shrink-0 items-center gap-2 rounded-full px-3 py-2 text-[11px] font-medium tracking-[0.01em] text-foreground/85 disabled:cursor-not-allowed disabled:opacity-55',
                                    copilotPillInteractiveClassName,
                                  )}
                                >
                                  <RotateCcw className={cn('h-3.5 w-3.5', retryingRunId === run.run_id && 'animate-spin')} />
                                  {retryingRunId === run.run_id ? t('copilot.drawer.retryingInterrupted') : t('copilot.drawer.retryInterrupted')}
                                </button>
                              )}
                            </div>
                            {isLatestRun && (
                              <div className="flex items-start justify-between gap-3 text-[11px] leading-relaxed text-muted-foreground/72">
                                <span>
                                  {t('copilot.drawer.retryHint')}
                                </span>
                              </div>
                            )}
                          </div>
                        </div>
                      )}

                      {run.status === 'error' && (
                        <div className={cn(dashedPanelClassName, 'border-[hsl(var(--color-danger)/0.22)] text-[hsl(var(--color-danger))] [background:linear-gradient(160deg,hsl(var(--color-danger)/0.08),transparent)]')}>
                          {run.error ?? t('copilot.drawer.errorFallback')}
                        </div>
                      )}

                      {run.status === 'completed' && run.answer && (
                        <div className={cn(copilotPanelClassName, 'rounded-[22px] rounded-tl-md px-4 py-3')}>
                          <div className="mb-1 text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground/70">
                            {t('copilot.drawer.analysisResult')}
                          </div>
                          <div className="whitespace-pre-wrap text-[13px] leading-relaxed text-foreground/90">{run.answer}</div>
                        </div>
                      )}

                      {(run.trace?.length > 0 || run.evidence?.length > 0) && (
                        <NovelCopilotResearchProcess trace={run.trace} evidence={run.evidence} />
                      )}

                      {run.status === 'completed' && pendingSuggestions.length > 0 && (
                        <section className={sectionPanelClassName}>
                          <div className="mb-3 flex items-center justify-between gap-3 px-1">
                            <h3 className="text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground/80">
                              {t('copilot.drawer.suggestions')}
                            </h3>
                            <div className="text-[10px] font-medium tracking-[0.05em] text-muted-foreground/60">{t('copilot.drawer.pendingSuggestions', { count: pendingSuggestions.length })}</div>
                          </div>
                          <div className="space-y-3">
                            {pendingSuggestions.map((s) => (
                              <NovelCopilotSuggestionCard
                                key={s.suggestion_id}
                                suggestion={s}
                                onApply={(id) => void applySuggestions(session.sessionId, run.run_id, [id])}
                                onDismiss={(id) => void dismissSuggestions(session.sessionId, run.run_id, [id])}
                                onLocateTarget={onLocateTarget}
                              />
                            ))}
                          </div>
                        </section>
                      )}

                      {run.status === 'completed' && appliedSuggestions.length > 0 && (
                        <section className={sectionPanelClassName}>
                          <div className="mb-3 flex items-center justify-between gap-3 px-1">
                            <h3 className="text-[10px] font-medium uppercase tracking-[0.2em] text-foreground/70">
                              {t('copilot.drawer.applied')}
                            </h3>
                            <div className="text-[10px] font-medium tracking-[0.05em] text-muted-foreground/60">{t('copilot.drawer.appliedSuggestions', { count: appliedSuggestions.length })}</div>
                          </div>
                          <div className="space-y-3">
                            {appliedSuggestions.map((s) => (
                              <NovelCopilotSuggestionCard
                                key={s.suggestion_id}
                                suggestion={s}
                                mode="applied"
                                onApply={() => undefined}
                                onDismiss={() => undefined}
                                onLocateTarget={onLocateTarget}
                              />
                            ))}
                          </div>
                        </section>
                      )}

                      {run.status === 'completed' && pendingSuggestions.length === 0 && appliedSuggestions.length === 0 && !run.answer && (
                        <div className={dashedPanelClassName}>{t('copilot.drawer.noSuggestions')}</div>
                      )}

                      {run.status === 'completed' && pendingSuggestions.length === 0 && appliedSuggestions.length > 0 && (
                        <div className={dashedPanelClassName}>
                          {t('copilot.drawer.allHandled')}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          <div className="shrink-0 border-t border-[var(--nw-copilot-border)] bg-[linear-gradient(180deg,hsl(var(--foreground)/0.03),transparent)] p-4">
            <NovelCopilotComposer
              onSubmit={handleSubmit}
              disabled={isFocusedSessionBusy}
              label={workbenchMeta.composerLabel}
              placeholder={workbenchMeta.composerPlaceholder}
            />
          </div>
        </div>
      </div>
    </>
  )
}
