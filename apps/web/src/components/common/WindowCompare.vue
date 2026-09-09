<template>
  <div class="vl-review" data-testid="review-window-compare">
    <div class="vl-review__stats">
      <div class="vl-review__stat">
        <span class="vl-review__label">复盘前</span>
        <b class="vl-number" data-testid="review-before-share">{{ formatPercent(beforeShare) }}</b>
        <span class="vl-review__meta vl-number">{{ before.n.toLocaleString() }} / {{ before.N.toLocaleString() }}</span>
      </div>
      <div class="vl-review__delta">
        <span class="vl-review__label">变化</span>
        <b class="vl-number" data-testid="review-share-delta">{{ delta }}</b>
      </div>
      <div class="vl-review__stat">
        <span class="vl-review__label">复盘后</span>
        <b class="vl-number" data-testid="review-after-share">{{ formatPercent(afterShare) }}</b>
        <span class="vl-review__meta vl-number">{{ after.n.toLocaleString() }} / {{ after.N.toLocaleString() }}</span>
      </div>
    </div>
    <p v-if="comparable" class="vl-review__note">观察到反馈占比变化;仅为描述性比较,不能据此证明因果关系。</p>
    <p v-else class="vl-review__note vl-review__note--insufficient">数据不足,暂不输出变化结论。</p>
  </div>
</template>

<script setup lang="ts">
// WindowCompare — 工程计划 W18:n/N、占比、百分点、相对变化与可比性限制;
// 数据不足不显示绿色改善结论;数量与分母始终可见。
import { computed } from 'vue'

const props = defineProps<{
  before: { n: number; N: number }
  after: { n: number; N: number }
}>()

const beforeShare = computed(() => (props.before.N > 0 ? (props.before.n / props.before.N) * 100 : 0))
const afterShare = computed(() => (props.after.N > 0 ? (props.after.n / props.after.N) * 100 : 0))
const comparable = computed(() => props.before.N > 0 && props.after.N > 0)
const delta = computed(() => (comparable.value ? `${(afterShare.value - beforeShare.value).toFixed(1)} 个百分点` : '—'))

function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`
}
</script>

<style scoped>
.vl-review__stats {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: var(--vl-space-4);
  align-items: center;
}
.vl-review__stat,
.vl-review__delta {
  border: 1px solid var(--vl-color-border);
  border-radius: var(--vl-radius-panel);
  background: var(--vl-color-surface);
  padding: var(--vl-space-4);
  text-align: center;
}
.vl-review__label {
  display: block;
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
.vl-review__stat b,
.vl-review__delta b {
  display: block;
  margin-top: var(--vl-space-1);
  font-size: var(--vl-text-lg);
}
.vl-review__meta {
  display: block;
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
.vl-review__note {
  margin: var(--vl-space-4) 0 0;
  font-size: var(--vl-text-sm);
  color: var(--vl-color-text-secondary);
}
.vl-review__note--insufficient {
  color: var(--vl-color-warning);
}
</style>
