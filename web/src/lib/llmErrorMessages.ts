import type { LlmConfig } from '@/lib/llmConfigStore'
import { resolveCurrentUiLocale } from '@/lib/uiLocale'
import { translateUiMessage, type UiLocale } from '@/lib/uiMessages'
import { ApiError } from '@/services/api'

export function getLlmConfigWarning(config: LlmConfig, locale?: UiLocale): string | null {
  const filled = [config.baseUrl, config.apiKey, config.model].filter(Boolean).length
  if (filled === 0 || filled === 3) return null
  return translateUiMessage(locale ?? resolveCurrentUiLocale(), 'llm.warning.partialConfig')
}

export function getLlmApiErrorMessage(err: ApiError, locale?: UiLocale): string | null {
  const effectiveLocale = locale ?? resolveCurrentUiLocale()
  switch (err.code) {
    case 'llm_config_incomplete':
      return translateUiMessage(effectiveLocale, 'llm.error.incompleteConfig')
    case 'ai_manually_disabled':
      return translateUiMessage(effectiveLocale, 'llm.error.aiDisabled')
    case 'ai_budget_hard_stop':
      return translateUiMessage(effectiveLocale, 'llm.error.budgetHardStop')
    case 'ai_budget_meter_disabled':
    case 'ai_budget_meter_unavailable':
      return translateUiMessage(effectiveLocale, 'llm.error.budgetUnavailable')
    case 'world_generate_llm_unavailable':
      return translateUiMessage(effectiveLocale, 'llm.error.modelUnavailable')
    default:
      return null
  }
}
