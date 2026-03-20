import { useMemo } from 'react'
import { cn } from '@/lib/utils'
import { useWorldRelationships } from '@/hooks/world/useRelationships'
import { LABELS } from '@/constants/labels'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { useNovelCopilot } from '@/components/novel-copilot/NovelCopilotContext'
import { buildRelationshipResearchCopilotLaunchArgs } from '@/components/novel-copilot/novelCopilotLauncher'
import { Sparkles, Plus } from 'lucide-react'

export function RelationshipSidebarPanel({
  novelId,
  selectedEntityId,
  selectedEntityName,
  onRequestNewRelationship,
  onOpenDraftReview,
  className,
}: {
  novelId: number
  selectedEntityId: number | null
  selectedEntityName?: string | null
  onRequestNewRelationship: () => void
  onOpenDraftReview: () => void
  className?: string
}) {
  const { t } = useUiLocale()
  const { data: relationships = [] } = useWorldRelationships(
    novelId,
    selectedEntityId !== null ? { entity_id: selectedEntityId } : undefined,
    selectedEntityId !== null,
  )
  const copilot = useNovelCopilot()

  const draftCount = useMemo(
    () => relationships.filter((r) => r.status === 'draft').length,
    [relationships],
  )
  return (
    <div
      className={cn('flex items-center gap-2 px-3 py-2', className)}
      data-testid="relationship-sidebar-panel"
    >
      <span className="text-xs font-medium text-foreground">{t('worldModel.relationship.sidebarTitle')}</span>
      <span className="text-xs tabular-nums text-muted-foreground">{relationships.length}</span>
      {draftCount > 0 && (
        <>
          <span className="text-xs text-muted-foreground/50">·</span>
          <button
            type="button"
            className="text-xs tabular-nums text-[hsl(var(--color-status-draft))] hover:text-foreground transition-colors"
            onClick={onOpenDraftReview}
          >
            {t('worldModel.relationship.sidebarDraftCount', { count: draftCount })}
          </button>
        </>
      )}
      <div className="ml-auto flex items-center gap-1">
        <button
          type="button"
          className="h-7 w-7 inline-flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-[var(--nw-glass-bg-hover)] transition-colors"
          onClick={() => copilot.openDrawer(...buildRelationshipResearchCopilotLaunchArgs({
            entityId: selectedEntityId,
            entityName: selectedEntityName,
            surface: 'atlas',
          }))}
          title={t('worldModel.relationship.aiSuggestions')}
        >
          <Sparkles className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          className="h-7 w-7 inline-flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-[var(--nw-glass-bg-hover)] transition-colors disabled:opacity-40"
          onClick={onRequestNewRelationship}
          disabled={selectedEntityId === null}
          title={LABELS.REL_NEW}
          data-testid="sidebar-rel-new"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}
