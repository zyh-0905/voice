<template>
  <div class="vl-import-health" data-testid="import-health">
    <ul class="vl-import-health__rows">
      <li><span class="vl-import-health__label">输入行</span><b class="vl-number" data-testid="input-rows">{{ health.inputRows }}</b></li>
      <li><span class="vl-import-health__label">有效行</span><b class="vl-number" data-testid="valid-rows">{{ health.validRows }}</b></li>
      <li><span class="vl-import-health__label">无效行</span><b class="vl-number" data-testid="invalid-rows">{{ health.invalidRows }}</b></li>
      <li><span class="vl-import-health__label">重复行</span><b class="vl-number" data-testid="duplicate-rows">{{ health.duplicateRows }}</b></li>
      <li><span class="vl-import-health__label">脱敏行</span><b class="vl-number" data-testid="redacted-rows">{{ health.redactedRows }}</b></li>
      <li><span class="vl-import-health__label">缺失时间</span><b class="vl-number" data-testid="undated-rows">{{ health.undatedRows }}</b></li>
    </ul>
  </div>
</template>

<script setup lang="ts">
// ImportHealth — 工程计划 W05:互斥计数与脱敏/缺时间交叉属性分开展示。
// 脱敏行、缺失时间行是交叉属性,不改变有效行总数。
import type { ImportHealthView } from '../../types/domain'

defineProps<{
  health: ImportHealthView
}>()
</script>

<style scoped>
.vl-import-health__rows {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr));
  gap: var(--vl-space-3);
}
.vl-import-health__rows li {
  border: 1px solid var(--vl-color-border);
  border-radius: var(--vl-radius-control);
  background: var(--vl-color-subtle);
  padding: var(--vl-space-3);
}
.vl-import-health__label {
  display: block;
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
.vl-import-health__rows b {
  display: block;
  margin-top: var(--vl-space-1);
  font-size: var(--vl-text-lg);
}
</style>
