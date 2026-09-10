// composables/useTopicsData.ts — 主题洞察数据(工程计划 W12)。
// 服务端排序/分页契约先行;当前演示数据在前端完成排序与分页,mock 由分页 size 示意。
import { onBeforeUnmount, ref, watch, type Ref } from 'vue'
import type { TopicRow } from '../types/domain'
import { ApiHttpError, apiClient, type ApiClient } from '../api/client'

export type TopicsStatus = 'idle' | 'loading' | 'success' | 'empty' | 'error' | 'forbidden'

export function useTopicsData(projectId: Ref<string>, client: ApiClient = apiClient()) {
  const topics = ref<TopicRow[]>([])
  const total = ref(0)
  const status = ref<TopicsStatus>('idle')
  const refreshing = ref(false)
  const error = ref<string | null>(null)
  const page = ref(1)
  const pageSize = ref(20)

  let controller: AbortController | null = null

  async function load(): Promise<void> {
    controller?.abort()
    controller = new AbortController()
    if (topics.value.length) refreshing.value = true
    else status.value = 'loading'
    error.value = null
    try {
      const rows = await client.topics(projectId.value, controller.signal)
      // 排序优先遵循后端;演示数据按反馈量降序,待归类置于末尾
      const ordered = [...rows].sort((a, b) => {
        if (a.id === 'unclassified') return 1
        if (b.id === 'unclassified') return -1
        return b.feedbackCount - a.feedbackCount
      })
      total.value = ordered.length
      topics.value = ordered
      status.value = ordered.length ? 'success' : 'empty'
      refreshing.value = false
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      status.value = err instanceof ApiHttpError && err.status === 403 ? 'forbidden' : 'error'
      error.value = err instanceof Error ? err.message : String(err)
      refreshing.value = false
    }
  }

  watch(projectId, () => { page.value = 1; void load() }, { immediate: true })
  onBeforeUnmount(() => controller?.abort())

  return { topics, total, status, refreshing, error, page, pageSize, reload: () => { void load() } }
}
