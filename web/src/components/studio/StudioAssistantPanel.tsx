import { BookOpen, Bot, Sparkles } from 'lucide-react'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { cn } from '@/lib/utils'
import { WorldBuildPanel } from '@/components/world-model/shared/WorldBuildPanel'

export function StudioAssistantPanel({
  novelId,
  activeChapterReference,
  latestChapterReference,
  chapterCount,
  contextualCopilotAction,
  className,
}: {
  novelId: number
  activeChapterReference: string | null
  latestChapterReference: string | null
  chapterCount: number
  contextualCopilotAction?: {
    title: string
    description: string
    onClick: () => void
  }
  className?: string
}) {
  const { t } = useUiLocale()
  const focusLabel = activeChapterReference ?? t('studio.assistant.waitingSelectChapter')
  const continuationLabel =
    latestChapterReference === null
      ? t('studio.assistant.noContinuationEntry')
      : t('studio.assistant.latestContinuation', { chapter: latestChapterReference })

  return (
    <div className={cn('flex h-full min-h-0 flex-col gap-3', className)} data-testid="studio-assistant-rail">
      <div className="relative overflow-hidden rounded-[24px] border border-[var(--nw-glass-border)] bg-[linear-gradient(160deg,hsl(var(--background)/0.16),transparent_72%)] px-4 py-4 shadow-[0_10px_30px_rgba(15,23,42,0.10)]">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,hsl(var(--accent)/0.18),transparent_36%),radial-gradient(circle_at_bottom_left,hsl(var(--accent)/0.10),transparent_42%)]" />
        <div className="relative">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[18px] border border-[hsl(var(--accent)/0.24)] bg-[hsl(var(--accent)/0.12)] text-[hsl(var(--accent))] shadow-[0_8px_18px_hsl(var(--accent)/0.14)]">
              <Bot className="h-4.5 w-4.5" />
            </div>
            <div className="min-w-0">
              <div className="text-[10px] font-semibold uppercase tracking-[0.26em] text-muted-foreground/72">
                Studio
              </div>
              <h2 className="mt-1 text-[16px] font-semibold tracking-[0.01em] text-foreground">
                {t('studio.assistant.title')}
              </h2>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-2.5">
            <div className="rounded-[18px] border border-[var(--nw-glass-border)] bg-background/20 px-3 py-3">
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-muted-foreground/70">
                <BookOpen className="h-3.5 w-3.5" />
                {t('studio.assistant.currentFocus')}
              </div>
              <div className="mt-2 text-sm font-medium text-foreground">{focusLabel}</div>
              <div className="mt-1 text-[11px] text-muted-foreground/76">{t('studio.assistant.chapterSwitchCount', { count: chapterCount })}</div>
            </div>
            <div className="rounded-[18px] border border-[var(--nw-glass-border)] bg-background/20 px-3 py-3">
              <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-muted-foreground/70">
                <Sparkles className="h-3.5 w-3.5" />
                {t('studio.assistant.continuationEntry')}
              </div>
              <div className="mt-2 text-sm font-medium text-foreground">{continuationLabel}</div>
              <div className="mt-1 text-[11px] text-muted-foreground/76">{t('studio.assistant.quickSwitch')}</div>
            </div>
          </div>
        </div>
      </div>

      <div className="nw-scrollbar-thin min-h-0 flex-1 overflow-y-auto pr-1">
        {contextualCopilotAction ? (
          <button
            type="button"
            onClick={contextualCopilotAction.onClick}
            className="mb-3 w-full rounded-[24px] border border-[var(--nw-glass-border)] bg-[linear-gradient(160deg,hsl(var(--accent)/0.12),transparent_78%)] px-4 py-4 text-left shadow-[0_10px_30px_rgba(15,23,42,0.08)] transition-colors hover:bg-[linear-gradient(160deg,hsl(var(--accent)/0.18),transparent_78%)]"
          >
            <div className="flex items-start gap-3">
              <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-[16px] border border-[hsl(var(--accent)/0.28)] bg-[hsl(var(--accent)/0.14)] text-[hsl(var(--accent))]">
                <Sparkles className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-muted-foreground/72">
                  Copilot
                </div>
                <div className="mt-1 text-sm font-semibold text-foreground">
                  {contextualCopilotAction.title}
                </div>
                <div className="mt-1 text-[12px] leading-5 text-muted-foreground/82">
                  {contextualCopilotAction.description}
                </div>
              </div>
            </div>
          </button>
        ) : null}
        <WorldBuildPanel novelId={novelId} variant="compact" />
      </div>
    </div>
  )
}
