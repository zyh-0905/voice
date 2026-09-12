<template>
  <div class="vl-page">
    <PageHeader :icon="Warning" title="风险复核" description="待复核队列与原文;候选不是已确认事故,裁决须填写理由。">
      <template #actions>
        <VlButton variant="ghost" data-testid="view-pending" @click="filterPending = !filterPending">
          {{ filterPending ? '查看全部风险' : '只看待复核' }}
        </VlButton>
      </template>
    </PageHeader>


    <AsyncState :status="status" :message="error ?? undefined">
      <template #empty>
        <EmptyState text="当前筛选下没有风险候选" hint="风险候选来自规则扫描,不是已确认事故" />
      </template>

      <!-- 严重度构成:取自当前列表,不新增口径 -->
      <VlPanel v-if="items.length" title="严重度构成" :description="`共 ${items.length} 条候选`" class="vl-risks__dist">
        <DistributionBar :segments="severitySegments" label="风险严重度分布" />
      </VlPanel>

      <div class="vl-table-scroll">
        <table class="vl-table vl-risk-table" data-testid="risk-table">
          <thead>
            <tr>
              <th scope="col">风险候选</th>
              <th scope="col">严重度</th>
              <th scope="col">复核状态</th>
              <th scope="col">处置状态</th>
              <th scope="col"><span class="vl-sr-only">操作</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="risk in visible" :key="risk.id" :data-resource-id="risk.id">
              <th scope="row" class="vl-risk-table__title">
                {{ risk.title }}
                <span class="vl-risk-table__rule">{{ risk.rule }}</span>
              </th>
              <td><StatusBadge kind="severity" :state="risk.severity" /></td>
              <td><StatusBadge kind="review" :state="risk.reviewState" /></td>
              <td><StatusBadge kind="task" :state="risk.status" /></td>
              <td>
                <VlButton
                  v-if="canAct && risk.reviewState === 'pending'"
                  variant="secondary"
                  size="small"
                  data-testid="risk-confirm"
                  @click="openReview(risk)"
                >
                  复核并裁决
                </VlButton>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </AsyncState>

    <el-dialog
      v-model="reviewOpen"
      title="复核风险候选"
      width="480px"
      :close-on-click-modal="false"
      append-to-body
    >
      <div v-if="current" class="vl-risk-review">
        <p class="vl-risk-review__title">{{ current.title }}</p>
        <p class="vl-risk-review__meta">{{ current.rule }} · 合成演示数据,请对照原文核验</p>
        <div class="vl-field">
          <label for="vl-risk-reason" class="vl-risk-review__label">裁决理由(必填)</label>
          <textarea
            id="vl-risk-reason"
            v-model="reason"
            rows="3"
            class="vl-risk-review__input"
            placeholder="说明依据:命中规则、证据原文与业务上下文"
          ></textarea>
          <span v-if="reasonError" class="vl-risk-review__error" data-testid="risk-reason-error">请填写裁决理由</span>
          <span v-if="conflict" class="vl-risk-review__conflict" data-testid="risk-version-conflict">
            该候选已被其他人裁决,请关闭后重新加载再操作(你填写的内容不会被清空)。
          </span>
        </div>
        <div class="vl-risk-review__actions">
          <VlButton variant="danger" data-testid="risk-exclude" :loading="pending" @click="decide('excluded')">
            排除候选
          </VlButton>
          <VlButton variant="primary" data-testid="risk-confirm-submit" :loading="pending" @click="decide('confirmed')">
            确认风险
          </VlButton>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
// RisksPage — 工程计划 W14:待复核队列 + 原文 + 裁决区;
// severity 与 review_state 分开显示;critical 置顶;VIEWER 只读;复核理由必填。
// 真实模式:列表来自 GET /risks,裁决待服务端状态机端点。
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Warning } from '@element-plus/icons-vue'
import { useSessionStore } from '../../stores/session'
import { ApiHttpError, apiClient } from '../../api/client'
import PageHeader from '../../components/common/PageHeader.vue'
import VlButton from '../../components/common/VlButton.vue'
import StatusBadge from '../../components/common/StatusBadge.vue'
import AsyncState from '../../components/common/AsyncState.vue'
import DistributionBar, { type DistributionSegment } from '../../components/common/DistributionBar.vue'
import EmptyState from '../../components/common/EmptyState.vue'
import type { RiskItem } from '../../types/domain'

type RiskView = RiskItem & { version?: number }

const session = useSessionStore()
const canAct = computed(() => (session.user?.role ?? 'VIEWER') !== 'VIEWER')
const isDemoMode = import.meta.env.VITE_USE_MOCK !== 'false'
const client = apiClient()

const route = useRoute()
const projectId = computed(() => String(route.params.p))

const items = ref<RiskView[]>([])
const status = ref<'idle' | 'loading' | 'success' | 'empty' | 'error'>('idle')
const error = ref('')
const filterPending = ref(false)

onMounted(async () => {
  status.value = 'loading'
  try {
    items.value = await client.listRisks(projectId.value)
    status.value = items.value.length ? 'success' : 'empty'
  } catch (err) {
    status.value = 'error'
    error.value = err instanceof Error ? err.message : String(err)
  }
})

// 排序优先遵循后端:critical 置顶不能被美观排序覆盖
const visible = computed(() => {
  const list = filterPending.value ? items.value.filter(r => r.reviewState === 'pending') : items.value
  return [...list].sort((a, b) => Number(b.severity === 'CRITICAL') - Number(a.severity === 'CRITICAL'))
})

// 严重度构成:按当前列表聚合,颜色表达升级关系(规范 3.1:红色仅用于高严重度)
const SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'NONE'] as const
const SEVERITY_LABEL: Record<string, string> = { CRITICAL: '严重', HIGH: '高', MEDIUM: '中', LOW: '低', NONE: '无' }
const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: 'var(--vl-color-danger)',
  HIGH: 'var(--vl-color-brand-vivid)',
  MEDIUM: 'var(--vl-chart-6)',
  LOW: 'var(--vl-chart-2)',
  NONE: 'var(--vl-color-border-control)',
}
const severitySegments = computed<DistributionSegment[]>(() => {
  const counts = new Map<string, number>()
  for (const risk of items.value) counts.set(risk.severity, (counts.get(risk.severity) ?? 0) + 1)
  return SEVERITY_ORDER.filter(s => counts.has(s)).map(s => ({
    label: SEVERITY_LABEL[s] ?? s, value: counts.get(s) ?? 0, color: SEVERITY_COLOR[s] ?? 'var(--vl-color-border-control)',
  }))
})

const reviewOpen = ref(false)
const current = ref<RiskView | null>(null)
const reason = ref('')
const reasonError = ref(false)
const pending = ref(false)
const conflict = ref(false)

function openReview(risk: RiskView) {
  current.value = risk
  reason.value = ''
  reasonError.value = false
  reviewOpen.value = true
}

async function decide(decision: 'confirmed' | 'excluded') {
  if (!reason.value.trim()) {
    reasonError.value = true
    return
  }
  const target = current.value
  if (!target) return
  pending.value = true
  conflict.value = false
  try {
    // 等待服务端确认,不做误导性的乐观更新(规范 9.3)
    const updated = await client.reviewRisk(projectId.value, target.id, {
      decision, reason: reason.value.trim(), expected_version: target.version,
    })
    const index = items.value.findIndex(r => r.id === updated.id)
    if (index >= 0) items.value[index] = updated
    reviewOpen.value = false
    current.value = null
    reason.value = ''
  } catch (err) {
    if (err instanceof ApiHttpError && err.status === 409) {
      // 版本冲突:保留本地输入,提示重新加载
      conflict.value = true
    } else if (err instanceof ApiHttpError && err.status === 403) {
      reasonError.value = true
      error.value = '当前角色无权裁决风险'
    } else {
      error.value = err instanceof Error ? err.message : '裁决失败,请稍后重试'
    }
  } finally {
    pending.value = false
  }
}
</script>

<style scoped>
.vl-risks__note {
  margin: 0 0 var(--vl-space-4);
  padding: var(--vl-space-2) var(--vl-space-3);
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-info-bg);
  color: var(--vl-color-info);
  font-size: var(--vl-text-xs);
}
.vl-risks__dist {
  margin-bottom: var(--vl-space-4);
}
.vl-risk-table__title {
  font-weight: 600;
}
.vl-risk-table__rule {
  display: block;
  font-size: var(--vl-text-xs);
  font-weight: 400;
  color: var(--vl-color-text-muted);
}
.vl-risk-review__title {
  margin: 0 0 var(--vl-space-1);
  font-weight: 600;
}
.vl-risk-review__meta {
  margin: 0 0 var(--vl-space-4);
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
.vl-risk-review__label {
  display: block;
  margin-bottom: var(--vl-space-2);
}
.vl-risk-review__input {
  width: 100%;
  min-height: var(--vl-control-height-touch);
  border: 1px solid var(--vl-color-border-control);
  border-radius: var(--vl-radius-control);
  padding: var(--vl-space-2) var(--vl-space-3);
  font: inherit;
}
.vl-risk-review__error {
  display: block;
  margin-top: var(--vl-space-1);
  color: var(--vl-color-danger);
  font-size: var(--vl-text-xs);
}
.vl-risk-review__conflict {
  display: block;
  margin-top: var(--vl-space-2);
  padding: var(--vl-space-2) var(--vl-space-3);
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-warning-bg);
  color: var(--vl-color-warning);
  font-size: var(--vl-text-xs);
}
.vl-risk-review__actions {
  display: flex;
  gap: var(--vl-space-3);
  margin-top: var(--vl-space-4);
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
</style>
