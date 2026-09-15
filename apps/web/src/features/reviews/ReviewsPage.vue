<template>
  <div class="vl-page">
    <PageHeader :icon="TrendCharts" title="效果复盘" description="选择 run、revision 与两个时间窗,确认主题映射后生成固定口径的复盘结果。">
      <template #actions>
        <VlButton v-if="canAct" variant="primary" data-testid="review-create" @click="openWizard">创建复盘</VlButton>
      </template>
    </PageHeader>

    <AsyncState :status="status" :message="error ?? undefined">
      <template #empty>
        <EmptyState text="暂无复盘记录" hint="选择任务、主题与两个时间窗后生成固定的对照口径" />
      </template>
      <template #error>
        <p class="vl-reviews__error">暂时无法获取复盘记录,请稍后重试。</p>
        <VlButton variant="secondary" @click="load">重试</VlButton>
      </template>

      <div class="vl-table-scroll">
        <table class="vl-table vl-review-table" data-testid="review-table">
          <thead>
            <tr>
              <th scope="col">复盘中主题</th>
              <th scope="col">复盘前 → 复盘后</th>
              <th scope="col" class="vl-review-table__num">占比变化</th>
              <th scope="col">结论状态</th>
              <th scope="col"><span class="vl-sr-only">操作</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="record in records" :key="record.id" :data-resource-id="record.id">
              <th scope="row" class="vl-review-table__title">
                {{ topicLabel(record) }}
                <span class="vl-review-table__meta">run {{ record.run_id }} · revision {{ record.revision }}</span>
              </th>
              <td class="vl-number">{{ record.before.n }} / {{ record.before.N }} → {{ record.after.n }} / {{ record.after.N }}</td>
              <td class="vl-review-table__num vl-number">{{ deltaLabel(record) }}</td>
              <td>
                <span class="vl-review-table__status" :class="`vl-review-table__status--${statusKind(record)}`">
                  {{ conclusionLabel(record) }}
                </span>
              </td>
              <td>
                <VlButton variant="ghost" size="small" data-testid="review-open" @click="openReview(record)">查看复盘</VlButton>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </AsyncState>

    <!-- W18 创建向导:选 run/主题 → 选两个等长不重叠的时间窗 → 人工确认映射 → 服务端推导 n/N -->
    <el-dialog v-model="wizardOpen" title="创建复盘" width="560px" :close-on-click-modal="false" append-to-body>
      <div v-if="wizardStep === 1" class="vl-wizard">
        <p v-if="!topicOptions.length" class="vl-wizard__hint" data-testid="wizard-empty">
          正在加载可选项…尚无已发布的分析时无法创建复盘。
        </p>
        <div class="vl-field vl-wizard__field">
          <label for="vl-wizard-run">分析 run</label>
          <select id="vl-wizard-run" v-model="wizard.runId" class="vl-wizard__input" data-testid="wizard-run">
            <option v-for="run in runOptions" :key="run.id" :value="run.id">{{ run.label }}</option>
          </select>
        </div>
        <div class="vl-field vl-wizard__field">
          <label for="vl-wizard-topic">主题</label>
          <select id="vl-wizard-topic" v-model="wizard.topicId" class="vl-wizard__input" data-testid="wizard-topic">
            <option v-for="topic in topicOptions" :key="topic.id" :value="topic.id">{{ topic.title }}</option>
          </select>
          <p class="vl-wizard__hint">名称相同不会自动对齐主题,必须显式确认映射。</p>
        </div>
        <div class="vl-wizard__windows">
          <fieldset class="vl-wizard__window">
            <legend>复盘前窗口</legend>
            <div class="vl-field">
              <label for="wizard-before-start">窗口开始</label>
              <input id="wizard-before-start" v-model="wizard.beforeStart" type="date" class="vl-wizard__input" data-testid="wizard-before-start" />
            </div>
            <div class="vl-field">
              <label for="wizard-before-end">窗口结束</label>
              <input id="wizard-before-end" v-model="wizard.beforeEnd" type="date" class="vl-wizard__input" data-testid="wizard-before-end" />
            </div>
          </fieldset>
          <fieldset class="vl-wizard__window">
            <legend>复盘后窗口</legend>
            <div class="vl-field">
              <label for="wizard-after-start">窗口开始</label>
              <input id="wizard-after-start" v-model="wizard.afterStart" type="date" class="vl-wizard__input" data-testid="wizard-after-start" />
            </div>
            <div class="vl-field">
              <label for="wizard-after-end">窗口结束</label>
              <input id="wizard-after-end" v-model="wizard.afterEnd" type="date" class="vl-wizard__input" data-testid="wizard-after-end" />
            </div>
          </fieldset>
        </div>
        <label class="vl-wizard__confirm">
          <input v-model="wizard.alignmentConfirmed" type="checkbox" data-testid="wizard-alignment" />
          <span>目标映射与原任务问题相符(人工确认后才输出变化结论)</span>
        </label>
        <p class="vl-wizard__hint">命中数 n 与分母 N 由服务端按 run 与窗口推导,不需要手工填写。</p>
        <p v-if="wizardError" class="vl-wizard__error" data-testid="wizard-error" role="alert">{{ wizardError }}</p>
      </div>

      <div v-else class="vl-wizard vl-wizard--confirm">
        <p class="vl-wizard__hint">请确认以下映射与口径。生成后结果不可变;改变筛选需新建复盘。</p>
        <dl class="vl-wizard__summary">
          <dt>分析</dt><dd>{{ wizard.runId }} · revision {{ wizard.revision }}</dd>
          <dt>主题</dt><dd>{{ selectedTopicTitle }}</dd>
          <dt>复盘前</dt><dd class="vl-number">{{ wizard.beforeStart }} → {{ wizard.beforeEnd }}</dd>
          <dt>复盘后</dt><dd class="vl-number">{{ wizard.afterStart }} → {{ wizard.afterEnd }}</dd>
          <dt>目标映射</dt><dd>{{ wizard.alignmentConfirmed ? '已确认与原任务问题相符' : '未确认' }}</dd>
        </dl>
        <p v-if="!wizard.alignmentConfirmed" class="vl-wizard__warning" data-testid="wizard-insufficient">
          未人工确认目标映射,结果将标记为「无法比较」,不会输出变化结论。
        </p>
        <p v-else-if="windowIssues.length" class="vl-wizard__warning" data-testid="wizard-window-warning">
          {{ windowIssues.join(';') }},结果将标记为「无法比较」,不会输出变化结论。
        </p>
        <p v-else class="vl-wizard__hint" data-testid="wizard-windows-ok">
          两窗等长且不重叠;生成后 n/N 由服务端从 run 推导。
        </p>
      </div>

      <template #footer>
        <div class="vl-wizard__actions">
          <VlButton variant="secondary" @click="wizardOpen = false">取消</VlButton>
          <VlButton v-if="wizardStep === 2" variant="ghost" @click="wizardStep = 1">上一步</VlButton>
          <VlButton
            variant="primary"
            :loading="creating"
            :data-testid="wizardStep === 1 ? 'wizard-next' : 'wizard-submit'"
            @click="wizardStep === 1 ? goConfirm() : submitReview()"
          >
            {{ wizardStep === 1 ? '下一步:确认映射' : '确认并生成复盘' }}
          </VlButton>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
// ReviewsPage — 工程计划 W18:记录表 + 创建向导;复盘结果不可变;
// 向导只收两个等长不重叠的时间窗与人工映射确认,n/N 由服务端从 run 推导;
// 不可比不显示任何变化数字,low_sample 只展示数量不给结论。
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { TrendCharts } from '@element-plus/icons-vue'
import PageHeader from '../../components/common/PageHeader.vue'
import VlButton from '../../components/common/VlButton.vue'
import AsyncState from '../../components/common/AsyncState.vue'
import EmptyState from '../../components/common/EmptyState.vue'
import { ApiHttpError, apiClient } from '../../api/client'
import { useSessionStore } from '../../stores/session'
import { comparabilityLabel, effectStatusLabel } from '../../lib/ui-status'
import type { AnalysisRun, ReviewRecord, TopicRow } from '../../types/domain'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const client = apiClient()

const projectId = computed(() => String(route.params.p))
const canAct = computed(() => (session.user?.role ?? 'VIEWER') !== 'VIEWER')

const records = ref<ReviewRecord[]>([])
const status = ref<'idle' | 'loading' | 'success' | 'empty' | 'error'>('idle')
const error = ref('')

async function load() {
  status.value = 'loading'
  try {
    // 复盘向导的选项也从服务端取:run 列表与主题列表并行,失败不阻塞复盘记录表
    const [reviewRecords, runList, topicRows] = await Promise.all([
      client.listReviews(projectId.value),
      client.listAnalyses(projectId.value).catch(() => [] as AnalysisRun[]),
      client.topics(projectId.value).catch(() => [] as TopicRow[]),
    ])
    records.value = reviewRecords
    runs.value = runList
    topics.value = topicRows
    status.value = records.value.length ? 'success' : 'empty'
  } catch (err) {
    status.value = 'error'
    error.value = err instanceof Error ? err.message : String(err)
  }
}
onMounted(load)

const runs = ref<AnalysisRun[]>([])
const topics = ref<TopicRow[]>([])

// 向导选项此前写死(run_demo_001/revision 1/三条主题),真实模式下提交必 404。
// 现在:run 选项来自 listAnalyses(已完成的)+ 主题行自带的当前已发布 run;
// 主题与 revision 以 listTopics 为准——它返回的就是最新已发布 run 的主题。
const currentRun = computed(() => topics.value[0]?.evidence.runId ?? null)
const currentRevision = computed(() => topics.value[0]?.evidence.revision ?? null)
const runOptions = computed(() => {
  const done = runs.value.filter(r => r.status === 'done').map(r => r.id)
  const options: Array<{ id: string; revision: number | null }> = done
    .filter(id => id !== currentRun.value)
    .map(id => ({ id, revision: null }))
  if (currentRun.value) {
    options.unshift({ id: currentRun.value, revision: currentRevision.value })
  }
  return options.map(o => ({ id: o.id, label: `${o.id} · revision ${o.revision ?? '—'}` }))
})
const topicOptions = computed(() => topics.value)

const wizardOpen = ref(false)
const wizardStep = ref(1)
const wizardError = ref('')
const creating = ref(false)
// 默认两窗等长且不重叠([08-01,08-31) 与 [09-01,10-01)),映射需人工勾选确认;
// run/主题/revision 默认值在打开向导时按服务端状态填(openWizard)
const wizard = ref({
  runId: '',
  revision: 1,
  topicId: '',
  beforeStart: '2026-08-01',
  beforeEnd: '2026-08-31',
  afterStart: '2026-09-01',
  afterEnd: '2026-10-01',
  alignmentConfirmed: false,
})

function openWizard() {
  wizard.value.alignmentConfirmed = false
  wizardError.value = ''
  wizardStep.value = 1
  wizardOpen.value = true
}

// 默认值跟随服务端数据:run/主题列表是异步的,打开向导时可能还没到;
// 用户已改过的字段不动,空值或失效值(该选项已不在列表里)回落到首项
watch([currentRun, topicOptions], () => {
  if (!wizard.value.runId || !runOptions.value.some(o => o.id === wizard.value.runId)) {
    wizard.value.runId = currentRun.value ?? runOptions.value[0]?.id ?? ''
  }
  if (!wizard.value.topicId || !topicOptions.value.some(t => t.id === wizard.value.topicId)) {
    wizard.value.topicId = topicOptions.value[0]?.id ?? ''
  }
}, { immediate: true })

const selectedTopicTitle = computed(() =>
  topicOptions.value.find(t => t.id === wizard.value.topicId)?.title ?? '—')
/** 选中主题的版本行 id(7.5 复盘契约的 topic_version_ids);演示回退行可能没有 */
const selectedTopicVersionId = computed(() =>
  topicOptions.value.find(t => t.id === wizard.value.topicId)?.versionId ?? null)

/** date 输入只到日:按 UTC 零点解释,避免本地时区把窗口端点移出等长 */
function toIso(date: string): string {
  return `${date}T00:00:00+00:00`
}
function windowDays(start: string, end: string): number {
  return (Date.parse(toIso(end)) - Date.parse(toIso(start))) / 86_400_000
}

/** 两窗的明显口径问题;是否可比最终由服务端判定,这里只用于确认页提示 */
const windowIssues = computed(() => {
  const w = wizard.value
  if (!w.beforeStart || !w.beforeEnd || !w.afterStart || !w.afterEnd) return ['请完整选择两个窗口的起止日期']
  const issues: string[] = []
  if (w.beforeStart >= w.beforeEnd || w.afterStart >= w.afterEnd) issues.push('窗口起点必须早于终点')
  else {
    if (windowDays(w.beforeStart, w.beforeEnd) !== windowDays(w.afterStart, w.afterEnd)) issues.push('前后窗口时长不等')
    if (w.beforeStart < w.afterEnd && w.afterStart < w.beforeEnd) issues.push('前后窗口重叠')
  }
  return issues
})

function goConfirm() {
  const w = wizard.value
  if (!w.runId || !w.topicId) {
    wizardError.value = '请先选择分析 run 与主题(尚无已发布的分析时无法创建复盘)。'
    return
  }
  if (!w.beforeStart || !w.beforeEnd || !w.afterStart || !w.afterEnd) {
    wizardError.value = '请完整选择两个窗口的起止日期'
    return
  }
  if (w.beforeStart >= w.beforeEnd || w.afterStart >= w.afterEnd) {
    wizardError.value = '窗口起点必须早于终点'
    return
  }
  wizardError.value = ''
  wizardStep.value = 2
}

async function submitReview() {
  creating.value = true
  try {
    // revision 与 topic_version_ids 都取自服务端返回的主题行——写死 revision=1
    // 在真实模式下必 404(第二个 run 的 revision 不是 1)
    const topicRow = topicOptions.value.find(t => t.id === wizard.value.topicId)
    const created = await client.createReview(projectId.value, {
      run_id: wizard.value.runId,
      revision: topicRow?.evidence.revision ?? wizard.value.revision,
      topic_version_ids: topicRow?.versionId ? [topicRow.versionId] : [],
      before: { start: toIso(wizard.value.beforeStart), end: toIso(wizard.value.beforeEnd) },
      after: { start: toIso(wizard.value.afterStart), end: toIso(wizard.value.afterEnd) },
      alignment_confirmed: wizard.value.alignmentConfirmed,
    })
    wizardOpen.value = false
    wizardStep.value = 1
    await load()
    void router.push(`/p/${projectId.value}/reviews/${created.id}`)
  } catch (err) {
    // 404 analysis_not_found:run 不存在或不属于本项目,提示重新选择而不是重试原请求
    wizardError.value = err instanceof ApiHttpError && err.status === 404
      ? '分析 run 不存在或不属于当前项目,请重新选择。'
      : err instanceof Error ? err.message : '创建失败,请稍后重试'
  } finally {
    creating.value = false
  }
}

function openReview(record: ReviewRecord) {
  void router.push(`/p/${projectId.value}/reviews/${record.id}`)
}

function topicLabel(record: ReviewRecord): string {
  const versionId = record.topic_version_ids[0]
  return topics.value.find(t => t.versionId === versionId)?.title ?? '复盘主题'
}
/** 只有 ok 才允许出现变化数字:low_sample 保留数量但不给结论,insufficient 一律 '—' */
function deltaLabel(record: ReviewRecord): string {
  if (record.comparability !== 'ok' || !record.metrics || record.metrics.share_delta_pp === null) return '—'
  return `${record.metrics.share_delta_pp} 个百分点`
}
function conclusionLabel(record: ReviewRecord): string {
  if (record.comparability === 'ok') return effectStatusLabel(record.effect_status)
  return comparabilityLabel(record.comparability)
}
function statusKind(record: ReviewRecord): string {
  return record.comparability === 'ok' ? 'observed' : 'insufficient'
}
</script>

<style scoped>
.vl-review-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}
.vl-review-table__title {
  font-weight: 600;
}
.vl-review-table__meta {
  display: block;
  font-size: var(--vl-text-xs);
  font-weight: 400;
  color: var(--vl-color-text-muted);
  font-family: var(--vl-font-mono);
}
.vl-review-table__num {
  text-align: right;
  white-space: nowrap;
}
.vl-review-table__status {
  border-radius: var(--vl-radius-sm);
  padding: 2px var(--vl-space-2);
  font-size: var(--vl-text-xs);
  white-space: nowrap;
}
.vl-review-table__status--observed {
  background: var(--vl-color-info-bg);
  color: var(--vl-color-info);
}
.vl-review-table__status--insufficient {
  background: var(--vl-color-warning-bg);
  color: var(--vl-color-warning);
}
.vl-reviews__error {
  color: var(--vl-color-danger);
}
.vl-wizard__field,
.vl-wizard__windows {
  margin-bottom: var(--vl-space-4);
}
.vl-wizard__input {
  width: 100%;
  min-height: var(--vl-control-height);
  border: 1px solid var(--vl-color-border-control);
  border-radius: var(--vl-radius-control);
  padding: 0 var(--vl-space-3);
  font: inherit;
}
.vl-wizard__hint {
  margin: var(--vl-space-2) 0 0;
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
.vl-wizard__windows {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--vl-space-4);
}
.vl-wizard__window {
  border: 1px solid var(--vl-color-border);
  border-radius: var(--vl-radius-panel);
  padding: var(--vl-space-3);
  min-width: 0;
}
.vl-wizard__window legend {
  font-size: var(--vl-text-sm);
  color: var(--vl-color-text-secondary);
  padding: 0 var(--vl-space-1);
}
.vl-wizard__window .vl-field {
  margin-bottom: var(--vl-space-3);
}
.vl-wizard__window label {
  display: block;
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
  margin-bottom: var(--vl-space-1);
}
.vl-wizard__confirm {
  display: flex;
  align-items: flex-start;
  gap: var(--vl-space-2);
  margin-bottom: var(--vl-space-2);
  font-size: var(--vl-text-sm);
}
.vl-wizard__error {
  color: var(--vl-color-danger);
}
.vl-wizard__warning {
  margin: var(--vl-space-3) 0 0;
  padding: var(--vl-space-2) var(--vl-space-3);
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-warning-bg);
  color: var(--vl-color-warning);
  font-size: var(--vl-text-xs);
}
.vl-wizard__summary {
  display: grid;
  grid-template-columns: 6rem 1fr;
  gap: var(--vl-space-2) var(--vl-space-3);
  margin: var(--vl-space-3) 0 0;
  font-size: var(--vl-text-sm);
}
.vl-wizard__summary dt {
  color: var(--vl-color-text-muted);
}
.vl-wizard__summary dd {
  margin: 0;
}
.vl-wizard__actions {
  display: flex;
  gap: var(--vl-space-3);
  justify-content: flex-end;
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
@media (max-width: 767px) {
  .vl-wizard__windows {
    grid-template-columns: 1fr;
  }
}
</style>
