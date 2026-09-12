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
          <EmptyState
            text="还没有导入客户反馈"
            :hint="canAct ? '导入并完成分析后,这里会显示行动指标与优先主题。' : '请联系管理员导入数据。'"
          >
            <template v-if="canAct" #action>
              <VlButton variant="primary" @click="goImports">去导入</VlButton>
            </template>
          </EmptyState>
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
          :icon="Warning"
        />
        <MetricCard
          data-testid="metric-overdue-tasks"
          title="逾期整改"
          :value="summary?.action_metrics.overdue_task_count ?? 0"
          scope-label="本项目·所有分析"
          description="未关闭任务中已超过截止时间的数量"
          :href="`/p/${projectId}/tasks?overdue=true`"
          :icon="AlarmClock"
        />
        <MetricCard
          data-testid="metric-active-tasks"
          title="未关闭任务"
          :value="summary?.action_metrics.active_task_count ?? 0"
          scope-label="本项目·所有分析"
          description="待开始、进行中与待验收任务"
          :href="`/p/${projectId}/tasks?state=OPEN&state=IN_PROGRESS&state=PENDING_REVIEW`"
          :icon="Finished"
        />
        <MetricCard
          data-testid="metric-valid-feedback"
          title="有效反馈"
          :value="summary?.insight_metrics.valid_feedback_count ?? null"
          unit="条"
          scope-label="所选分析与筛选"
          description="所选分析与筛选条件下的有效反馈数"
          :href="metricHref('/topics', '')"
          :icon="DataLine"
          :sparkline="trend"
        />
      </section>

      <!-- 构成概览:三组分布图,全部取自本页已加载的真实记录,不新增口径 -->
      <section class="vl-overview-distributions" aria-label="构成概览">
        <VlPanel title="风险严重度" :description="`共 ${risks.length} 条候选`">
          <DistributionBar
            v-if="risks.length"
            :segments="severitySegments"
            label="风险严重度分布"
          />
          <p v-else class="vl-overview__muted">暂无风险候选</p>
        </VlPanel>

        <VlPanel title="任务状态" :description="`共 ${taskSummaries.length} 条任务`">
          <DistributionBar
            v-if="taskSummaries.length"
            :segments="taskSegments"
            label="任务状态分布"
          />
          <p v-else class="vl-overview__muted">暂无任务</p>
        </VlPanel>

        <VlPanel title="主题复核" :description="`共 ${topics.length} 个主题`">
          <DonutChart
            v-if="topics.length"
            :segments="reviewSegments"
            label="主题复核构成"
            total-label="主题"
          />
          <p v-else class="vl-overview__muted">暂无主题</p>
        </VlPanel>
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
              <table class="vl-table vl-topic-table" data-testid="topic-table">
                <thead>
                  <tr>
                    <th scope="col">主题</th>
                    <th scope="col" class="vl-table__num">反馈 n/N</th>
                    <th scope="col" class="vl-topic-table__ratio-col">占比</th>
                    <th scope="col">趋势</th>
                    <th scope="col" class="vl-table__num">CPI</th>
                    <th scope="col">复核状态</th>
                    <th scope="col"><span class="vl-sr-only">操作</span></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="topic in topics" :key="topic.id" :data-resource-id="topic.id">
                    <th scope="row" class="vl-topic-table__title">{{ topic.title }}</th>
                    <td class="vl-table__num">{{ topic.feedbackCount }} / {{ formatCount(topic.denominator) }}</td>
                    <td class="vl-topic-table__ratio">
                      <span class="vl-topic-table__ratio-value vl-number">{{ topic.ratio.toFixed(1) }}%</span>
                      <!-- 占比可视化条:同源数据,宽度按各主题占比归一(最高者占满) -->
                      <span class="vl-topic-table__ratio-track" aria-hidden="true">
                        <span class="vl-topic-table__ratio-fill" :style="{ width: `${ratioWidth(topic.ratio)}%` }" />
                      </span>
                    </td>
                    <td><span class="vl-topic-table__trend">{{ trendLabel(topic.trend) }}</span></td>
                    <td class="vl-table__num">{{ topic.cpiDisplayValue ?? '—' }}</td>
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
import { AlarmClock, DataLine, Finished, Warning } from '@element-plus/icons-vue'
import PageHeader from '../components/common/PageHeader.vue'
import EmptyState from '../components/common/EmptyState.vue'
import DistributionBar, { type DistributionSegment } from '../components/common/DistributionBar.vue'
import DonutChart from '../components/common/DonutChart.vue'
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
import { taskStatusLabel } from '../lib/ui-status'
import type { EvidenceContext, TaskStatus, TopicRow, TopicTrend } from '../types/domain'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const project = useProjectStore()

const projectId = computed(() => String(route.params.p || project.selectedProjectId))
const { summary, topics, trend, taskSummaries, recentBatches, risks, status, refreshing, stale, staleAt, error, reload } = useOverviewData(projectId)
const canAct = computed(() => (session.user?.role ?? 'VIEWER') !== 'VIEWER')

// —— 筛选:URL 只保存 ID、时间和枚举(风格规范 9.3) ——
function readFiltersFromQuery(): FilterValues {
  return {
    runId: typeof route.query.run === 'string' ? route.query.run : null,
    start: typeof route.query.start === 'string' ? route.query.start : null,
    end: typeof route.query.end === 'string' ? route.query.end : null,
    channel: typeof route.query.channel === 'string' ? route.query.channel : null,
    product: typeof route.query.product === 'string' ? route.query.product : null,
  }
}
const filters = ref<FilterValues>(readFiltersFromQuery())

const runs = computed(() => {
  const current = summary.value
  // 无已发布 run(未分析态)时不提供可选分析,避免渲染「null·revision null」
  if (!current?.run_id) return []
  return [{ id: current.run_id, label: `${current.run_id}·revision ${current.revision ?? '—'}` }]
})
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
  // 筛选变化须取消旧请求并按新条件重载(风格规范 9.3)
  reload()
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
watch(projectId, () => {
  closeEvidence()
  // 切项目后筛选不得沿用上一项目的条件(URL 已不含旧 query 时重读为空)
  filters.value = readFiltersFromQuery()
})

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

// —— 构成概览:分布数据由页面已加载的记录聚合,口径与来源列表一致 ——
const SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'NONE'] as const
const SEVERITY_LABEL: Record<string, string> = { CRITICAL: '严重', HIGH: '高', MEDIUM: '中', LOW: '低', NONE: '无' }
// 严重度用语义色表达升级关系(规范 3.1:红色仅用于高严重度与危险提示)
const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: 'var(--vl-color-danger)',
  HIGH: 'var(--vl-color-brand-vivid)',
  MEDIUM: 'var(--vl-chart-6)',
  LOW: 'var(--vl-chart-2)',
  NONE: 'var(--vl-color-border-control)',
}

const severitySegments = computed<DistributionSegment[]>(() => {
  const counts = new Map<string, number>()
  for (const risk of risks.value) counts.set(risk.severity, (counts.get(risk.severity) ?? 0) + 1)
  return SEVERITY_ORDER
    .filter(severity => counts.has(severity))
    .map(severity => ({
      label: SEVERITY_LABEL[severity] ?? severity,
      value: counts.get(severity) ?? 0,
      color: SEVERITY_COLOR[severity] ?? 'var(--vl-color-border-control)',
    }))
})

const TASK_STATE_ORDER: TaskStatus[] = ['OPEN', 'IN_PROGRESS', 'PENDING_REVIEW', 'DRAFT', 'CLOSED', 'CANCELLED']
const TASK_STATE_COLOR: Record<string, string> = {
  OPEN: 'var(--vl-chart-2)',
  IN_PROGRESS: 'var(--vl-color-brand-vivid)',
  PENDING_REVIEW: 'var(--vl-color-warning)',
  DRAFT: 'var(--vl-color-border-control)',
  CLOSED: 'var(--vl-color-success)',
  CANCELLED: 'var(--vl-color-text-muted)',
}

const taskSegments = computed<DistributionSegment[]>(() => {
  const counts = new Map<string, number>()
  for (const task of taskSummaries.value) counts.set(task.status, (counts.get(task.status) ?? 0) + 1)
  return TASK_STATE_ORDER
    .filter(state => counts.has(state))
    .map(state => ({
      label: taskStatusLabel(state),
      value: counts.get(state) ?? 0,
      color: TASK_STATE_COLOR[state] ?? 'var(--vl-color-border-control)',
    }))
})

const REVIEW_ORDER = ['confirmed', 'pending', 'excluded'] as const
const REVIEW_LABEL: Record<string, string> = { confirmed: '已确认', pending: '待复核', excluded: '已排除' }
const REVIEW_COLOR: Record<string, string> = {
  confirmed: 'var(--vl-color-success)',
  pending: 'var(--vl-color-brand-vivid)',
  excluded: 'var(--vl-color-text-muted)',
}

const reviewSegments = computed<DistributionSegment[]>(() => {
  const counts = new Map<string, number>()
  for (const topic of topics.value) counts.set(topic.reviewState, (counts.get(topic.reviewState) ?? 0) + 1)
  return REVIEW_ORDER
    .filter(state => counts.has(state))
    .map(state => ({
      label: REVIEW_LABEL[state] ?? state,
      value: counts.get(state) ?? 0,
      color: REVIEW_COLOR[state] ?? 'var(--vl-color-border-control)',
    }))
})

const maxRatio = computed(() => Math.max(1, ...topics.value.map(t => t.ratio)))

/** 归一化到最高占比,保证最长的条也能读;具体数值始终以文本为准 */
function ratioWidth(ratio: number): number {
  return Math.max(2, Math.round((ratio / maxRatio.value) * 100))
}

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
.vl-overview-distributions {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--vl-space-4);
  margin-bottom: var(--vl-space-4);
}
@media (max-width: 1023px) {
  .vl-overview-distributions {
    grid-template-columns: minmax(0, 1fr);
  }
}
.vl-metrics {
  margin-bottom: var(--vl-space-4);
}
.vl-overview__topics-empty {
  margin: 0;
  color: var(--vl-color-text-muted);
}
.vl-topic-table__title {
  font-weight: 600;
  white-space: nowrap;
}
.vl-topic-table__ratio-col {
  min-width: 9rem;
}
.vl-topic-table__ratio {
  display: grid;
  gap: var(--vl-space-1);
  min-width: 8rem;
}
.vl-topic-table__ratio-value {
  font-variant-numeric: tabular-nums;
}
.vl-topic-table__ratio-track {
  display: block;
  height: 0.375rem;
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-subtle);
  overflow: hidden;
}
.vl-topic-table__ratio-fill {
  display: block;
  height: 100%;
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-brand);
  transition: width var(--vl-motion-normal) var(--vl-ease);
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
