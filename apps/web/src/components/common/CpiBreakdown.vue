<template>
  <div class="vl-cpi" data-testid="cpi-breakdown">
    <template v-if="cpi">
      <p class="vl-cpi__value">
        CPI <b class="vl-number">{{ cpi.display_value }}</b>
        <span v-if="cpi.provisional" class="vl-cpi__provisional">暂定</span>
      </p>
      <ul v-if="cpi.components.length" class="vl-cpi__components">
        <li v-for="component in cpi.components" :key="component.label">
          <span>{{ component.label }}</span>
          <span class="vl-number">{{ component.displayValue }}</span>
          <span v-if="component.coverage !== null" class="vl-cpi__coverage">覆盖率 {{ component.coverage }}%</span>
        </li>
      </ul>
      <p v-if="cpi.coverage !== null" class="vl-cpi__meta">整体覆盖率 {{ cpi.coverage }}%</p>
    </template>
    <p v-else class="vl-cpi__meta">暂无 CPI 数据</p>
  </div>
</template>

<script setup lang="ts">
// CpiBreakdown — 风格规范 9.4/UI-11:CPI 是可解释指数,不是概率;
// 使用服务端 display_value,分项与覆盖率明确,缺项显式标注,不重新计算。
import type { CpiResult } from '../../types/domain'

defineProps<{
  cpi: CpiResult | null
}>()
</script>

<style scoped>
.vl-cpi__value {
  margin: 0 0 var(--vl-space-2);
  font-size: var(--vl-text-sm);
  color: var(--vl-color-text-secondary);
}
.vl-cpi__value b {
  font-size: var(--vl-text-lg);
  color: var(--vl-color-text);
}
.vl-cpi__provisional {
  margin-inline-start: var(--vl-space-2);
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-warning-bg);
  color: var(--vl-color-warning);
  padding: 2px var(--vl-space-2);
  font-size: var(--vl-text-xs);
}
.vl-cpi__components {
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: var(--vl-text-xs);
}
.vl-cpi__components li {
  display: flex;
  gap: var(--vl-space-2);
  padding: var(--vl-space-1) 0;
}
.vl-cpi__components li span:first-child {
  flex: 1;
  color: var(--vl-color-text-secondary);
}
.vl-cpi__coverage {
  color: var(--vl-color-text-muted);
}
.vl-cpi__meta {
  margin: var(--vl-space-2) 0 0;
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
</style>
