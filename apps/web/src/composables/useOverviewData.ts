// composables/useOverviewData.ts — 概览页数据状态(风格规范 9.1/9.5):
// 单一 status 状态机 + refreshing/stale 附加状态;项目切换 Abort 旧请求;
// 校验响应 project_id 上下文;服务端数据由 composable 管理,不复制进 Pinia。
import { onBeforeUnmount, ref, watch, type Ref } from 'vue'
import type { DatasetBatch, SummaryResponse, TaskSummary, TopicRow, TrendPoint } from '../types/domain'
import type { ApiClient } from '../api/client'
import { mockApi } from '../api/mock'

export type AsyncStatus = 'idle' | 'loading' | 'success' | 'empty' | 'error' | 'forbidden'

export interface OverviewData {
  summary: Ref<SummaryResponse | null>
  topics: Ref<TopicRow[]>
  trend: Ref<TrendPoint[]>
  taskSummaries: Ref<TaskSummary[]>
  recentBatches: Ref<DatasetBatch[]>
  status: Ref<AsyncStatus>
  refreshing: Ref<boolean>
  stale: Ref<boolean>
  staleAt: Ref<string | null>
  error: Ref<string | null>
  reload: () => void
}

export function useOverviewData(projectId: Ref<string>, client: ApiClient = mockApi): OverviewData {
  const summary = ref<SummaryResponse | null>(null)
  const topics = ref<TopicRow[]>([])
  const trend = ref<TrendPoint[]>([])
  const taskSummaries = ref<TaskSummary[]>([])
  const recentBatches = ref<DatasetBatch[]>([])
  const status = ref<AsyncStatus>('idle')
  const refreshing = ref(false)
  const stale = ref(false)
  const staleAt = ref<string | null>(null)
  const error = ref<string | null>(null)

  let controller: AbortController | null = null
  const hasData = () => summary.value !== null

  async function load(): Promise<void> {
    controller?.abort()
    controller = new AbortController()
    const signal = controller.signal
    if (hasData()) {
      refreshing.value = true
    } else {
      status.value = 'loading'
    }
    error.value = null
    try {
      const [nextSummary, nextTopics, nextTrend, nextTasks, nextBatches] = await Promise.all([
        client.summary(projectId.value, signal),
        client.topics(projectId.value, signal),
        client.trend(projectId.value, signal),
        client.taskSummaries(projectId.value, signal),
        client.recentBatches(projectId.value, signal),
      ])
      // 上下文校验:快速切项目后旧响应不得覆盖新界面
      if (nextSummary.project_id !== projectId.value) {
        throw new Error(`contract:project_mismatch (${nextSummary.project_id})`)
      }
      summary.value = nextSummary
      topics.value = nextTopics
      trend.value = nextTrend
      taskSummaries.value = nextTasks
      recentBatches.value = nextBatches
      // 无已发布 run = 尚未分析,与「没有匹配结果」区分(UI-13)
      status.value = nextSummary.run_id === null ? 'empty' : 'success'
      refreshing.value = false
      stale.value = false
      staleAt.value = null
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      if (hasData()) {
        // 刷新失败:保留旧内容并显式标为过期(UI-14)
        stale.value = true
        staleAt.value = new Date().toLocaleString('zh-CN')
        refreshing.value = false
      } else {
        status.value = 'error'
        error.value = err instanceof Error ? err.message : String(err)
      }
    }
  }

  watch(projectId, () => { void load() }, { immediate: true })
  onBeforeUnmount(() => controller?.abort())

  return {
    summary,
    topics,
    trend,
    taskSummaries,
    recentBatches,
    status,
    refreshing,
    stale,
    staleAt,
    error,
    reload: () => { void load() },
  }
}
