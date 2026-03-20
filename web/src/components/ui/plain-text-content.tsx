import { useState, type ReactNode } from 'react'
import * as Popover from '@radix-ui/react-popover'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { cn } from '@/lib/utils'

export type PlainTextSplitMode = 'auto' | 'doubleNewline' | 'newline'

export interface TextAnnotation {
  /** Dedup key (used as React key). */
  id: string
  /** Exact substring to match (case-sensitive). */
  term: string
  /** CSS class applied to the highlight span. */
  className?: string
  /** If provided, a Radix Popover opens on hover/focus with this content. */
  renderPopover?: (props: { onClose: () => void }) => ReactNode
}

function splitPlainText(content: string, mode: PlainTextSplitMode): string[] {
  const normalized = content.replace(/\r\n?/g, '\n')
  if (!normalized) return []

  if (mode === 'doubleNewline') {
    return normalized.split(/\n{2,}/)
  }
  if (mode === 'newline') {
    // Treat any run of line breaks as a paragraph boundary.
    return normalized.split(/\n+/)
  }

  // auto: prefer paragraph breaks when present, otherwise treat line breaks as paragraphs.
  return normalized.includes('\n\n') ? normalized.split(/\n{2,}/) : normalized.split(/\n+/)
}

/**
 * Apply annotations to a paragraph string.
 *
 * For each annotation term, finds ALL non-overlapping occurrences (greedy left-to-right,
 * longest first for ties at same position) and wraps them in highlight spans.
 */
function annotateParagraph(text: string, annotations: TextAnnotation[]): ReactNode[] {
  if (annotations.length === 0) return [text]

  // Build all match positions
  const matches: { start: number; end: number; annotation: TextAnnotation }[] = []
  for (const ann of annotations) {
    if (!ann.term) continue
    let searchFrom = 0
    while (searchFrom < text.length) {
      const idx = text.indexOf(ann.term, searchFrom)
      if (idx === -1) break
      matches.push({ start: idx, end: idx + ann.term.length, annotation: ann })
      searchFrom = idx + 1
    }
  }

  if (matches.length === 0) return [text]

  // Sort: leftmost first, longest first for ties
  matches.sort((a, b) => a.start - b.start || (b.end - b.start) - (a.end - a.start))

  // Greedy non-overlapping selection
  const selected: typeof matches = []
  let cursor = 0
  for (const m of matches) {
    if (m.start >= cursor) {
      selected.push(m)
      cursor = m.end
    }
  }

  // Build segments
  const segments: ReactNode[] = []
  let pos = 0
  for (let i = 0; i < selected.length; i++) {
    const m = selected[i]
    if (m.start > pos) {
      segments.push(text.slice(pos, m.start))
    }
    segments.push(
      <AnnotatedSpan
        key={`${m.annotation.id}-${m.start}`}
        annotation={m.annotation}
        matchedText={text.slice(m.start, m.end)}
      />,
    )
    pos = m.end
  }
  if (pos < text.length) {
    segments.push(text.slice(pos))
  }

  return segments
}

function AnnotatedSpan({
  annotation,
  matchedText,
}: {
  annotation: TextAnnotation
  matchedText: string
}) {
  const [open, setOpen] = useState(false)

  const highlight = (
    <span className={cn('rounded-sm', annotation.className)}>
      {matchedText}
    </span>
  )

  if (!annotation.renderPopover) return highlight

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <span
          className={cn('rounded-sm cursor-default', annotation.className)}
          role="button"
          tabIndex={0}
        >
          {matchedText}
        </span>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="top"
          sideOffset={6}
          align="center"
          className="z-50 animate-in fade-in-0 zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95"
          onOpenAutoFocus={(e) => e.preventDefault()}
        >
          {annotation.renderPopover({ onClose: () => setOpen(false) })}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}

export function PlainTextContent({
  isLoading,
  content,
  loadingLabel,
  emptyLabel,
  splitMode = 'newline',
  maxWidth,
  className,
  contentClassName,
  paragraphClassName,
  annotations,
}: {
  isLoading?: boolean
  content: string | null | undefined
  loadingLabel?: string
  emptyLabel?: string
  splitMode?: PlainTextSplitMode
  /** Center text content with a readable max width. */
  maxWidth?: boolean
  /** Root wrapper class. Useful for scroll containers (`flex-1 min-h-0 overflow-y-auto`). */
  className?: string
  /** Inner content wrapper class. Use to tune spacing (`space-y-6`) or width. */
  contentClassName?: string
  /** Paragraph `<p>` class override. */
  paragraphClassName?: string
  /** Optional text annotations. No annotations = current behavior. */
  annotations?: TextAnnotation[]
}) {
  const { t } = useUiLocale()
  const effectiveLoadingLabel = loadingLabel ?? t('plainText.loading')
  const effectiveEmptyLabel = emptyLabel ?? t('plainText.empty')

  if (isLoading) {
    return (
      <div className={cn('h-full flex items-center justify-center', className)}>
        <span className="text-sm text-muted-foreground">{effectiveLoadingLabel}</span>
      </div>
    )
  }

  const raw = content ?? ''
  const paragraphs = splitPlainText(raw, splitMode).filter((p) => p.trim().length > 0)
  if (paragraphs.length === 0) {
    return (
      <div className={cn('h-full flex items-center justify-center', className)}>
        <span className="text-sm text-muted-foreground">{effectiveEmptyLabel}</span>
      </div>
    )
  }

  const hasAnnotations = annotations && annotations.length > 0

  return (
    <div className={cn('h-full', className)}>
      <div
        className={cn(
          'space-y-5',
          maxWidth ? 'max-w-3xl mx-auto' : null,
          contentClassName
        )}
      >
        {paragraphs.map((p, i) => (
          <p
            // Content is already plain text; index keys are stable enough for read-only rendering.
            key={i}
            className={cn('text-[15px] leading-[2] text-foreground', paragraphClassName)}
          >
            {hasAnnotations ? annotateParagraph(p, annotations) : p}
          </p>
        ))}
      </div>
    </div>
  )
}
