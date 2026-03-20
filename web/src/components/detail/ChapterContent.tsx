import { GlassCard } from '@/components/GlassCard'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { PlainTextContent, type TextAnnotation } from '@/components/ui/plain-text-content'

export function ChapterContent({
  isLoading,
  content,
  annotations,
}: {
  isLoading: boolean
  content: string | null
  annotations?: TextAnnotation[]
}) {
  const { t } = useUiLocale()

  return (
    <GlassCard className="flex-1 overflow-auto rounded-xl p-6 sm:p-8 nw-scrollbar-thin">
      <PlainTextContent
        isLoading={isLoading}
        content={content}
        loadingLabel={t('chapter.loadingContent')}
        emptyLabel={t('chapter.emptySelectToRead')}
        maxWidth
        contentClassName="space-y-6"
        annotations={annotations}
      />
    </GlassCard>
  )
}
