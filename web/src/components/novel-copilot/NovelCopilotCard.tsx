import { ChevronRight, Globe, Search, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { WorldGenerationDialog } from '@/components/world-model/shared/WorldGenerationDialog'
import { BootstrapPanel } from '@/components/world-model/shared/BootstrapPanel'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { useNovelCopilot } from './NovelCopilotContext'
import { useOptionalNovelShell } from '@/components/novel-shell/NovelShellContext'
import { buildWholeBookCopilotLaunchArgs } from './novelCopilotLauncher'
import { useNovelWindowIndex } from '@/hooks/novel/useNovelWindowIndex'
import { useWorldEntities } from '@/hooks/world/useEntities'
import { useWorldRelationships } from '@/hooks/world/useRelationships'
import { useWorldSystems } from '@/hooks/world/useSystems'
import { getWindowIndexCopilotStatusMeta } from '@/lib/windowIndexStatus'
import {
  getCopilotResearchStatusClassName,
} from './novelCopilotChrome'
import { setAtlasStudioOriginSearchParams } from '@/components/novel-shell/NovelShellRouteState'

function ActionStrip({
  icon: Icon,
  title,
  description,
  onClick,
  testId,
  compact = false,
  current = false,
}: {
  icon: typeof Search
  title: string
  description: string
  onClick?: () => void
  testId?: string
  compact?: boolean
  current?: boolean
}) {
  const content = (
    <>
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] border border-[var(--nw-glass-border)] bg-background/20 text-muted-foreground">
        <Icon className="h-3.5 w-3.5" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-medium text-foreground">{title}</div>
        <div className="mt-0.5 text-[11px] leading-4 text-muted-foreground/80">
          {description}
        </div>
      </div>
      <ChevronRight className={cn('h-3.5 w-3.5 shrink-0 text-muted-foreground/45', current && 'opacity-0')} />
    </>
  )

  if (!onClick) {
    return (
      <div
        className={cn(
          'flex w-full items-center gap-3 rounded-[14px] border border-[var(--nw-glass-border)] bg-background/20 text-left',
          compact ? 'px-3 py-2.5' : 'px-3.5 py-3',
        )}
        data-testid={testId}
      >
        {content}
      </div>
    )
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex w-full items-center gap-3 rounded-[14px] border border-[var(--nw-glass-border)] bg-background/20 text-left transition-colors hover:bg-[var(--nw-glass-bg-hover)]',
        compact ? 'px-3 py-2.5' : 'px-3.5 py-3',
      )}
      data-testid={testId}
    >
      {content}
    </button>
  )
}

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
  const { t } = useUiLocale()
  const navigate = useNavigate()
  const location = useLocation()
  const copilot = useNovelCopilot()
  const shell = useOptionalNovelShell()
  const { data: indexState } = useNovelWindowIndex(novelId)
  const { data: entities = [] } = useWorldEntities(novelId)
  const { data: relationships = [] } = useWorldRelationships(novelId)
  const { data: systems = [] } = useWorldSystems(novelId)
  const compact = variant === 'compact'
  const indexStatusMeta = getWindowIndexCopilotStatusMeta(indexState)
  const atlasSummary = entities.length > 0 || relationships.length > 0 || systems.length > 0
    ? t('copilot.card.atlasSummary', {
      entities: entities.length,
      relationships: relationships.length,
      systems: systems.length,
    })
    : t('copilot.card.atlasSummaryEmpty')
  const isAtlasSurface = shell?.routeState.surface === 'atlas'

  const handleOpenAtlas = () => {
    if (isAtlasSurface) return

    const nextSearchParams = setAtlasStudioOriginSearchParams(new URLSearchParams(), shell ? {
      stage: shell.routeState.stage ?? 'chapter',
      chapterNum: shell.routeState.chapterNum,
      entityId: shell.routeState.entityId,
      systemId: shell.routeState.systemId,
      reviewKind: shell.routeState.reviewKind,
      resultsProvenance: null,
      artifactPanelState: null,
    } : null)
    const nextSearch = nextSearchParams.toString()
    navigate(`/world/${novelId}${nextSearch ? `?${nextSearch}` : ''}`, {
      state: location.state,
    })
  }

  return (
    <div className={cn('space-y-1.5', className)} data-testid="world-build-panel" data-variant={variant}>
      <ActionStrip
        icon={Search}
        title={t('copilot.card.openWholeBook')}
        description={indexStatusMeta.text}
        onClick={() => copilot.openDrawer(...buildWholeBookCopilotLaunchArgs(shell?.routeState))}
        testId="novel-copilot-trigger"
        compact={compact}
      />

      <ActionStrip
        icon={Globe}
        title={t('studio.rail.atlasTitle')}
        description={atlasSummary}
        onClick={isAtlasSurface ? undefined : handleOpenAtlas}
        testId="world-build-open-atlas"
        compact={compact}
        current={isAtlasSurface}
      />

      <ActionStrip
        icon={Sparkles}
        title={t('copilot.card.generateDrafts')}
        description={t('copilot.card.generateFromSettingsLong')}
        onClick={() => setGenOpen(true)}
        testId="world-build-generate"
        compact={compact}
      />

      <div className={cn(compact ? 'px-2' : 'px-2.5 pt-0.5')}>
        <div className={cn('rounded-[12px] border border-[var(--nw-glass-border)] bg-background/10', compact ? 'px-1 py-0.5' : 'px-1.5 py-1')}>
          <BootstrapPanel novelId={novelId} variant="sidebar" />
        </div>
      </div>

      <WorldGenerationDialog novelId={novelId} open={genOpen} onOpenChange={setGenOpen} />
    </div>
  )
}
