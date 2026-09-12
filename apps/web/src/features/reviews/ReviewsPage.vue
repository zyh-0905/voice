<template>
  <div class="vl-page">
    <PageHeader title="效果复盘" description="选择 run、revision 与两个时间窗,确认主题映射后生成固定口径的复盘结果。">
      <template #actions>
        <VlButton v-if="canAct" variant="primary" data-testid="review-create" @click="wizardOpen = true">创建复盘</VlButton>
      </template>
    </PageHeader>

    <AsyncState :status="status" :message="error ?? undefined" empty-message="暂无复盘记录。">
      <template #error>
        <p class="vl-reviews__error">暂时无法获取复盘记录,请稍后重试。</p>
        <VlButton variant="secondary" @click="load">重试</VlButton>
      </template>

      <div class="vl-table-scroll">
        <table class="vl-review-table" data-testid="review-table">
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
              <td class="vl-review-table__num vl-number">
                {{ record.metrics.share_delta_pp === null ? '—' : `${record.metrics.share_delta_pp} 个百分点` }}
              </td>
              <td>
                <span class="vl-review-table__status" :class="`vl-review-table__status--${statusKind(record)}`">
                  {{ effectLabel(record) }}
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

    <!-- W18 创建向导:选择数据/主题/窗口 → 确认映射 → 生成固定口径结果 -->
    <el-dialog v-model="wizardOpen" title="创建复盘" width="560px" :close-on-click-modal="false" append-to-body>
      <div v-if="wizardStep === 1" class="vl-wizard">
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
              <label :for="`wizard-before-n`">命中数 n</label>
              <input :id="`wizard-before-n`" v-model.number="wizard.nBefore" type="number" min="0" class="vl-wizard__input" data-testid="wizard-before-n" />
            </div>
            <div class="vl-field">
              <label :for="`wizard-before-N`">分母 N</label>
              <input :id="`wizard-before-N`" v-model.number="wizard.NBefore" type="number" min="0" class="vl-wizard__input" data-testid="wizard-before-N" />
            </div>
          </fieldset>
          <fieldset class="vl-wizard__window">
            <legend>复盘后窗口</legend>
            <div class="vl-field">
              <label :for="`wizard-after-n`">命中数 n</label>
              <input :id="`wizard-after-n`" v-model.number="wizard.nAfter" type="number" min="0" class="vl-wizard__input" data-testid="wizard-after-n" />
            </div>
            <div class="vl-field">
              <label :for="`wizard-after-N`">分母 N</label>
              <input :id="`wizard-after-N`" v-model.number="wizard.NAfter" type="number" min="0" class="vl-wizard__input" data-testid="wizard-after-N" />
            </div>
          </fieldset>
        </div>
        <p v-if="wizardError" class="vl-wizard__error" data-testid="wizard-error" role="alert">{{ wizardError }}</p>
      </div>

      <div v-else class="vl-wizard vl-wizard--confirm">
        <p class="vl-wizard__hint">请确认以下映射与口径。生成后结果不可变;改变筛选需新建复盘。</p>
        <dl class="vl-wizard__summary">
          <dt>分析</dt><dd>{{ wizard.runId }} · revision {{ wizard.revision }}</dd>
          <dt>主题</dt><dd>{{ selectedTopicTitle }}</dd>
          <dt>复盘前</dt><dd class="vl-number">{{ wizard.nBefore }} / {{ wizard.NBefore }}</dd>
          <dt>复盘后</dt><dd class="vl-number">{{ wizard.nAfter }} / {{ wizard.NAfter }}</dd>
        </dl>
        <p v-if="!wizardComparable" class="vl-wizard__warning" data-testid="wizard-insufficient">
          当前分母为 0,结果将标记为「数据不足」,不会输出变化结论。
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
// 不可比数据不显示改善结论;n/N、占比、百分点、相对变化始终可见。
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '../../components/common/PageHeader.vue'
import VlButton from '../../components/common/VlButton.vue'
import AsyncState from '../../components/common/AsyncState.vue'
import { apiClient } from '../../api/client'
import { useSessionStore } from '../../stores/session'
import { effectStatusLabel } from '../../lib/ui-status'
import type { ReviewRecord } from '../../types/domain'

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
    records.value = await client.listReviews(projectId.value)
    status.value = records.value.length ? 'success' : 'empty'
  } catch (err) {
    status.value = 'error'
    error.value = err instanceof Error ? err.message : String(err)
  }
}
onMounted(load)

const runOptions = computed(() => [
  { id: records.value[0]?.run_id ?? 'run_demo_001', label: `${records.value[0]?.run_id ?? 'run_demo_001'} · revision ${records.value[0]?.revision ?? 1}` },
])
const topicOptions = [
  { id: 'delivery', title: '物流体验' },
  { id: 'refund', title: '退款进度' },
  { id: 'product', title: '产品使用' },
]

const wizardOpen = ref(false)
const wizardStep = ref(1)
const wizardError = ref('')
const creating = ref(false)
const wizard = ref({ runId: runOptions.value[0]?.id ?? 'run_demo_001', revision: 1, topicId: 'delivery', nBefore: 168, NBefore: 1000, nAfter: 102, NAfter: 1000 })

const selectedTopicTitle = computed(() => topicOptions.find(t => t.id === wizard.value.topicId)?.title ?? '—')
const wizardComparable = computed(() => Number(wizard.value.NBefore) > 0 && Number(wizard.value.NAfter) > 0)

function goConfirm() {
  if (Number(wizard.value.nBefore) < 0 || Number(wizard.value.NBefore) < 0 || Number(wizard.value.nAfter) < 0 || Number(wizard.value.NAfter) < 0) {
    wizardError.value = '数量与分母不能为负数'
    return
  }
  wizardError.value = ''
  wizardStep.value = 2
}

async function submitReview() {
  creating.value = true
  try {
    const created = await client.createReview(projectId.value, {
      run_id: wizard.value.runId,
      revision: wizard.value.revision,
      topic_version_ids: [wizard.value.topicId],
      n_before: Number(wizard.value.nBefore),
      N_before: Number(wizard.value.NBefore),
      n_after: Number(wizard.value.nAfter),
      N_after: Number(wizard.value.NAfter),
    })
    wizardOpen.value = false
    wizardStep.value = 1
    await load()
    void router.push(`/p/${projectId.value}/reviews/${created.id}`)
  } catch (err) {
    wizardError.value = err instanceof Error ? err.message : '创建失败,请稍后重试'
  } finally {
    creating.value = false
  }
}

function openReview(record: ReviewRecord) {
  void router.push(`/p/${projectId.value}/reviews/${record.id}`)
}

function topicLabel(record: ReviewRecord): string {
  const id = record.topic_version_ids[0]
  return topicOptions.find(t => t.id === id)?.title ?? '复盘主题'
}
function effectLabel(record: ReviewRecord): string {
  return effectStatusLabel(record.effect_status)
}
function statusKind(record: ReviewRecord): string {
  if (!record.metrics.comparable) return 'insufficient'
  return 'observed'
}
</script>

<style scoped>
.vl-review-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}
.vl-review-table thead th {
  padding: var(--vl-space-3);
  background: var(--vl-color-subtle);
  font-size: var(--vl-text-sm);
  font-weight: 600;
}
.vl-review-table tbody th,
.vl-review-table tbody td {
  padding: var(--vl-space-3);
  border-bottom: 1px solid var(--vl-color-border);
  vertical-align: top;
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
