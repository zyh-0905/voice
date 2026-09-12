<template>
  <div class="vl-dist" data-testid="distribution-bar">
    <div class="vl-dist__track" role="img" :aria-label="ariaLabel">
      <span
        v-for="(segment, index) in visibleSegments"
        :key="segment.label"
        class="vl-dist__segment"
        :style="{ width: `${segment.percent}%`, background: segment.color }"
        :title="`${segment.label} ${segment.value}`"
      />
    </div>
    <ul class="vl-dist__legend">
      <li v-for="segment in segments" :key="segment.label" class="vl-dist__legend-item">
        <span class="vl-dist__swatch" :style="{ background: segment.color }" aria-hidden="true" />
        <span class="vl-dist__label">{{ segment.label }}</span>
        <span class="vl-dist__value vl-number">{{ segment.value }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
// DistributionBar — 构成分布(堆叠条 + 图例)。数值与图例同时给出,
// 不依赖颜色单独传达信息(风格规范 6.3/6.6)。颜色取自图表色板。
import { computed } from 'vue'

export interface DistributionSegment {
  label: string
  value: number
  /** CSS 变量引用,如 'var(--vl-chart-1)' 或 'var(--vl-color-danger)';只允许用 token */
  color: string
}

const props = defineProps<{
  segments: DistributionSegment[]
  /** 无障碍描述,如「风险严重度分布」 */
  label: string
}>()

const visibleSegments = computed(() => {
  const total = props.segments.reduce((sum, s) => sum + s.value, 0)
  if (total <= 0) return []
  return props.segments
    .filter(s => s.value > 0)
    .map(s => ({ ...s, percent: Math.round((s.value / total) * 100) }))
})

const ariaLabel = computed(() => {
  const parts = props.segments.map(s => `${s.label} ${s.value}`).join(',')
  return `${props.label}:${parts}`
})
</script>

<style scoped>
.vl-dist {
  display: grid;
  gap: var(--vl-space-3);
}
.vl-dist__track {
  display: flex;
  height: 0.5rem;
  border-radius: var(--vl-radius-sm);
  overflow: hidden;
  background: var(--vl-color-subtle);
}
.vl-dist__segment {
  display: block;
  height: 100%;
  transition: width var(--vl-motion-normal) var(--vl-ease);
}
.vl-dist__legend {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: var(--vl-space-2);
}
.vl-dist__legend-item {
  display: flex;
  align-items: center;
  gap: var(--vl-space-2);
  font-size: var(--vl-text-sm);
}
.vl-dist__swatch {
  width: 0.625rem;
  height: 0.625rem;
  border-radius: 0.1875rem;
  flex: none;
}
.vl-dist__label {
  flex: 1;
  min-width: 0;
  color: var(--vl-color-text-secondary);
}
.vl-dist__value {
  color: var(--vl-color-text);
  font-weight: 600;
}
</style>
