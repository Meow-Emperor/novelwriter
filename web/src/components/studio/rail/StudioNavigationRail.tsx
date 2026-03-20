import '@/lib/uiMessagePacks/novel'
import { BookOpen } from 'lucide-react'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { Input } from '@/components/ui/input'
import { StudioModeRailSection } from './StudioModeRailSection'
import {
  StudioChapterList,
  type StudioChapterListItem,
} from './StudioChapterList'
import type { NovelShellStage } from '@/components/novel-shell/NovelShellRouteState'

export function StudioNavigationRail({
  novelTitle,
  searchQuery,
  onSearchQueryChange,
  chapters,
  selectedChapterNumber,
  onSelectChapter,
  chapterCount,
  onCreateChapter,
  isCreating,
  latestChapterReference,
  onContinuation,
  onOpenAtlas,
  activeStage,
}: {
  novelTitle: string
  searchQuery: string
  onSearchQueryChange: (next: string) => void
  chapters: StudioChapterListItem[]
  selectedChapterNumber: number | null
  onSelectChapter: (chapterNumber: number) => void
  chapterCount: number
  onCreateChapter?: () => void
  isCreating?: boolean
  latestChapterReference: string | null
  onContinuation: () => void
  onOpenAtlas: () => void
  activeStage: NovelShellStage | null
}) {
  const { t } = useUiLocale()
  const hasSearch = searchQuery.trim().length > 0

  return (
    <div className="flex h-full min-h-0 flex-col text-foreground/90" data-testid="studio-rail">
      <div className="shrink-0 border-b border-[var(--nw-glass-border)] px-5 py-5">
        <div className="mb-4 flex items-center gap-2" title={novelTitle}>
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-accent shadow-sm">
            <BookOpen size={14} className="text-white" />
          </div>
          <div className="min-w-0">
            <div className="truncate text-[15px] font-semibold text-foreground">{novelTitle}</div>
            <div className="text-[11px] text-muted-foreground">Studio</div>
          </div>
        </div>

        <Input
          type="text"
          placeholder={t('studio.rail.searchChapters')}
          value={searchQuery}
          onChange={(e) => onSearchQueryChange(e.target.value)}
          className="h-8 rounded-lg border-none bg-background/40 text-[13px] shadow-sm transition-all placeholder:text-muted-foreground hover:bg-background/60 focus:bg-background focus-visible:ring-[1px] focus-visible:ring-accent focus-visible:ring-offset-0"
          data-testid="studio-rail-search"
        />
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-4 px-3 py-4">
        <StudioModeRailSection
          activeStage={activeStage}
          latestChapterReference={latestChapterReference}
          onContinuation={onContinuation}
          onOpenAtlas={onOpenAtlas}
        />

        {hasSearch ? (
          <div className="px-2 text-[11px] text-muted-foreground">
            {t('studio.rail.searchResults', { count: chapters.length })}
          </div>
        ) : null}

        <StudioChapterList
          chapters={chapters}
          selectedChapterNumber={selectedChapterNumber}
          onSelectChapter={onSelectChapter}
          chapterCount={chapterCount}
          onCreateChapter={onCreateChapter}
          isCreating={isCreating}
          activeStage={activeStage}
        />
      </div>
    </div>
  )
}
