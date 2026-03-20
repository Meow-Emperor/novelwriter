import '@/lib/uiMessagePacks/novel'
import { NovelCopilotCard } from '@/components/novel-copilot/NovelCopilotCard'
import { NovelCopilotDrawer } from '@/components/novel-copilot/NovelCopilotDrawer'
import { useOptionalNovelCopilot } from '@/components/novel-copilot/NovelCopilotContext'
import {
  NovelCopilotProvider,
} from '@/components/novel-copilot/NovelCopilotProvider'
import { ToastProvider } from '@/components/world-model/shared/Toast'
import { useUiLocale } from '@/contexts/UiLocaleContext'

export function WorldBuildPanel({
  novelId,
  className,
  variant = 'default',
}: {
  novelId: number
  className?: string
  variant?: 'default' | 'compact'
}) {
  const copilot = useOptionalNovelCopilot()
  const { locale } = useUiLocale()

  if (copilot) {
    return <NovelCopilotCard novelId={novelId} className={className} variant={variant} />
  }

  return (
    <ToastProvider>
      <NovelCopilotProvider
        key={`${novelId}:${locale}`}
        novelId={novelId}
        interactionLocale={locale}
      >
        <NovelCopilotCard novelId={novelId} className={className} variant={variant} />
        <NovelCopilotDrawer novelId={novelId} />
      </NovelCopilotProvider>
    </ToastProvider>
  )
}
