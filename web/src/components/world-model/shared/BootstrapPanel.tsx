import { useEffect, useRef, useState } from 'react'
import { BookOpen, ChevronRight } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import '@/lib/uiMessagePacks/novel'
import { useBootstrapStatus, useTriggerBootstrap } from '@/hooks/world/useBootstrap'
import { useNovelWindowIndex } from '@/hooks/novel/useNovelWindowIndex'
import { worldKeys } from '@/hooks/world/keys'
import { useToast } from '@/components/world-model/shared/useToast'
import { getLlmApiErrorMessage } from '@/lib/llmErrorMessages'
import { getWindowIndexBootstrapStatusMeta } from '@/lib/windowIndexStatus'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { ApiError } from '@/services/api'
import type { BootstrapStatus, BootstrapTriggerRequest } from '@/types/api'

const TOTAL_STEPS = 5

const INITIAL_EXTRACTION_PAYLOAD: BootstrapTriggerRequest = { mode: 'initial' }

const REEXTRACT_PAYLOAD: BootstrapTriggerRequest = {
  mode: 'reextract',
  draft_policy: 'replace_bootstrap_drafts',
  force: true,
}

function isRunning(status: BootstrapStatus): boolean {
  return ['pending', 'tokenizing', 'extracting', 'windowing', 'refining'].includes(status)
}

function isTerminal(status: BootstrapStatus): boolean {
  return status === 'completed' || status === 'failed'
}

type BootstrapPanelVariant = 'sidebar' | 'page'

export function BootstrapPanel({ novelId, variant = 'sidebar' }: { novelId: number; variant?: BootstrapPanelVariant }) {
  const { locale, t } = useUiLocale()
  const { data: job, isLoading } = useBootstrapStatus(novelId)
  const { data: indexState } = useNovelWindowIndex(novelId)
  const trigger = useTriggerBootstrap(novelId)
  const { toast } = useToast()
  const qc = useQueryClient()
  const previousStatusRef = useRef<BootstrapStatus | null>(null)
  const [reextractConfirmOpen, setReextractConfirmOpen] = useState(false)
  const initializedFallback = Boolean(
    job && (
      job.mode === 'initial' ||
      job.mode === 'reextract' ||
      (job.status === 'completed' && !job.result.index_refresh_only)
    )
  )
  const isInitialized = Boolean(job?.initialized ?? initializedFallback)
  const indexStatusMeta = getWindowIndexBootstrapStatusMeta(indexState, locale)
  const indexStatusClassName = indexStatusMeta.tone === 'warning'
    ? 'text-[hsl(var(--color-warning))]'
    : 'text-muted-foreground/75'
  const stepLabels: Record<string, string> = {
    pending: t('worldModel.bootstrap.step.pending'),
    tokenizing: t('worldModel.bootstrap.step.tokenizing'),
    extracting: t('worldModel.bootstrap.step.extracting'),
    windowing: t('worldModel.bootstrap.step.windowing'),
    refining: t('worldModel.bootstrap.step.refining'),
  }

  const renderRowCopy = (options?: { summary?: string | null }) => (
    <span className="flex flex-1 flex-col text-left">
      <span>{t('worldModel.bootstrap.extractFromChapters')}</span>
      {options?.summary ? (
        <span className="text-[11px] opacity-70">{options.summary}</span>
      ) : null}
      <span className={`text-[10px] ${indexStatusClassName}`}>{indexStatusMeta.text}</span>
    </span>
  )

  useEffect(() => {
    const previousStatus = previousStatusRef.current
    const currentStatus = job?.status ?? null
    previousStatusRef.current = currentStatus

    if (!currentStatus || !isTerminal(currentStatus)) return
    if (previousStatus && isTerminal(previousStatus)) return

    qc.invalidateQueries({ queryKey: worldKeys.entities(novelId) })
    qc.invalidateQueries({ queryKey: worldKeys.relationships(novelId) })
  }, [job?.status, novelId, qc])

  const handleTrigger = (payload: BootstrapTriggerRequest) => {
    trigger.mutate(payload, {
      onError: (err) => {
        if (err instanceof ApiError) {
          const llmMessage = getLlmApiErrorMessage(err, locale)
          if (llmMessage) {
            toast(llmMessage)
            return
          }
          if (err.code === 'bootstrap_already_running') {
            toast(t('worldModel.common.processing'))
          } else if (err.code === 'bootstrap_no_text') {
            toast(t('worldModel.bootstrap.noText'))
          } else {
            toast(t('worldModel.bootstrap.triggerFailed'))
          }
        } else {
          toast(t('worldModel.bootstrap.triggerFailed'))
        }
      },
    })
  }

  const handleInitialExtraction = () => {
    handleTrigger(INITIAL_EXTRACTION_PAYLOAD)
  }

  const handleReextract = () => {
    setReextractConfirmOpen(true)
  }

  const handleConfirmReextract = () => {
    if (trigger.isPending) return
    setReextractConfirmOpen(false)
    handleTrigger(REEXTRACT_PAYLOAD)
  }

  const reextractConfirmDialog = (
    <ConfirmDialog
      open={reextractConfirmOpen}
      tone="destructive"
      title={t('worldModel.bootstrap.confirmTitle')}
      description={t('worldModel.bootstrap.confirmDescription')}
      confirmText={t('worldModel.bootstrap.confirmAction')}
      onConfirm={handleConfirmReextract}
      onClose={() => setReextractConfirmOpen(false)}
    />
  )

  // ── Sidebar variant: inline row that lives inside WorldBuildPanel card ──
  if (variant === 'sidebar') {
    if (isLoading) {
      return (
        <div className="px-3 py-2.5">
          <div className="h-4 w-32 rounded bg-[hsl(var(--foreground)/0.10)] animate-pulse" />
        </div>
      )
    }

    // Running
    if (job && isRunning(job.status)) {
      const progress = job.progress.step / TOTAL_STEPS
      const stepLabel = stepLabels[job.status] ?? job.progress.detail
      return (
        <div className="px-3 py-2.5 space-y-1.5">
          <div className="flex items-center gap-2">
            <BookOpen className="h-4 w-4 shrink-0 opacity-70 text-muted-foreground" />
            <span className="text-xs text-muted-foreground flex-1">{stepLabel}</span>
          </div>
          <div className="h-1 rounded-full bg-[hsl(var(--foreground)/0.10)] overflow-hidden">
            <div
              className="h-full rounded-full bg-accent animate-pulse transition-all duration-500"
              style={{ width: `${Math.max(progress * 100, 5)}%` }}
            />
          </div>
        </div>
      )
    }

    // Failed
    if (job?.status === 'failed') {
      const handleFailedAction = isInitialized ? handleReextract : handleInitialExtraction
      return (
        <>
          <button
            type="button"
            onClick={handleFailedAction}
            disabled={trigger.isPending}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-xs text-muted-foreground transition-colors hover:bg-[var(--nw-glass-bg-hover)] hover:text-foreground disabled:opacity-50 disabled:pointer-events-none"
          >
            <BookOpen className="h-4 w-4 shrink-0 opacity-70" />
            <span className="flex flex-1 flex-col text-left">
              <span className="text-[hsl(var(--color-warning))]">{t('worldModel.bootstrap.failed')} · {t('worldModel.common.retry')}</span>
              <span className={`text-[10px] ${indexStatusClassName}`}>{indexStatusMeta.text}</span>
            </span>
            <ChevronRight className="h-3.5 w-3.5 shrink-0 opacity-40" />
          </button>
          {reextractConfirmDialog}
        </>
      )
    }

    // Completed
    if (job?.status === 'completed') {
      const summary = job.result.index_refresh_only
        ? t('worldModel.bootstrap.completedIndexRefresh')
        : t('worldModel.bootstrap.summaryCounts', {
          entities: job.result.entities_found,
          relationships: job.result.relationships_found,
        })
      return (
        <>
          <button
            type="button"
            onClick={handleReextract}
            disabled={trigger.isPending}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-xs text-muted-foreground transition-colors hover:bg-[var(--nw-glass-bg-hover)] hover:text-foreground disabled:opacity-50 disabled:pointer-events-none"
          >
            <BookOpen className="h-4 w-4 shrink-0 opacity-70" />
            {renderRowCopy({ summary })}
            <ChevronRight className="h-3.5 w-3.5 shrink-0 opacity-40" />
          </button>
          {reextractConfirmDialog}
        </>
      )
    }

    // Idle (no job)
    return (
      <>
        <button
          type="button"
          onClick={handleInitialExtraction}
          disabled={trigger.isPending}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-xs text-muted-foreground transition-colors hover:bg-[var(--nw-glass-bg-hover)] hover:text-foreground disabled:opacity-50 disabled:pointer-events-none"
        >
          <BookOpen className="h-4 w-4 shrink-0 opacity-70" />
          {renderRowCopy()}
          <ChevronRight className="h-3.5 w-3.5 shrink-0 opacity-40" />
        </button>
        {reextractConfirmDialog}
      </>
    )
  }

  // ── Page variant: unchanged ──

  const renderPrimaryAction = (primaryVariant: 'default' | 'outline' = 'default') => (
    <div className="flex items-center gap-2 ml-auto">
      {isInitialized ? (
        <Button
          size="sm"
          variant={primaryVariant}
          className="h-7 text-xs text-muted-foreground hover:text-foreground"
          onClick={handleReextract}
          disabled={trigger.isPending}
        >
          {t('worldModel.bootstrap.reextractDrafts')}
        </Button>
      ) : (
        <Button size="sm" variant={primaryVariant} className="h-7 text-xs" onClick={handleInitialExtraction} disabled={trigger.isPending}>
          {t('worldModel.bootstrap.extractFromChapters')}
        </Button>
      )}
    </div>
  )

  const shellClass = 'px-4 py-2 border-b border-[var(--nw-glass-border)]'

  if (isLoading) {
    return (
      <div className={shellClass}>
        <div className="h-5 w-40 rounded bg-[hsl(var(--foreground)/0.10)] animate-pulse" />
      </div>
    )
  }

  if (job && isRunning(job.status)) {
    const progress = job.progress.step / TOTAL_STEPS
    const stepLabel = stepLabels[job.status] ?? job.progress.detail
    return (
      <div className={shellClass + ' space-y-1'}>
        <div className="flex items-center gap-3">
          <div className="flex-1 h-1.5 rounded-full bg-[hsl(var(--foreground)/0.10)] overflow-hidden">
            <div
              className="h-full rounded-full bg-accent animate-pulse transition-all duration-500"
              style={{ width: `${Math.max(progress * 100, 5)}%` }}
            />
          </div>
          <Button size="sm" variant="ghost" disabled className="h-7 text-xs">
            {t('worldModel.common.processing')}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">{stepLabel}</p>
      </div>
    )
  }

  if (job?.status === 'failed') {
    return (
      <>
        <div className={shellClass + ' flex items-center gap-3'}>
          <div className="flex flex-col gap-0.5">
            <span className="text-xs text-[hsl(var(--color-warning))]">{t('worldModel.bootstrap.failed')}</span>
            <span className={`text-[11px] ${indexStatusClassName}`}>{indexStatusMeta.text}</span>
          </div>
          {renderPrimaryAction('outline')}
        </div>
        {reextractConfirmDialog}
      </>
    )
  }

  if (job?.status === 'completed') {
    const completionText = job.result.index_refresh_only
      ? t('worldModel.bootstrap.completedIndexRefresh')
      : t('worldModel.bootstrap.summaryCounts', {
        entities: job.result.entities_found,
        relationships: job.result.relationships_found,
      })
    return (
      <>
        <div className={shellClass + ' flex items-center gap-3'}>
          <div className="flex flex-col gap-0.5">
            <span className="text-xs text-muted-foreground">{completionText}</span>
            <span className={`text-[11px] ${indexStatusClassName}`}>{indexStatusMeta.text}</span>
          </div>
          {renderPrimaryAction('outline')}
        </div>
        {reextractConfirmDialog}
      </>
    )
  }

  return (
    <>
      <div className={shellClass + ' flex items-center gap-3'}>
        <span className={`text-xs flex-1 ${indexStatusClassName}`}>{indexStatusMeta.text}</span>
        {renderPrimaryAction()}
      </div>
      {reextractConfirmDialog}
    </>
  )
}
