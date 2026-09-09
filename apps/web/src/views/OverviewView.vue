<template>
  <div class="vl-page">
    <PageHeader title="工作台" description="先看现在要处理什么,再核对判断依据,最后明确谁来做、做到哪一步。">
      <template #actions>
        <VlButton v-if="canAct" variant="primary" @click="goImports">导入客户反馈</VlButton>
      </template>
    </PageHeader>

    <DemoNotice source-kind="synthetic" :computed-at="displayComputedAt" />

    <div class="vl-overview__filters">
      <FilterBar
        :filters="filters"
        :runs="runs"
        :channels="channelOptions"
        :products="productOptions"
        timezone-label="Asia/Shanghai"
        @update:filters="applyFilters"
        @clear="clearFilters"
      />
    </div>

    <AsyncState
      :status="status"
      :message="error ?? undefined"
      :refreshing="refreshing"
      :stale="stale"
      :stale-at="staleAt ?? undefined"
    >
      <template #empty>
        <div class="vl-async-empty-box">
          <p>还没有导入客户反馈</p>
          <p class="vl-async-empty-box__hint">{{ canAct ? '请先导入反馈并完成分析。' : '请联系管理员导入数据。' }}</p>
          <VlButton v-if="canAct" variant="primary" @click="goImports">去导入</VlButton>
        </div>
      </template>
      <template #error>
        <div class="vl-async-error-box">
          <p>暂时无法获取数据,请稍后重试。</p>
          <VlButton variant="secondary" @click="reload()">重试</VlButton>
        </div>
      </template>

      <section class="vl-metrics" aria-label="行动指标">
        <MetricCard
          data-testid="metric-pending-risks"
          title="待复核风险"
          :value="summary?.insight_metrics.pending_risk_feedback_count ?? null"
          scope-label="所选分析与筛选"
          description="全严重度待复核候选,不是已确认事故"
          :href="metricHref('/risks', 'state=PENDING')"
        />
        <MetricCard
          data-testid="metric-overdue-tasks"
          title="逾期整改"
          :value="summary?.action_metrics.overdue_task_count ?? 0"
          scope-label="本项目·所有分析"
          description="未关闭任务中已超过截止时间的数量"
          :href="`/p/${projectId}/tasks?overdue=true`"
        />
        <MetricCard
          data-testid="metric-active-tasks"
          title="未关闭任务"
          :value="summary?.action_metrics.active_task_count ?? 0"
          scope-label="本项目·所有分析"
          description="待开始、进行中与待验收任务"
          :href="`/p/${projectId}/tasks?state=OPEN&state=IN_PROGRESS&state=PENDING_REVIEW`"
        />
        <MetricCard
          data-testid="metric-valid-feedback"
          title="有效反馈"
          :value="summary?.insight_metrics.valid_feedback_count ?? null"
          unit="条"
          scope-label="所选分析与筛选"
          description="所选分析与筛选条件下的有效反馈数"
          :href="metricHref('/topics', '')"
        />
      </section>

      <div class="vl-overview-grid">
        <div class="vl-overview-primary">
          <VlPanel
            :title="`优先处理主题${summary?.insight_metrics.topic_count != null ? `(${summary.insight_metrics.topic_count})` : ''}`"
            :description="`占比分母为 ${formatCount(summary?.denominator ?? null)} 条有效反馈;多标签主题占比可合计超过 100%`"
          >
            <template #actions>
              <VlButton variant="ghost" size="small" @click="goTopics">全部主题</VlButton>
            </template>
            <p v-if="!topics.length" class="vl-overview__topics-empty">
              暂无已归类主题,仍可查看风险候选与待归类反馈
            </p>
            <div v-else class="vl-table-scroll">
              <table class="vl-topic-table" data-testid="topic-table">
                <thead>
                  <tr>
                    <th scope="col">主题</th>
                    <th scope="col" class="vl-topic-table__num">反馈 n/N</th>
                    <th scope="col" class="vl-topic-table__num">占比</th>
                    <th scope="col">趋势</th>
                    <th scope="col" class="vl-topic-table__num">CPI</th>
                    <th scope="col">复核状态</th>
                    <th scope="col"><span class="vl-sr-only">操作</span></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="topic in topics" :key="topic.id" :data-resource-id="topic.id">
                    <th scope="row" class="vl-topic-table__title">{{ topic.title }}</th>
                    <td class="vl-topic-table__num vl-number">{{ topic.feedbackCount }} / {{ formatCount(topic.denominator) }}</td>
                    <td class="vl-topic-table__num vl-number">{{ topic.ratio.toFixed(1) }}%</td>
                    <td><span class="vl-topic-table__trend vl-number">{{ trendLabel(topic.trend) }}</span></td>
                    <td class="vl-topic-table__num vl-number">{{ topic.cpiDisplayValue ?? '—' }}</td>
                    <td><StatusBadge kind="review" :state="topic.reviewState" /></td>
                    <td>
                      <VlButton variant="ghost" size="small" @click="openEvidence(topic, $event)">查看证据</VlButton>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </VlPanel>

          <TrendChart
            v-if="summary?.run_id"
            :data="trend"
            unit="条"
            :time-range="trendRange"
            summary="所选时间范围内每日有效反馈量;缺失日期保持断点,不跨空值连线。"
          />
        </div>

        <div class="vl-overview-secondary">
          <!-- 证据同一时刻只存在一份:≥1440 用非模态侧栏,<1440 用模态抽屉,辅助列恢复待办 -->
          <template v-if="!selected || !isWide">
            <VlPanel title="待办摘要" :description="`按 ${taskAsOfLabel} 统计,来自本项目全部任务`">
              <ul v-if="taskSummaries.length" class="vl-overview__list">
                <li v-for="task in taskSummaries" :key="task.id" class="vl-overview__list-item">
                  <span class="vl-overview__list-title">{{ task.title }}</span>
                  <StatusBadge kind="task" :state="task.status" />
                  <span v-if="task.overdue" class="vl-overview__overdue">已逾期</span>
                  <span class="vl-overview__list-meta">{{ displayDate(task.dueAt) }}</span>
                </li>
              </ul>
              <p v-else class="vl-overview__muted">暂无待办任务</p>
              <template #actions>
                <VlButton variant="ghost" size="small" @click="goTasks">全部任务</VlButton>
              </template>
            </VlPanel>
            <VlPanel title="最近批次" description="最近导入的数据批次,最多显示 3 条">
              <ul v-if="recentBatches.length" class="vl-overview__list">
                <li v-for="batch in recentBatches" :key="batch.id" class="vl-overview__list-item">
                  <span class="vl-overview__list-title">{{ batch.name }}</span>
                  <span class="vl-overview__list-meta">{{ formatCount(batch.rows) }} 行 · {{ displayDate(batch.createdAt) }}</span>
                </li>
              </ul>
              <p v-else class="vl-overview__muted">还没有导入客户反馈</p>
            </VlPanel>
          </template>
          <EvidencePanel
            v-else
            :evidence="selected"
            :run-label="`${selected.runId} · revision ${selected.revision}`"
            @close="closeEvidence"
          />
        </div>
      </div>
    </AsyncState>

    <EvidenceDrawer
      :open="selected !== null && !isWide"
      :evidence="selected ?? fallbackEvidence"
      :run-label="selected ? `${selected.runId} · revision ${selected.revision}` : ''"
      @close="closeEvidence"
    />
  </div>
</template>

<script setup lang="ts">
// OverviewView — 风格规范 5.3/工程计划 9.3:行动优先首页。
// 从上到下:标题与导入 → 筛选 → 四卡(顺序与范围固定)→ 优先主题表 → 趋势 →
// 右侧辅助列(待办/最近批次),选中主题后切换为证据(≥1440 非模态侧栏,<1440 模态抽屉)。
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '../components/common/PageHeader.vue'
import VlButton from '../components/common/VlButton.vue'
import VlPanel from '../components/common/VlPanel.vue'
import MetricCard from '../components/common/MetricCard.vue'
import StatusBadge from '../components/common/StatusBadge.vue'
import DemoNotice from '../components/common/DemoNotice.vue'
import AsyncState from '../components/common/AsyncState.vue'
import FilterBar, { type FilterValues } from '../components/common/FilterBar.vue'
import EvidencePanel from '../components/common/EvidencePanel.vue'
import EvidenceDrawer from '../components/common/EvidenceDrawer.vue'
import TrendChart from '../components/common/TrendChart.vue'
import { useOverviewData } from '../composables/useOverviewData'
import { useSessionStore } from '../stores/session'
import { useProjectStore } from '../stores/project'
import type { EvidenceContext, TopicRow, TopicTrend } from '../types/domain'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const project = useProjectStore()

const projectId = computed(() => String(route.params.p || project.selectedProjectId))
const { summary, topics, trend, taskSummaries, recentBatches, status, refreshing, stale, staleAt, error, reload } = useOverviewData(projectId)
const canAct = computed(() => (session.user?.role ?? 'VIEWER') !== 'VIEWER')

// —— 筛选:URL 只保存 ID、时间和枚举(风格规范 9.3) ——
const filters = ref<FilterValues>({
  runId: typeof route.query.run === 'string' ? route.query.run : null,
  start: typeof route.query.start === 'string' ? route.query.start : null,
  end: typeof route.query.end === 'string' ? route.query.end : null,
  channel: typeof route.query.channel === 'string' ? route.query.channel : null,
  product: typeof route.query.product === 'string' ? route.query.product : null,
})

const runs = computed(() => [
  { id: summary.value?.run_id ?? 'run_demo_001', label: summary.value ? `${summary.value.run_id}·revision ${summary.value.revision}` : 'run_demo_001' },
])
const channelOptions = [
  { value: 'phone', label: '电话' },
  { value: 'chat', label: '在线客服' },
  { value: 'email', label: '邮件' },
]
const productOptions = [
  { value: 'delivery', label: '配送服务' },
  { value: 'billing', label: '账单与账户' },
]

function applyFilters(next: FilterValues) {
  filters.value = next
  const query: Record<string, string> = {}
  if (next.runId) query.run = next.runId
  if (next.start) query.start = next.start
  if (next.end) query.end = next.end
  if (next.channel) query.channel = next.channel
  if (next.product) query.product = next.product
  void router.replace({ query })
}
function clearFilters() {
  applyFilters({ runId: null, start: null, end: null, channel: null, product: null })
}

function metricHref(base: string, extra: string): string {
  const query = new URLSearchParams()
  if (filters.value.runId) query.set('run', filters.value.runId)
  if (filters.value.start) query.set('start', filters.value.start)
  if (filters.value.end) query.set('end', filters.value.end)
  if (filters.value.channel) query.set('channel', filters.value.channel)
  if (filters.value.product) query.set('product', filters.value.product)
  const suffix = [...query.entries(), ...new URLSearchParams(extra).entries()]
    .map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
    .join('&')
  return suffix ? `/p/${projectId.value}${base}?${suffix}` : `/p/${projectId.value}${base}`
}

// —— 证据联动 ——
const selected = ref<EvidenceContext | null>(null)
// fallbackEvidence 仅为 v-else 分支提供类型安全的占位,抽屉在 selected 为 null 时不可见
const fallbackEvidence: EvidenceContext = {
  topicId: '', topicTitle: '', runId: '', revision: 0, summary: '', cpi: null, quotes: [],
  aiProvenance: { origin: 'unknown', needsReview: true, reviewRecord: null },
}
let trigger: HTMLElement | null = null
function openEvidence(topic: TopicRow, event: MouseEvent) {
  trigger = event.currentTarget as HTMLElement
  selected.value = topic.evidence
}
function closeEvidence() {
  selected.value = null
  trigger?.focus()
  trigger = null
}
watch(projectId, () => closeEvidence())

// ≥1440 非模态侧栏;<1440 模态抽屉(风格规范 5.2 断点矩阵)
const isWide = ref(false)
const mq = typeof window !== 'undefined' ? window.matchMedia('(min-width: 1440px)') : null
function syncWidth() { isWide.value = mq?.matches ?? false }
onMounted(() => { syncWidth(); mq?.addEventListener('change', syncWidth) })
onBeforeUnmount(() => mq?.removeEventListener('change', syncWidth))

// —— 展示辅助 ——
const displayComputedAt = computed(() => summary.value?.computed_at ?? undefined)
const trendRange = computed(() => ({
  start: (summary.value?.filters.start ?? '').slice(0, 10) || '—',
  end: (summary.value?.filters.end ?? '').slice(0, 10) || '—',
}))
const taskAsOfLabel = computed(() => (summary.value?.action_metrics.task_as_of ?? '').slice(0, 10) || '最近')

function formatCount(value: number | null): string {
  return value === null ? '—' : new Intl.NumberFormat('zh-CN').format(value)
}
function displayDate(value: string | null): string {
  return value ? value.slice(0, 10) : '—'
}
function trendLabel(trend: TopicTrend): string {
  switch (trend) {
    case 'up': return '上升'
    case 'down': return '下降'
    case 'flat': return '平稳'
    case 'new': return '新增'
    default: return '—'
  }
}

function goImports() { void router.push(`/p/${projectId.value}/imports`) }
function goTopics() { void router.push(metricHref('/topics', '')) }
function goTasks() { void router.push(`/p/${projectId.value}/tasks`) }
</script>

<style scoped>
.vl-overview__filters {
  margin-top: var(--vl-space-4);
}
.vl-metrics {
  margin-bottom: var(--vl-space-4);
}
.vl-overview__topics-empty {
  margin: 0;
  color: var(--vl-color-text-muted);
}
.vl-topic-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}
.vl-topic-table thead th {
  padding: var(--vl-space-3);
  background: var(--vl-color-subtle);
  font-size: var(--vl-text-sm);
  font-weight: 600;
}
.vl-topic-table tbody th,
.vl-topic-table tbody td {
  padding: var(--vl-space-3);
  border-bottom: 1px solid var(--vl-color-border);
  vertical-align: top;
}
.vl-topic-table__title {
  font-weight: 600;
  white-space: nowrap;
}
.vl-topic-table__num {
  text-align: right;
  white-space: nowrap;
}
.vl-topic-table__trend {
  color: var(--vl-color-text-secondary);
}
.vl-sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.vl-overview-secondary {
  display: flex;
  flex-direction: column;
  gap: var(--vl-space-4);
}
.vl-overview__list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.vl-overview__list-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--vl-space-2);
  padding: var(--vl-space-2) 0;
  border-bottom: 1px solid var(--vl-color-border);
}
.vl-overview__list-item:last-child {
  border-bottom: none;
}
.vl-overview__list-title {
  flex: 1;
  min-width: 0;
  font-size: var(--vl-text-sm);
}
.vl-overview__list-meta {
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
.vl-overview__overdue {
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-danger-bg);
  color: var(--vl-color-danger);
  padding: 2px var(--vl-space-2);
  font-size: var(--vl-text-xs);
}
.vl-overview__muted {
  margin: 0;
  color: var(--vl-color-text-muted);
}
.vl-async-empty-box,
.vl-async-error-box {
  border: 1px solid var(--vl-color-border);
  border-radius: var(--vl-radius-panel);
  background: var(--vl-color-surface);
  padding: var(--vl-space-8);
  text-align: center;
}
.vl-async-empty-box p,
.vl-async-error-box p {
  margin: 0 0 var(--vl-space-2);
}
.vl-async-empty-box__hint {
  font-size: var(--vl-text-sm);
  color: var(--vl-color-text-muted);
}
.vl-async-error-box p {
  color: var(--vl-color-danger);
}
</style>
