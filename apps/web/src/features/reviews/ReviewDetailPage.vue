<template>
  <div class="vl-page">
    <PageHeader title="复盘详情" description="固定口径的对照结果:原始数量与分母始终可见,结论受可比性限制。">
      <template #actions>
        <VlButton variant="ghost" @click="goBack">返回复盘列表</VlButton>
      </template>
    </PageHeader>

    <AsyncState :status="status" :message="error ?? undefined" empty-message="复盘记录不存在或已被删除。">
      <template #error>
        <p class="vl-review-detail__error">暂时无法获取复盘记录,请稍后重试。</p>
        <VlButton variant="secondary" @click="load">重试</VlButton>
      </template>

      <template v-if="record">
        <VlPanel title="对照结果" :description="`run ${record.run_id} · revision ${record.revision}`">
          <WindowCompare :before="record.before" :after="record.after" :comparability="record.comparability" />
        </VlPanel>

        <VlPanel title="统计明细" description="百分点用于占比变化,相对变化单独标注「相对」">
          <dl class="vl-review-detail__metrics">
            <template v-if="metricsVisible">
              <dt>命中数变化</dt>
              <dd class="vl-number" data-testid="review-count-change">{{ signed(record.metrics!.count_change) }}</dd>
              <dt>复盘前占比</dt>
              <dd class="vl-number" data-testid="review-before-pp">{{ percent(record.metrics!.share_before_pp) }}</dd>
              <dt>复盘后占比</dt>
              <dd class="vl-number" data-testid="review-after-pp">{{ percent(record.metrics!.share_after_pp) }}</dd>
              <dt>占比变化</dt>
              <dd class="vl-number" data-testid="review-delta-pp">
                {{ record.metrics!.share_delta_pp === null ? '—' : `${record.metrics!.share_delta_pp} 个百分点` }}
              </dd>
              <dt>相对变化</dt>
              <dd class="vl-number" data-testid="review-relative">
                {{ record.metrics!.relative_share_change === null ? '—' : `相对 ${(record.metrics!.relative_share_change * 100).toFixed(1)}%` }}
              </dd>
            </template>
            <dt>结论状态</dt>
            <dd data-testid="review-effect">{{ conclusionLabel }}</dd>
          </dl>
          <!-- low_sample 保留原始数量,但不得宣称任何变化结论 -->
          <p v-if="record.comparability === 'low_sample'" class="vl-review-detail__warning" data-testid="review-low-sample-note">
            样本量不足(N&lt;50),仅展示原始数量与分母,不输出变化结论。
          </p>
        </VlPanel>

        <VlPanel v-if="record.comparability !== 'ok' && record.reasons.length" title="不可比原因">
          <ul class="vl-review-detail__limits" data-testid="review-reasons">
            <li v-for="(reason, index) in record.reasons" :key="index">{{ reason }}</li>
          </ul>
        </VlPanel>

        <VlPanel title="限制说明">
          <ul class="vl-review-detail__limits" data-testid="review-limitations">
            <li v-for="(line, index) in limitations" :key="index">{{ line }}</li>
          </ul>
        </VlPanel>
      </template>
    </AsyncState>
  </div>
</template>

<script setup lang="ts">
// ReviewDetailPage — 工程计划 W18:百分点不写成百分比;相对变化必须标「相对」;
// 数据不足不显示绿色改善结论;不宣称因果。
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '../../components/common/PageHeader.vue'
import VlPanel from '../../components/common/VlPanel.vue'
import VlButton from '../../components/common/VlButton.vue'
import AsyncState from '../../components/common/AsyncState.vue'
import WindowCompare from '../../components/common/WindowCompare.vue'
import { ApiHttpError, apiClient } from '../../api/client'
import { comparabilityLabel, effectStatusLabel } from '../../lib/ui-status'
import type { ReviewRecord } from '../../types/domain'

const route = useRoute()
const router = useRouter()
const client = apiClient()

const projectId = computed(() => String(route.params.p))
const reviewId = computed(() => String(route.params.r))

const status = ref<'idle' | 'loading' | 'success' | 'empty' | 'error'>('idle')
const error = ref('')
const record = ref<ReviewRecord | null>(null)

async function load() {
  status.value = 'loading'
  try {
    record.value = await client.getReview(projectId.value, reviewId.value)
    status.value = 'success'
  } catch (err) {
    if (err instanceof ApiHttpError && err.status === 404) {
      status.value = 'empty'
      return
    }
    status.value = 'error'
    error.value = err instanceof Error ? err.message : String(err)
  }
}
onMounted(load)

/** metrics 仅在 ok / low_sample 时非空;只有 ok 允许展示变化数字 */
const metricsVisible = computed(() => record.value?.comparability === 'ok' && record.value.metrics !== null)

const conclusionLabel = computed(() => {
  if (!record.value) return '—'
  if (record.value.comparability === 'ok') return effectStatusLabel(record.value.effect_status)
  return record.value.comparability === 'low_sample' ? '样本量不足,不输出结论' : comparabilityLabel(record.value.comparability)
})

const limitations = computed(() => {
  if (!record.value) return []
  const base = [...record.value.limitations]
  if (record.value.comparability === 'ok') {
    base.push('观察到反馈占比变化;仅为描述性比较,不能据此证明因果关系。')
  } else if (record.value.comparability === 'low_sample') {
    base.push('样本量不足(N<50),不输出变化结论。')
  } else {
    base.push('数据不足或口径不可比,不输出变化结论。')
  }
  base.push('复盘结果生成后不再变化;改变筛选条件请新建复盘。')
  return base
})

function signed(value: number | null): string {
  if (value === null) return '—'
  return value > 0 ? `+${value}` : String(value)
}
function percent(value: number | null): string {
  return value === null ? '—' : `${value.toFixed(1)}%`
}
function goBack() {
  void router.push(`/p/${projectId.value}/reviews`)
}
</script>

<style scoped>
.vl-review-detail {
  display: grid;
  gap: var(--vl-space-4);
}
.vl-review-detail__metrics {
  display: grid;
  grid-template-columns: 8rem 1fr;
  gap: var(--vl-space-2) var(--vl-space-3);
  margin: 0;
  font-size: var(--vl-text-sm);
}
.vl-review-detail__metrics dt {
  color: var(--vl-color-text-muted);
}
.vl-review-detail__metrics dd {
  margin: 0;
}
.vl-review-detail__limits {
  margin: 0;
  padding-inline-start: var(--vl-space-5);
  color: var(--vl-color-text-secondary);
  font-size: var(--vl-text-sm);
}
.vl-review-detail__error {
  color: var(--vl-color-danger);
}
.vl-review-detail__warning {
  margin: var(--vl-space-4) 0 0;
  padding: var(--vl-space-2) var(--vl-space-3);
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-warning-bg);
  color: var(--vl-color-warning);
  font-size: var(--vl-text-xs);
}
</style>
