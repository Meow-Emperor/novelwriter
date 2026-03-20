import { GlassSurface } from '@/components/ui/glass-surface'
import { useUiLocale } from '@/contexts/UiLocaleContext'

export function DriftWarningPopover({
  code,
  term,
  onDismiss,
}: {
  code: string
  term: string
  onDismiss: () => void
}) {
  const { t } = useUiLocale()

  const label = code === 'unknown_term_quoted' || code === 'unknown_term_bracketed'
    ? t('drift.unknownTerm')
    : code === 'unknown_term_named' || code === 'unknown_address_token'
    ? t('drift.unknownNaming')
    : t('drift.unknownDefault')

  return (
    <GlassSurface
      variant="floating"
      className="rounded-xl px-4 py-3 max-w-xs flex items-center gap-3"
    >
      <span className="text-xs font-medium px-2 py-0.5 rounded-md bg-[hsl(217,91%,60%,0.2)] text-[hsl(217,91%,80%)]">
        {label}
      </span>
      <span className="text-sm font-semibold text-foreground">{term}</span>
      <button
        type="button"
        onClick={onDismiss}
        className="text-xs text-muted-foreground hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-sm px-1"
      >
        {t('drift.dismiss')}
      </button>
    </GlassSurface>
  )
}
