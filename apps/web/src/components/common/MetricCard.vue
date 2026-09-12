<template>
  <RouterLink
    v-if="href"
    class="vl-metric vl-metric--link"
    :to="href"
    :aria-label="`${title}:${displayValue},统计范围:${scopeLabel}`"
    v-bind="$attrs"
  >
    <p class="vl-metric__head">
      <span v-if="icon" class="vl-metric__icon" aria-hidden="true">
        <el-icon :size="18"><component :is="icon" /></el-icon>
      </span>
      <span class="vl-metric__title">{{ title }}</span>
    </p>
    <span class="vl-metric__body">
      <span class="vl-metric__value vl-number" :class="{ 'vl-metric__value--error': state === 'error' }" data-testid="metric-value">
        {{ displayValue }}<span v-if="value !== null && state !== 'error' && unit" class="vl-metric__unit">{{ unit }}</span>
      </span>
      <span v-if="sparkline && sparkline.length" class="vl-metric__spark">
        <SparklineChart :data="sparkline" />
      </span>
    </span>
    <p class="vl-metric__scope" data-testid="metric-scope">{{ scopeLabel }}</p>
    <p v-if="description" class="vl-metric__desc">{{ description }}</p>
  </RouterLink>
  <article v-else class="vl-metric" v-bind="$attrs">
    <p class="vl-metric__head">
      <span v-if="icon" class="vl-metric__icon" aria-hidden="true">
        <el-icon :size="18"><component :is="icon" /></el-icon>
      </span>
      <span class="vl-metric__title">{{ title }}</span>
    </p>
    <span class="vl-metric__body">
      <span class="vl-metric__value vl-number" :class="{ 'vl-metric__value--error': state === 'error' }" data-testid="metric-value">
        {{ displayValue }}<span v-if="value !== null && state !== 'error' && unit" class="vl-metric__unit">{{ unit }}</span>
      </span>
      <span v-if="sparkline && sparkline.length" class="vl-metric__spark">
        <SparklineChart :data="sparkline" />
      </span>
    </span>
    <p class="vl-metric__scope" data-testid="metric-scope">{{ scopeLabel }}</p>
    <p v-if="description" class="vl-metric__desc">{{ description }}</p>
  </article>
</template>

<script setup lang="ts">
// MetricCard — 风格规范 6.1/9.4 与 UI-10:null 显示「—」,0 显示 0,error 不显示数字;
// scopeLabel 必需常显(按后端 scope 赋值,不统一写「本周」);外层 testid 由调用方传入。
// 品牌化:语义图标 + 可选迷你趋势(趋势必须来自真实结果,不编造同比数字)。
import { computed, type Component } from 'vue'
import SparklineChart from './SparklineChart.vue'
import type { TrendPoint } from '../../types/domain'

const props = defineProps<{
  title: string
  value: number | null
  state?: 'success' | 'error'
  unit?: string
  description?: string
  /** 统计范围说明:「所选分析与筛选」/「本项目·所有分析」 */
  scopeLabel: string
  href?: string
  /** 语义图标(@element-plus/icons-vue 组件),装饰性 */
  icon?: Component
  /** 迷你趋势:仅当该指标确有对应时间序列时传入 */
  sparkline?: TrendPoint[]
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
  transition: border-color var(--vl-motion-fast) var(--vl-ease),
              box-shadow var(--vl-motion-fast) var(--vl-ease);
}
.vl-metric--link:hover,
.vl-metric--link:focus-visible {
  border-color: var(--vl-color-brand-line);
  box-shadow: var(--vl-shadow-float);
}
.vl-metric__head {
  display: flex;
  align-items: center;
  gap: var(--vl-space-2);
  margin: 0;
}
.vl-metric__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.75rem;
  height: 1.75rem;
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-brand-soft);
  color: var(--vl-color-brand);
  flex: none;
}
.vl-metric__title {
  font-size: var(--vl-text-sm);
  color: var(--vl-color-text-secondary);
}
.vl-metric__body {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--vl-space-3);
  margin-top: var(--vl-space-3);
}
.vl-metric__value {
  font-size: var(--vl-text-metric);
  line-height: 2.25rem;
  font-weight: 600;
  color: var(--vl-color-text);
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
.vl-metric__spark {
  flex: 1 1 auto;
  min-width: 3rem;
  max-width: 7rem;
}
.vl-metric__scope {
  margin: var(--vl-space-3) 0 0;
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
.vl-metric__desc {
  margin: var(--vl-space-1) 0 0;
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
</style>
