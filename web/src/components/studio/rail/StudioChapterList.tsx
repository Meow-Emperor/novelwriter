import '@/lib/uiMessagePacks/novel'
import { FileText, Plus } from 'lucide-react'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { NwButton } from '@/components/ui/nw-button'
import { cn } from '@/lib/utils'
import type { NovelShellStage } from '@/components/novel-shell/NovelShellRouteState'

export type StudioChapterListItem = {
  chapterNumber: number
  label: string
}

export function StudioChapterList({
  chapters,
  selectedChapterNumber,
  onSelectChapter,
  chapterCount,
  onCreateChapter,
  isCreating,
  activeStage,
}: {
  chapters: StudioChapterListItem[]
  selectedChapterNumber: number | null
  onSelectChapter: (chapterNumber: number) => void
  chapterCount: number
  onCreateChapter?: () => void
  isCreating?: boolean
  activeStage: NovelShellStage | null
}) {
  const { t } = useUiLocale()
  const isChapterStage = activeStage !== 'write'

  return (
    <section className="flex min-h-0 flex-1 flex-col" data-testid="studio-rail-chapters">
      <div className="mb-2 flex items-center justify-between px-2">
        <div className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
          {t('studio.rail.chapters')}
        </div>
        {onCreateChapter ? (
          <NwButton
            onClick={onCreateChapter}
            disabled={isCreating}
            variant="ghost"
            className="h-6 w-6 rounded-md p-0 text-muted-foreground hover:bg-foreground/5"
            title={t('studio.rail.createChapter')}
          >
            <Plus size={12} />
          </NwButton>
        ) : null}
      </div>

      {chapters.length === 0 ? (
        <div className="px-4 py-6 text-center text-sm text-muted-foreground">
          {t('studio.rail.noChapters')}
        </div>
      ) : (
        <div className="nw-scrollbar-thin min-h-0 flex-1 overflow-y-auto">
          <div className="space-y-1">
            {chapters.map((chapter) => {
              const selected = isChapterStage && chapter.chapterNumber === selectedChapterNumber
              return (
                <button
                  key={chapter.chapterNumber}
                  type="button"
                  onClick={() => onSelectChapter(chapter.chapterNumber)}
                  className={cn(
                    'w-full rounded-[12px] border px-3 py-2 text-left text-[13px] transition-all',
                    'flex items-center gap-2.5',
                    selected
                      ? 'border-accent/25 bg-accent/10 text-accent shadow-sm'
                      : 'border-transparent text-foreground/80 hover:bg-foreground/5 hover:text-foreground',
                  )}
                >
                  <FileText size={14} className={cn('shrink-0', selected ? 'opacity-100' : 'opacity-55')} />
                  <span className="truncate">{chapter.label}</span>
                </button>
              )
            })}
          </div>
        </div>
      )}

      <div className="mt-3 border-t border-[var(--nw-glass-border)] px-2 pt-3 text-xs text-muted-foreground">
        {t('studio.rail.chapterCount', { count: chapterCount })}
      </div>
    </section>
  )
}
