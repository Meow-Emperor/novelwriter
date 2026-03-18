import type { WindowIndexState } from '@/types/api'

export interface WindowIndexStatusMeta {
  text: string
  tone: 'muted' | 'success' | 'warning'
  requiresFallback: boolean
}

const ACTIVE_JOB_STATUSES = new Set(['queued', 'running'])

export function isWindowIndexRebuilding(state: WindowIndexState | null | undefined): boolean {
  return Boolean(state?.job && ACTIVE_JOB_STATUSES.has(state.job.status))
}

export function getWindowIndexBootstrapStatusMeta(state: WindowIndexState | null | undefined): WindowIndexStatusMeta {
  if (!state) {
    return { text: '检索索引状态读取中', tone: 'muted', requiresFallback: false }
  }
  if (isWindowIndexRebuilding(state) && state.status !== 'fresh') {
    return { text: '检索索引更新中', tone: 'muted', requiresFallback: true }
  }
  switch (state.status) {
    case 'fresh':
      return { text: '检索索引已就绪', tone: 'success', requiresFallback: false }
    case 'stale':
      return { text: '检索索引待刷新', tone: 'warning', requiresFallback: true }
    case 'missing':
      return { text: '检索索引尚未就绪', tone: 'warning', requiresFallback: true }
    case 'failed':
      return { text: '检索索引刷新失败', tone: 'warning', requiresFallback: true }
  }
}

export function getWindowIndexCopilotStatusMeta(state: WindowIndexState | null | undefined): WindowIndexStatusMeta {
  if (!state) {
    return { text: '正在读取检索索引状态。', tone: 'muted', requiresFallback: false }
  }
  if (isWindowIndexRebuilding(state) && state.status !== 'fresh') {
    return {
      text: '章节有更新，检索索引正在刷新；当前会先回退到最近章节。',
      tone: 'muted',
      requiresFallback: true,
    }
  }
  switch (state.status) {
    case 'fresh':
      return { text: '检索索引已就绪，可直接进行全书检索。', tone: 'success', requiresFallback: false }
    case 'stale':
      return {
        text: '章节有更新，检索索引待刷新；当前会先回退到最近章节。',
        tone: 'warning',
        requiresFallback: true,
      }
    case 'missing':
      return {
        text: '检索索引尚未就绪；当前会先回退到最近章节。',
        tone: 'warning',
        requiresFallback: true,
      }
    case 'failed':
      return {
        text: '检索索引刷新失败；当前会先回退到最近章节。',
        tone: 'warning',
        requiresFallback: true,
      }
  }
}
