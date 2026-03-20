import { useMemo, useState, type KeyboardEvent } from 'react'
import { ArrowLeft, Compass, Sparkles } from 'lucide-react'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { RelationshipInspector } from '@/components/world-model/relationships/RelationshipInspector'
import { NwButton } from '@/components/ui/nw-button'
import { useWorldEntities } from '@/hooks/world/useEntities'
import {
  useConfirmRelationships,
  useDeleteRelationship,
  useUpdateRelationship,
  useWorldRelationships,
} from '@/hooks/world/useRelationships'
import { cn } from '@/lib/utils'

export function StudioRelationshipStage({
  novelId,
  entityId,
  onReturnToArtifact,
  onOpenAtlas,
  onOpenCopilot,
}: {
  novelId: number
  entityId: number | null
  onReturnToArtifact?: () => void
  onOpenAtlas: () => void
  onOpenCopilot: () => void
}) {
  const { t } = useUiLocale()
  const { data: entities = [] } = useWorldEntities(novelId)
  const { data: relationships = [] } = useWorldRelationships(
    novelId,
    entityId !== null ? { entity_id: entityId } : undefined,
    entityId !== null,
  )
  const updateRelationship = useUpdateRelationship(novelId)
  const deleteRelationship = useDeleteRelationship(novelId)
  const confirmRelationships = useConfirmRelationships(novelId)
  const [selectedRelationshipId, setSelectedRelationshipId] = useState<number | null>(null)

  const entityName = entityId === null
    ? null
    : entities.find((entity) => entity.id === entityId)?.name ?? null
  const effectiveSelectedRelationshipId = (
    selectedRelationshipId !== null && relationships.some((relationship) => relationship.id === selectedRelationshipId)
  )
    ? selectedRelationshipId
    : (relationships[0]?.id ?? null)
  const selectedRelationship = useMemo(
    () => relationships.find((relationship) => relationship.id === effectiveSelectedRelationshipId) ?? null,
    [effectiveSelectedRelationshipId, relationships],
  )

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden" data-testid="studio-relationship-stage">
      <div className="shrink-0 border-b border-[var(--nw-glass-border)] px-6 py-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-1">
            <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">
              Studio
            </div>
            <h2 className="text-lg font-semibold text-foreground">
              {t('studio.stage.relationship.title')}
            </h2>
            <p className="text-sm text-muted-foreground">
              {t('studio.stage.relationship.description', { subject: entityName ?? t('studio.stage.relationship.currentEntity') })}
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            {onReturnToArtifact ? (
              <NwButton
                onClick={onReturnToArtifact}
                variant="glass"
                className="rounded-[10px] px-4 py-2 text-sm font-medium"
              >
                <ArrowLeft size={14} />
                {t('studio.stage.returnToResults')}
              </NwButton>
            ) : null}
            <NwButton
              onClick={onOpenCopilot}
              variant="glass"
              className="rounded-[10px] px-4 py-2 text-sm font-medium"
            >
              <Sparkles size={14} />
              {t('studio.stage.relationship.openCopilot')}
            </NwButton>
            <NwButton
              onClick={onOpenAtlas}
              variant="accentOutline"
              className="rounded-[10px] px-4 py-2 text-sm font-medium"
            >
              <Compass size={14} />
              {t('studio.stage.openInAtlas')}
            </NwButton>
          </div>
        </div>
      </div>

      {entityId === null ? (
        <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground">
          {t('studio.stage.relationship.noContext')}
        </div>
      ) : (
        <div className="flex-1 min-h-0 flex overflow-hidden">
          <div className="w-[280px] shrink-0 border-r border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl overflow-hidden flex flex-col min-h-0">
            <div className="shrink-0 p-4 space-y-2">
              <div className="text-sm font-medium text-foreground">
                {t('studio.stage.relationship.forEntity', {
                  subject: entityName ?? t('studio.stage.relationship.entityWithId', { id: entityId }),
                })}
              </div>
              <div className="text-xs text-muted-foreground">
                {t('studio.stage.relationship.count', { count: relationships.length })}
              </div>
            </div>

            <div className="nw-scrollbar-thin min-h-0 flex-1 overflow-y-auto">
              {relationships.length === 0 ? (
                <div className="px-4 py-2 text-sm text-muted-foreground">
                  {t('studio.stage.relationship.empty')}
                </div>
              ) : (
                relationships.map((relationship) => {
                  const targetName = entities.find((entity) => entity.id === relationship.target_id)?.name ?? String(relationship.target_id)
                  const selected = relationship.id === effectiveSelectedRelationshipId
                  return (
                    <div
                      key={relationship.id}
                      className={cn(
                        'w-full px-4 py-2 text-left text-sm flex items-center gap-2 transition-colors cursor-pointer',
                        selected
                          ? 'bg-[var(--nw-glass-bg-hover)] border-l-2 border-l-accent'
                          : 'hover:bg-[var(--nw-glass-bg-hover)]',
                      )}
                      role="button"
                      tabIndex={0}
                      onClick={() => setSelectedRelationshipId(relationship.id)}
                      onKeyDown={(e: KeyboardEvent<HTMLDivElement>) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          setSelectedRelationshipId(relationship.id)
                        }
                      }}
                    >
                      {relationship.status === 'draft' && (
                        <span className="w-1.5 h-1.5 rounded-full bg-[hsl(var(--color-status-draft))] shrink-0" />
                      )}
                      <span className="truncate flex-1 text-foreground">
                        {relationship.label || t('studio.stage.relationship.unnamed')}
                      </span>
                      <span className="text-xs text-muted-foreground shrink-0 truncate max-w-[100px]">
                        → {targetName}
                      </span>
                    </div>
                  )
                })
              )}
            </div>
          </div>

          <div className="flex-1 min-w-0 overflow-hidden">
            <RelationshipInspector
              rel={selectedRelationship}
              entities={entities}
              onUpdate={(relId, data) => updateRelationship.mutate({ relId, data })}
              onConfirm={(relId) => confirmRelationships.mutate([relId])}
              onDelete={(relId) => deleteRelationship.mutate(relId)}
              allowDelete={false}
              layout="full"
              className="h-full min-h-0"
            />
          </div>
        </div>
      )}
    </div>
  )
}
