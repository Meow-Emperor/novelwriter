import { Bot } from 'lucide-react'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { cn } from '@/lib/utils'
import { WorldBuildPanel } from '@/components/world-model/shared/WorldBuildPanel'

export function StudioAssistantPanel({
  novelId,
  contextualCopilotAction,
  className,
}: {
  novelId: number
  contextualCopilotAction?: {
    title: string
    description: string
    onClick: () => void
  }
  className?: string
}) {
  const { t } = useUiLocale()

  return (
    <div className={cn('flex h-full min-h-0 flex-col', className)} data-testid="studio-assistant-rail">
      <div className="nw-scrollbar-thin min-h-0 flex-1 overflow-y-auto pr-1 space-y-1.5">
        {contextualCopilotAction ? (
          <button
            type="button"
            onClick={contextualCopilotAction.onClick}
            className="flex w-full items-center gap-3 rounded-[14px] border border-[var(--nw-glass-border)] bg-background/20 px-3 py-2.5 text-left transition-colors hover:bg-[var(--nw-glass-bg-hover)]"
          >
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] border border-[var(--nw-glass-border)] bg-background/20 text-muted-foreground">
              <Bot className="h-3.5 w-3.5" />
            </div>
            <div className="min-w-0">
              <div className="text-[13px] font-medium text-foreground">
                {contextualCopilotAction.title}
              </div>
              <div className="mt-0.5 text-[11px] leading-4 text-muted-foreground/80">
                {contextualCopilotAction.description}
              </div>
            </div>
          </button>
        ) : null}
        <WorldBuildPanel novelId={novelId} variant="compact" />
      </div>
    </div>
  )
}
