<template>
  <section class="page" data-testid="analysis-page">
    <h1>分析任务</h1>
    <p class="muted">项目:{{ projectId }} · 数据批次:{{ datasetId }}</p>
    <div class="card">
      <p>
        状态:
        <span data-testid="analysis-status">{{ statusLabel }}</span>
        <span v-if="run?.stage && !isTerminal" class="vl-analysis__stage">（{{ run.stage }}）</span>
      </p>
      <p v-if="percent !== null" data-testid="analysis-percent">
        进度:{{ percent }}%（{{ run?.progress ?? 0 }} / {{ run?.total ?? 0 }}）
      </p>
      <p v-if="run?.status === 'error' && run.error" class="vl-analysis__error" data-testid="analysis-error">
        {{ run.error }}
      </p>
      <p v-if="startError" class="vl-analysis__error" data-testid="analysis-start-error" role="alert">
        {{ startError }}
      </p>
      <VlButton :disabled="!canStart" data-testid="analysis-start" @click="start">
        {{ run && run.status !== 'queued' ? '重新分析' : '开始分析' }}
      </VlButton>
      <p v-if="run && !isTerminal" class="vl-analysis__hint">分析进行中,页面会自动刷新状态。</p>
    </div>
  </section>
</template>

<script setup lang="ts">
// AnalysisProgress — 工程计划 7.3 / QA-12:刷新页面后作业可恢复,终态停止轮询。
//
// **状态以服务端为准。** 此前这一屏把 run 存进 sessionStorage 并一直读它:
// POST 之后页面再也没问过服务端,状态永远停在 POST 那一刻的返回值(POST 返回的是
// queued),「刷新可恢复」恢复的其实是浏览器里的那个字符串。后端一直有
// `GET /projects/{p}/analyses/{id}`,只是前端从没有过调用方——所以这个页面看起来
// 完全正常,却永远看不到分析结束。
//
// 现在:run id 写进 URL(刷新/分享都能回到同一个作业),没有 run id 时按批次回查列表;
// 只在非终态继续轮询。
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiClient } from '../../api/client'
import { TERMINAL_RUN_STATUSES, type AnalysisRun, type AnalysisRunStatus } from '../../types/domain'
import VlButton from '../../components/common/VlButton.vue'

const POLL_INTERVAL_MS = 1500

const STATUS_LABELS: Record<AnalysisRunStatus, string> = {
  queued: '排队中',
  running: '分析中',
  done: '已完成',
  error: '失败',
  cancelled: '已取消',
}

const client = apiClient()
const route = useRoute()
const router = useRouter()

// 路由仅参数变化时组件会被复用,projectId/datasetId 必须是响应式派生值
const projectId = computed(() => String(route.params.p))
const datasetId = computed(() => String(route.query.dataset || 'demo-1'))

const run = ref<AnalysisRun | null>(null)
const busy = ref(false)
const startError = ref('')

const isTerminal = computed(() => !!run.value && TERMINAL_RUN_STATUSES.includes(run.value.status))
// 没有 run 时是空态,应当可以发起;有 run 且未终态时才是「进行中」。
// 写成 `!isTerminal` 会把空态也算成进行中,于是首屏按钮永远是灰的。
const canStart = computed(() => !busy.value && (!run.value || isTerminal.value))
const statusLabel = computed(() => (run.value ? STATUS_LABELS[run.value.status] : '尚未开始'))
const percent = computed(() => {
  const current = run.value
  if (!current || !current.total) return null
  return Math.round(((current.progress ?? 0) / current.total) * 100)
})

// 每次「重新解析」自增,作废所有在途请求与已排期的轮询。
// 没有它的话,切项目或切批次后旧请求返回会覆盖新状态——看起来像状态在乱跳。
let generation = 0
let timer: ReturnType<typeof setTimeout> | null = null

function stopPolling() {
  if (timer !== null) {
    clearTimeout(timer)
    timer = null
  }
}

function schedulePoll(gen: number) {
  stopPolling()
  timer = setTimeout(() => void refresh(gen), POLL_INTERVAL_MS)
}

async function refresh(gen: number) {
  const current = run.value
  if (gen !== generation || !current || TERMINAL_RUN_STATUSES.includes(current.status)) return
  try {
    const next = await client.getAnalysis(projectId.value, current.id)
    if (gen !== generation) return
    run.value = next
    // 终态不再排期。收敛由两处共同保证:这里的排期判断,以及 refresh 开头对
    // 终态的提前返回——后者拦住「已排期但途中已转终态」的那一次多余查询。
    if (!TERMINAL_RUN_STATUSES.includes(next.status)) schedulePoll(gen)
  } catch {
    if (gen !== generation) return
    // 查询失败不等于作业失败:把网络抖动显示成「分析失败」是在编造终态。
    // 保留原状态,退避后再问一次。
    schedulePoll(gen)
  }
}

/** 从服务端解析出这个批次当前对应的 run:URL 里的优先,否则回查列表。 */
async function resolve() {
  const gen = ++generation
  stopPolling()
  run.value = null
  startError.value = ''

  const fromUrl = typeof route.query.run === 'string' ? route.query.run : ''
  if (fromUrl) {
    try {
      const found = await client.getAnalysis(projectId.value, fromUrl)
      if (gen !== generation) return
      run.value = found
      if (!TERMINAL_RUN_STATUSES.includes(found.status)) schedulePoll(gen)
      return
    } catch {
      // 失效的 run id(作业被删/换了项目)不应卡住页面,回落到按批次查找
      if (gen !== generation) return
    }
  }

  try {
    const runs = await client.listAnalyses(projectId.value)
    if (gen !== generation) return
    const mine = runs.find(item => (item.dataset_ids ?? []).includes(datasetId.value))
    if (!mine) return
    run.value = mine
    if (!TERMINAL_RUN_STATUSES.includes(mine.status)) schedulePoll(gen)
  } catch {
    // 列表也拿不到就停在「尚未开始」:这比显示一个猜出来的状态诚实
  }
}

async function start() {
  const gen = ++generation
  stopPolling()
  busy.value = true
  startError.value = ''
  try {
    const created = await client.runAnalysis(projectId.value, datasetId.value)
    if (gen !== generation) return
    run.value = created
    // run id 进 URL:刷新与分享都回到同一个作业,而不是问浏览器要
    void router.replace({ query: { ...route.query, run: created.id } })
    if (!TERMINAL_RUN_STATUSES.includes(created.status)) schedulePoll(gen)
  } catch (err) {
    if (gen !== generation) return
    startError.value = err instanceof Error ? err.message : '无法开始分析'
  } finally {
    busy.value = false
  }
}

watch([projectId, datasetId], () => void resolve(), { immediate: true })
onUnmounted(() => {
  generation += 1
  stopPolling()
})
</script>

<style scoped>
.vl-analysis__stage {
  color: var(--vl-color-text-muted);
}
.vl-analysis__error {
  margin: var(--vl-space-2) 0 0;
  color: var(--vl-color-danger);
}
.vl-analysis__hint {
  margin: var(--vl-space-2) 0 0;
  color: var(--vl-color-text-muted);
  font-size: var(--vl-text-xs);
}
</style>
