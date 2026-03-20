import { useCallback, useRef, useState } from 'react'
import { ArrowLeft, Compass } from 'lucide-react'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { DraftReviewNavigator } from '@/components/atlas/review/DraftReviewNavigator'
import type { DraftReviewKind } from '@/components/atlas/review/DraftReviewSummaryCard'
import { DraftReviewTab } from '@/components/world-model/shared/DraftReviewTab'
import { NwButton } from '@/components/ui/nw-button'

export function StudioDraftReviewStage({
  novelId,
  reviewKind,
  onReviewKindChange,
  onOpenEntity,
  onOpenRelationships,
  onOpenSystem,
  onOpenAtlas,
  onReturnToArtifact,
}: {
  novelId: number
  reviewKind: DraftReviewKind
  onReviewKindChange: (kind: DraftReviewKind) => void
  onOpenEntity: (entityId: number) => void
  onOpenRelationships: (entityId: number) => void
  onOpenSystem: (systemId: number) => void
  onOpenAtlas: () => void
  onReturnToArtifact?: () => void
}) {
  const { t } = useUiLocale()
  const [reviewSearch, setReviewSearch] = useState('')
  const [reviewHighlight, setReviewHighlight] = useState<number | null>(null)
  const highlightTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleReviewSelect = useCallback((_kind: DraftReviewKind, id: number) => {
    setReviewHighlight(id)
    if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current)
    highlightTimerRef.current = setTimeout(() => setReviewHighlight(null), 2500)
  }, [])

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden" data-testid="studio-review-stage">
      <div className="shrink-0 border-b border-[var(--nw-glass-border)] px-6 py-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-1">
            <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">
              Studio
            </div>
            <h2 className="text-lg font-semibold text-foreground">
              {t('studio.stage.draftReview.title')}
            </h2>
            <p className="text-sm text-muted-foreground">
              {t('studio.stage.draftReview.description')}
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

      <div className="flex-1 min-h-0 flex overflow-hidden">
        <DraftReviewNavigator
          novelId={novelId}
          kind={reviewKind}
          onKindChange={onReviewKindChange}
          search={reviewSearch}
          onSearchChange={setReviewSearch}
          activeItemId={reviewHighlight}
          onSelectItem={handleReviewSelect}
        />
        <div className="flex-1 min-w-0 overflow-hidden">
          <DraftReviewTab
            novelId={novelId}
            kind={reviewKind}
            onKindChange={onReviewKindChange}
            search={reviewSearch}
            showKindSelector={false}
            showBatchActions={false}
            highlightId={reviewHighlight}
            onOpenEntity={onOpenEntity}
            onOpenRelationships={onOpenRelationships}
            onOpenSystem={onOpenSystem}
          />
        </div>
      </div>
    </div>
  )
}
