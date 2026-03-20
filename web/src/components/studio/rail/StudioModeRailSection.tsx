import '@/lib/uiMessagePacks/novel'
import { Globe, PenTool } from 'lucide-react'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { cn } from '@/lib/utils'
import type { NovelShellStage } from '@/components/novel-shell/NovelShellRouteState'

export function StudioModeRailSection({
  activeStage,
  latestChapterReference,
  onContinuation,
  onOpenAtlas,
}: {
  activeStage: NovelShellStage | null
  latestChapterReference: string | null
  onContinuation: () => void
  onOpenAtlas: () => void
}) {
  const { t } = useUiLocale()

  return (
    <section className="space-y-2" data-testid="studio-rail-modes">
      <div className="px-2 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
        {t('studio.rail.workspace')}
      </div>

      <div className="space-y-1.5">
        {latestChapterReference !== null ? (
          <button
            type="button"
            onClick={onContinuation}
            data-testid="studio-rail-continuation"
            className={cn(
              'w-full rounded-[14px] border px-3 py-3 text-left transition-all',
              'flex items-start gap-3',
              activeStage === 'write'
                ? 'border-accent/25 bg-accent/10 text-accent shadow-sm'
                : 'border-[var(--nw-glass-border)] bg-background/15 text-foreground/85 hover:bg-foreground/5',
            )}
          >
            <PenTool size={16} className="mt-0.5 shrink-0" />
            <div className="min-w-0">
              <div className="text-[13px] font-medium">{t('studio.rail.continuationTitle')}</div>
              <div className="mt-0.5 text-[11px] text-muted-foreground">
                {t('studio.rail.continuationDescription', { chapter: latestChapterReference })}
              </div>
            </div>
          </button>
        ) : null}

        <button
          type="button"
          onClick={onOpenAtlas}
          className={cn(
            'w-full rounded-[14px] border border-[var(--nw-glass-border)] bg-background/15 px-3 py-3 text-left transition-all',
            'flex items-start gap-3 text-foreground/85 hover:bg-foreground/5',
          )}
        >
          <Globe size={16} className="mt-0.5 shrink-0" />
          <div className="min-w-0">
            <div className="text-[13px] font-medium">{t('studio.rail.atlasTitle')}</div>
            <div className="mt-0.5 text-[11px] text-muted-foreground">
              {t('studio.rail.atlasDescription')}
            </div>
          </div>
        </button>
      </div>
    </section>
  )
}
