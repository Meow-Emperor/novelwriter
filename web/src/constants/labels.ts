import '@/lib/uiMessagePacks/novel'
import { resolveCurrentUiLocale } from '@/lib/uiLocale'
import { translateUiMessage, type UiLocale } from '@/lib/uiMessages'

function currentLocale(): UiLocale {
  return resolveCurrentUiLocale()
}

function worldLabel(key: Parameters<typeof translateUiMessage>[1], params?: Parameters<typeof translateUiMessage>[2]) {
  return translateUiMessage(currentLocale(), key, params)
}

export const LABELS = {
  // Tabs
  get TAB_SYSTEMS() { return worldLabel('worldModel.common.systems') },
  get TAB_ENTITIES() { return worldLabel('worldModel.common.entities') },
  get TAB_RELATIONSHIPS() { return worldLabel('worldModel.common.relationships') },

  // Entity
  get ENTITY_NEW() { return worldLabel('worldModel.entity.new') },
  get ENTITY_SEARCH_PLACEHOLDER() { return worldLabel('worldModel.common.searchEntities') },
  get ENTITY_EMPTY() { return worldLabel('worldModel.entity.empty') },
  get ENTITY_DELETE() { return worldLabel('worldModel.entity.delete') },
  get ENTITY_DELETE_CONFIRM() { return worldLabel('worldModel.entity.deleteConfirm') },
  get ENTITY_TYPE_ALL() { return worldLabel('worldModel.common.all') },
  get ENTITY_ATTRIBUTES() { return worldLabel('worldModel.entity.attributes') },
  get ENTITY_ADD_ATTRIBUTE() { return worldLabel('worldModel.entity.addAttribute') },
  ENTITY_DRAFT_BANNER: (count: number) => `${count} ${worldLabel('worldModel.common.statusDraft')}`,
  get STATUS_DRAFT() { return worldLabel('worldModel.common.statusDraft') },

  // Visibility
  get VIS_ACTIVE() { return worldLabel('worldModel.common.visibilityActive') },
  get VIS_REFERENCE() { return worldLabel('worldModel.common.visibilityReference') },
  get VIS_HIDDEN() { return worldLabel('worldModel.common.visibilityHidden') },

  // System
  get SYSTEM_NEW() { return worldLabel('worldModel.system.new') },
  get SYSTEM_SEARCH_PLACEHOLDER() { return worldLabel('worldModel.common.searchSystems') },
  get SYSTEM_BACK() { return worldLabel('worldModel.system.back') },
  get SYSTEM_CONSTRAINTS() { return worldLabel('worldModel.system.constraints') },
  get SYSTEM_ADD_CONSTRAINT() { return worldLabel('worldModel.system.addConstraint') },
  get SYSTEM_ADD_ROOT() { return worldLabel('worldModel.system.addRoot') },
  get SYSTEM_ADD_EVENT() { return worldLabel('worldModel.system.addEvent') },
  get SYSTEM_ADD_ITEM() { return worldLabel('worldModel.system.addItem') },
  get SYSTEM_INSERT() { return worldLabel('worldModel.system.insert') },
  get SYSTEM_TYPE_HIERARCHY() { return worldLabel('worldModel.system.display.hierarchy') },
  get SYSTEM_TYPE_TIMELINE() { return worldLabel('worldModel.system.display.timeline') },
  get SYSTEM_TYPE_LIST() { return worldLabel('worldModel.system.display.list') },
  get SYSTEM_TYPE_GRAPH_LEGACY() { return worldLabel('worldModel.system.display.graph') },
  get SYSTEM_DELETE() { return worldLabel('worldModel.system.delete') },
  get SYSTEM_DELETE_CONFIRM() { return worldLabel('worldModel.system.deleteConfirm') },

  // Relationship
  get REL_EMPTY() { return worldLabel('worldModel.relationship.empty') },
  get REL_NEW() { return worldLabel('worldModel.relationship.new') },
  get REL_DELETE() { return worldLabel('worldModel.relationship.delete') },
  get REL_DELETE_CONFIRM() { return worldLabel('worldModel.relationship.deleteConfirm') },
  get REL_DESCRIPTION() { return worldLabel('worldModel.relationship.description') },
  get REL_LABEL_PLACEHOLDER() { return worldLabel('worldModel.relationship.labelPlaceholder') },
  get REL_DESCRIPTION_PLACEHOLDER() { return worldLabel('worldModel.relationship.descriptionPlaceholder') },
  get REL_INSPECTOR_EMPTY() { return worldLabel('worldModel.relationship.inspectorEmpty') },
  get REL_INSPECTOR_HINT() { return worldLabel('worldModel.relationship.inspectorHint') },

  // Common
  get CONFIRM() { return worldLabel('dialog.confirm') },
  get CANCEL() { return worldLabel('dialog.cancel') },
  get DELETE() { return worldLabel('worldModel.common.deleted') },
  get SAVE() { return worldLabel('editor.save') },
  get BATCH_CONFIRM() { return `${worldLabel('dialog.confirm')} ${worldLabel('worldModel.common.all')}` },

  // Placeholders
  get PH_KEY() { return worldLabel('worldModel.placeholder.key') },
  get PH_VALUE() { return worldLabel('worldModel.placeholder.value') },
  get PH_NAME() { return worldLabel('worldModel.placeholder.name') },
  get PH_DESCRIPTION() { return worldLabel('worldModel.placeholder.description') },
  get PH_NODE_NAME() { return worldLabel('worldModel.placeholder.nodeName') },
  get PH_EVENT_NAME() { return worldLabel('worldModel.placeholder.eventName') },
  get PH_TIME() { return worldLabel('worldModel.placeholder.time') },
  get PH_CONSTRAINT() { return worldLabel('worldModel.placeholder.constraint') },
  get PH_SYSTEM_NAME() { return worldLabel('worldModel.placeholder.systemName') },

  // Bootstrap
  get BOOTSTRAP_INITIAL_EXTRACTION() { return worldLabel('worldModel.bootstrap.extractFromChapters') },
  get BOOTSTRAP_REEXTRACT() { return worldLabel('worldModel.bootstrap.reextractDrafts') },
  get BOOTSTRAP_SCANNING() { return worldLabel('worldModel.common.processing') },
  get BOOTSTRAP_COMPLETED_INDEX_REFRESH() { return worldLabel('worldModel.bootstrap.completedIndexRefresh') },
  BOOTSTRAP_COMPLETED_EXTRACTION: (entities: number, relationships: number) =>
    worldLabel('worldModel.bootstrap.completedExtraction', { entities, relationships }),
  get BOOTSTRAP_FAILED() { return worldLabel('worldModel.bootstrap.failed') },
  get BOOTSTRAP_REEXTRACT_CONFIRM_TITLE() { return worldLabel('worldModel.bootstrap.confirmTitle') },
  get BOOTSTRAP_REEXTRACT_CONFIRM_DESC() { return worldLabel('worldModel.bootstrap.confirmDescription') },
  get BOOTSTRAP_REEXTRACT_CONFIRM() { return worldLabel('worldModel.bootstrap.confirmAction') },
  get BOOTSTRAP_STEP_PENDING() { return worldLabel('worldModel.bootstrap.step.pending') },
  get BOOTSTRAP_STEP_TOKENIZING() { return worldLabel('worldModel.bootstrap.step.tokenizing') },
  get BOOTSTRAP_STEP_EXTRACTING() { return worldLabel('worldModel.bootstrap.step.extracting') },
  get BOOTSTRAP_STEP_WINDOWING() { return worldLabel('worldModel.bootstrap.step.windowing') },
  get BOOTSTRAP_STEP_REFINING() { return worldLabel('worldModel.bootstrap.step.refining') },
  get BOOTSTRAP_NO_TEXT() { return worldLabel('worldModel.bootstrap.noText') },

  // Error toasts (World Model)
  get ERROR_DELETE_FAILED() { return worldLabel('worldModel.error.deleteFailed') },
  get ERROR_SAVE_FAILED() { return worldLabel('worldModel.error.saveFailed') },
  get ERROR_CONFIRM_FAILED() { return worldLabel('worldModel.error.confirmFailed') },
  get ERROR_REJECT_FAILED() { return worldLabel('worldModel.error.rejectFailed') },
  get ERROR_BOOTSTRAP_TRIGGER_FAILED() { return worldLabel('worldModel.error.bootstrapTriggerFailed') },
  get WORLDPACK_IMPORT_COMPLETED() { return worldLabel('worldModel.worldpack.completed') },
  get WORLDPACK_IMPORT_FAILED() { return worldLabel('worldModel.worldpack.failed') },

  // Draft review
  get CONFIRM_ALL_ENTITIES() { return `${worldLabel('dialog.confirm')} ${worldLabel('worldModel.common.all')}` },
  get CONFIRM_ALL_RELATIONSHIPS() { return `${worldLabel('dialog.confirm')} ${worldLabel('worldModel.common.all')}` },

  // Display helpers
  ENTITY_TYPE_LABEL: (entityType: string, locale: UiLocale = currentLocale()) => {
    const table: Record<UiLocale, Record<string, string>> = {
      zh: {
        Character: '角色',
        Location: '地点',
        Faction: '势力',
        Concept: '概念',
        Vehicle: '载具',
        Item: '物品',
      },
      en: {
        Character: 'Character',
        Location: 'Location',
        Faction: 'Faction',
        Concept: 'Concept',
        Vehicle: 'Vehicle',
        Item: 'Item',
      },
    }
    return table[locale][entityType] ?? entityType
  },
} as const
