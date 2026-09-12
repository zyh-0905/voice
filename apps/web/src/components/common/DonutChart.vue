<template>
  <div class="vl-donut" data-testid="donut-chart">
    <svg class="vl-donut__svg" viewBox="0 0 42 42" role="img" :aria-label="ariaLabel">
      <circle class="vl-donut__track" cx="21" cy="21" r="15.915" />
      <circle
        v-for="slice in slices"
        :key="slice.label"
        class="vl-donut__slice"
        cx="21"
        cy="21"
        r="15.915"
        :stroke="slice.color"
        :stroke-dasharray="`${slice.percent} ${100 - slice.percent}`"
        :stroke-dashoffset="slice.offset"
      />
    </svg>
    <div class="vl-donut__center" aria-hidden="true">
      <span class="vl-donut__total vl-number">{{ total }}</span>
      <span class="vl-donut__total-label">{{ totalLabel }}</span>
    </div>
    <ul class="vl-donut__legend">
      <li v-for="slice in slices" :key="slice.label" class="vl-donut__legend-item">
        <span class="vl-donut__swatch" :style="{ background: slice.color }" aria-hidden="true" />
        <span class="vl-donut__label">{{ slice.label }}</span>
        <span class="vl-donut__value vl-number">{{ slice.value }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
// DonutChart — 构成占比(环形 + 图例 + 中心合计)。中心数字与图例给出精确值,
// 不靠颜色单独传达;占比按本图内各段合计计算,不冒充其它口径。
import { computed } from 'vue'
import type { DistributionSegment } from './DistributionBar.vue'

const props = defineProps<{
  segments: DistributionSegment[]
  label: string
  totalLabel?: string
}>()

const total = computed(() => props.segments.reduce((sum, s) => sum + s.value, 0))

const slices = computed(() => {
  const sum = total.value
  if (sum <= 0) return []
  let offset = 25 // 从 12 点方向起始
  return props.segments
    .filter(s => s.value > 0)
    .map((s) => {
      const percent = (s.value / sum) * 100
      const slice = { ...s, percent, offset }
      offset -= percent
      return slice
    })
})

const ariaLabel = computed(() => {
  const parts = props.segments.map(s => `${s.label} ${s.value}`).join(',')
  return `${props.label},合计 ${total.value}:${parts}`
})
</script>

<style scoped>
.vl-donut {
  position: relative;
  display: grid;
  justify-items: center;
  gap: var(--vl-space-4);
}
.vl-donut__svg {
  width: 8.5rem;
  height: 8.5rem;
  transform: rotate(-0deg);
}
.vl-donut__track {
  fill: none;
  stroke: var(--vl-color-subtle);
  stroke-width: 5;
}
.vl-donut__slice {
  fill: none;
  stroke-width: 5;
  transition: stroke-dasharray var(--vl-motion-normal) var(--vl-ease);
}
.vl-donut__center {
  position: absolute;
  top: 3.25rem;
  display: grid;
  justify-items: center;
  line-height: 1.1;
}
.vl-donut__total {
  font-size: var(--vl-text-lg);
  font-weight: 600;
  color: var(--vl-color-text);
}
.vl-donut__total-label {
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
.vl-donut__legend {
  list-style: none;
  margin: 0;
  padding: 0;
  width: 100%;
  display: grid;
  gap: var(--vl-space-2);
}
.vl-donut__legend-item {
  display: flex;
  align-items: center;
  gap: var(--vl-space-2);
  font-size: var(--vl-text-sm);
}
.vl-donut__swatch {
  width: 0.625rem;
  height: 0.625rem;
  border-radius: 0.1875rem;
  flex: none;
}
.vl-donut__label {
  flex: 1;
  min-width: 0;
  color: var(--vl-color-text-secondary);
}
.vl-donut__value {
  font-weight: 600;
}
</style>
