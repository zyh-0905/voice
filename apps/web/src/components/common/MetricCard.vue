<template>
  <RouterLink
    v-if="href"
    class="vl-metric vl-metric--link"
    :to="href"
    :aria-label="`${title}:${displayValue},统计范围:${scopeLabel}`"
    v-bind="$attrs"
  >
    <p class="vl-metric__title">{{ title }}</p>
    <p class="vl-metric__value vl-number" :class="{ 'vl-metric__value--error': state === 'error' }" data-testid="metric-value">
      {{ displayValue }}<span v-if="value !== null && state !== 'error' && unit" class="vl-metric__unit">{{ unit }}</span>
    </p>
    <p class="vl-metric__scope" data-testid="metric-scope">{{ scopeLabel }}</p>
    <p v-if="description" class="vl-metric__desc">{{ description }}</p>
  </RouterLink>
  <article v-else class="vl-metric" v-bind="$attrs">
    <p class="vl-metric__title">{{ title }}</p>
    <p class="vl-metric__value vl-number" :class="{ 'vl-metric__value--error': state === 'error' }" data-testid="metric-value">
      {{ displayValue }}<span v-if="value !== null && state !== 'error' && unit" class="vl-metric__unit">{{ unit }}</span>
    </p>
    <p class="vl-metric__scope" data-testid="metric-scope">{{ scopeLabel }}</p>
    <p v-if="description" class="vl-metric__desc">{{ description }}</p>
  </article>
</template>

<script setup lang="ts">
// MetricCard — 风格规范 6.1/9.4 与 UI-10:null 显示「—」,0 显示 0,error 不显示数字;
// scopeLabel 必需常显(按后端 scope 赋值,不统一写「本周」);
// 外层 testid 由调用方通过 attrs 传入(如 metric-pending-risks),内部提供 metric-value/metric-scope。
import { computed } from 'vue'

const props = defineProps<{
  title: string
  value: number | null
  state?: 'success' | 'error'
  unit?: string
  description?: string
  /** 统计范围说明:「所选分析与筛选」/「本项目·所有分析」 */
  scopeLabel: string
  href?: string
}>()

const displayValue = computed(() => {
  if (props.state === 'error') return '获取失败'
  if (props.value === null) return '—'
  return new Intl.NumberFormat('zh-CN').format(props.value)
})
</script>

<style scoped>
.vl-metric {
  display: block;
  text-decoration: none;
  color: inherit;
  min-width: 0;
  border: 1px solid var(--vl-color-border);
  border-radius: var(--vl-radius-panel);
  background: var(--vl-color-surface);
  padding: var(--vl-space-5);
  box-shadow: var(--vl-shadow-panel);
}
.vl-metric--link {
  transition: border-color var(--vl-motion-fast) var(--vl-ease);
}
.vl-metric--link:hover,
.vl-metric--link:focus-visible {
  border-color: var(--vl-color-brand);
}
.vl-metric__title {
  margin: 0;
  font-size: var(--vl-text-sm);
  color: var(--vl-color-text-secondary);
}
.vl-metric__value {
  margin: var(--vl-space-2) 0 0;
  font-size: var(--vl-text-metric);
  line-height: 2.25rem;
  font-weight: 600;
}
.vl-metric__value--error {
  color: var(--vl-color-danger);
  font-size: var(--vl-text-lg);
  line-height: var(--vl-space-8);
}
.vl-metric__unit {
  margin-inline-start: var(--vl-space-1);
  font-size: var(--vl-text-sm);
  font-weight: 400;
  color: var(--vl-color-text-muted);
}
.vl-metric__scope {
  margin: var(--vl-space-2) 0 0;
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
.vl-metric__desc {
  margin: var(--vl-space-2) 0 0;
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
</style>
