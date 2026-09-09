<template>
  <p class="vl-demo-notice" data-testid="demo-notice">
    {{ text }}
    <span v-if="readOnly"> · 只读</span>
    <span v-if="computedAt"> · 计算时间 {{ computedAt }}</span>
  </p>
</template>

<script setup lang="ts">
// DemoNotice — 风格规范 6.1:小型蓝灰信息条,不做红色警报;始终区分合成演示、预计算演示和真实项目。
import { computed } from 'vue'

const props = defineProps<{
  sourceKind: 'synthetic' | 'precomputed' | 'real'
  readOnly?: boolean
  computedAt?: string
}>()

const text = computed(() => {
  switch (props.sourceKind) {
    case 'synthetic':
      return '合成演示数据,不代表真实业务结果'
    case 'precomputed':
      return '预计算演示数据'
    case 'real':
      return '真实项目数据'
  }
})
</script>

<style scoped>
.vl-demo-notice {
  margin: 0;
  display: inline-block;
  border: 1px solid var(--vl-color-info-bg);
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-info-bg);
  color: var(--vl-color-info);
  padding: var(--vl-space-1) var(--vl-space-3);
  font-size: var(--vl-text-xs);
}
</style>
