import type { Visibility } from '@/types/api'
import { readDocumentUiLocale } from '@/lib/uiLocale'
import { translateUiMessage } from '@/lib/uiMessages'

interface LegacyGraphNode {
  id?: string
  label?: string
  entity_id?: number | null
  visibility?: Visibility
}

interface LegacyGraphEdge {
  from?: string
  to?: string
  label?: string
  visibility?: Visibility
}

function visibilityText(visibility?: Visibility): string {
  const locale = readDocumentUiLocale() ?? 'zh'
  if (visibility === 'hidden') return translateUiMessage(locale, 'worldModel.common.visibilityHidden')
  if (visibility === 'reference') return translateUiMessage(locale, 'worldModel.common.visibilityReference')
  return translateUiMessage(locale, 'worldModel.common.visibilityActive')
}

export function LegacyGraphReadonly({ data }: { data: Record<string, unknown> }) {
  const locale = readDocumentUiLocale() ?? 'zh'
  const rawNodes = Array.isArray(data.nodes) ? data.nodes : []
  const rawEdges = Array.isArray(data.edges) ? data.edges : []

  const nodes: LegacyGraphNode[] = rawNodes.filter((node): node is LegacyGraphNode => (
    typeof node === 'object' && node !== null
  ))
  const edges: LegacyGraphEdge[] = rawEdges.filter((edge): edge is LegacyGraphEdge => (
    typeof edge === 'object' && edge !== null
  ))

  const nodeNames = new Map<string, string>()
  for (const node of nodes) {
    const nodeId = typeof node.id === 'string' ? node.id : ''
    const label = typeof node.label === 'string' ? node.label.trim() : ''
    if (nodeId && label) {
      nodeNames.set(nodeId, label)
    }
  }

  return (
    <div className="space-y-4" data-testid="legacy-graph-readonly">
      <div className="rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
        {translateUiMessage(locale, 'worldModel.legacyGraph.notice')}
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-2xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] p-4">
          <div className="text-sm font-medium text-foreground">{translateUiMessage(locale, 'worldModel.legacyGraph.nodes', { count: nodes.length })}</div>
          {nodes.length > 0 ? (
            <div className="mt-3 space-y-2">
              {nodes.map((node, index) => {
                const label = typeof node.label === 'string' && node.label.trim()
                  ? node.label.trim()
                  : translateUiMessage(locale, 'worldModel.common.unnamedNode', { index: index + 1 })
                return (
                  <div key={node.id ?? `${label}-${index}`} className="rounded-xl border border-[var(--nw-glass-border)] px-3 py-2 text-sm">
                    <div className="text-foreground">{label}</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {translateUiMessage(locale, 'worldModel.common.visibility')}：{visibilityText(node.visibility)}
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="mt-3 text-sm text-muted-foreground">{translateUiMessage(locale, 'worldModel.legacyGraph.emptyNodes')}</div>
          )}
        </div>

        <div className="rounded-2xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] p-4">
          <div className="text-sm font-medium text-foreground">{translateUiMessage(locale, 'worldModel.legacyGraph.edges', { count: edges.length })}</div>
          {edges.length > 0 ? (
            <div className="mt-3 space-y-2">
              {edges.map((edge, index) => {
                const from = typeof edge.from === 'string' ? nodeNames.get(edge.from) ?? edge.from : translateUiMessage(locale, 'worldModel.common.unknownNode')
                const to = typeof edge.to === 'string' ? nodeNames.get(edge.to) ?? edge.to : translateUiMessage(locale, 'worldModel.common.unknownNode')
                const label = typeof edge.label === 'string' ? edge.label.trim() : ''
                return (
                  <div key={`${edge.from ?? 'from'}-${edge.to ?? 'to'}-${index}`} className="rounded-xl border border-[var(--nw-glass-border)] px-3 py-2 text-sm">
                    <div className="text-foreground">
                      {from}
                      {label ? ` —${label}→ ` : ' → '}
                      {to}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {translateUiMessage(locale, 'worldModel.common.visibility')}：{visibilityText(edge.visibility)}
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="mt-3 text-sm text-muted-foreground">{translateUiMessage(locale, 'worldModel.legacyGraph.emptyEdges')}</div>
          )}
        </div>
      </div>
    </div>
  )
}
