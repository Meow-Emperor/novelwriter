import { Sparkles, Bot, Search } from 'lucide-react'
import { cn } from '@/lib/utils'
import { WorldGenerationDialog } from '@/components/world-model/shared/WorldGenerationDialog'
import { BootstrapPanel } from '@/components/world-model/shared/BootstrapPanel'
import { useState } from 'react'
import { useNovelCopilot } from './NovelCopilotContext'
import { useOptionalNovelShell } from '@/components/novel-shell/NovelShellContext'
import { buildWholeBookCopilotLaunchArgs } from './novelCopilotLauncher'
import { useNovelWindowIndex } from '@/hooks/novel/useNovelWindowIndex'
import { getWindowIndexCopilotStatusMeta } from '@/lib/windowIndexStatus'
import {
  copilotHighlightLineClassName,
  copilotPanelClassName,
  copilotPillClassName,
  copilotPillInteractiveClassName,
} from './novelCopilotChrome'

export function NovelCopilotCard({
  novelId,
  className,
  variant = 'default',
}: {
  novelId: number
  className?: string
  variant?: 'default' | 'compact'
}) {
  const [genOpen, setGenOpen] = useState(false)
  const copilot = useNovelCopilot()
  const shell = useOptionalNovelShell()
  const { data: indexState } = useNovelWindowIndex(novelId)
  const compact = variant === 'compact'
  const indexStatusMeta = getWindowIndexCopilotStatusMeta(indexState)
  const indexStatusClassName = indexStatusMeta.tone === 'warning'
    ? 'text-[hsl(var(--color-warning))]'
    : 'text-muted-foreground/72'

  return (
    <div className={cn('space-y-3', className)} data-testid="world-build-panel">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-[11px] font-medium tracking-wide text-foreground/78 uppercase">
          <Bot className="h-3.5 w-3.5" /> AI 工具
        </div>
      </div>

      <div className={cn('group relative overflow-hidden rounded-[24px]', copilotPanelClassName)}>
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_left,var(--nw-copilot-glow-1),transparent_65%)] [mix-blend-mode:var(--nw-copilot-glow-blend)] opacity-[calc(var(--nw-copilot-glow-op)*0.8)] transition-opacity duration-500 group-hover:opacity-[var(--nw-copilot-glow-op)]" />
        <div className={cn('pointer-events-none absolute inset-x-5 top-0 h-px opacity-80', copilotHighlightLineClassName)} />

        <div className="divide-y divide-[var(--nw-glass-border)] relative z-10">
          <div className={cn('bg-gradient-to-r from-transparent to-[hsl(var(--accent)/0.03)]', compact ? 'p-3.5' : 'p-4')}>
            <div className={cn('flex items-center justify-between gap-3', compact ? 'mb-2.5' : 'mb-3')}>
              <div>
                <div className="text-[10px] font-semibold tracking-wider text-muted-foreground uppercase">研究工作台</div>
                {!compact ? (
                  <div className="mt-1 text-[11px] text-muted-foreground/72">
                    从全书视角检索设定缺口、潜在线索与值得进一步研究的世界锚点。
                  </div>
                ) : null}
                <div className={`mt-1 text-[10px] ${indexStatusClassName}`}>
                  {indexStatusMeta.text}
                </div>
              </div>
              <span className={cn('inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium text-muted-foreground', copilotPillClassName)}>
                全书探索
              </span>
            </div>
            <button
              type="button"
              onClick={() => copilot.openDrawer(...buildWholeBookCopilotLaunchArgs(shell?.routeState))}
              className={cn(
                'flex w-full items-center gap-3 text-left text-xs text-foreground transition-all',
                compact ? 'rounded-[16px] px-3 py-2.5' : 'rounded-[18px] px-3.5 py-3',
                copilotPillInteractiveClassName,
                'shadow-[0_14px_28px_rgba(15,23,42,0.08)]',
              )}
              data-testid="novel-copilot-trigger"
            >
              <div className={cn(
                'flex shrink-0 items-center justify-center bg-[hsl(var(--accent)/0.12)] text-[hsl(var(--accent))] ring-1 ring-[hsl(var(--accent)/0.25)] shadow-[0_4px_12px_rgba(0,0,0,0.08)]',
                compact ? 'h-9 w-9 rounded-[14px]' : 'h-10 w-10 rounded-2xl',
              )}>
                <Search className="h-4 w-4 shrink-0" />
              </div>
              <div className="flex-1">
                <div className="font-semibold text-foreground">Novel Copilot</div>
                <div className="mt-0.5 text-[10px] text-muted-foreground/80">
                  {compact ? '全书探索与上下文研究' : '跨章节研究世界状态、设定缺口与潜在线索'}
                </div>
              </div>
            </button>
          </div>

          <div className={compact ? 'p-3.5' : 'p-4'}>
            <div className="mb-2 text-[10px] font-semibold tracking-wider text-muted-foreground uppercase">批量生成与初始化</div>
            <div className="space-y-1.5">
              <button
                type="button"
                onClick={() => setGenOpen(true)}
                className={cn(
                  'flex w-full items-center gap-3 rounded-[16px] px-3 py-2.5 text-left text-xs text-muted-foreground transition-colors',
                  copilotPillInteractiveClassName,
                  'hover:text-foreground',
                )}
                data-testid="world-build-generate"
              >
                <Sparkles className="h-4 w-4 shrink-0 opacity-80 text-[hsl(var(--accent))]" />
                <span className="flex-1">{compact ? '从设定生成' : '从设定文本生成 (大段输入)'}</span>
              </button>

              <BootstrapPanel novelId={novelId} variant="sidebar" />
            </div>
          </div>
        </div>
      </div>

      <WorldGenerationDialog novelId={novelId} open={genOpen} onOpenChange={setGenOpen} />
    </div>
  )
}
