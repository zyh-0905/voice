<template>
  <span class="vl-badge" :class="`vl-badge--${appearance}`">
    {{ label }}
  </span>
</template>

<script setup lang="ts">
// StatusBadge — 风格规范 6.1/9.4:severity、任务状态、来源状态分别传入,禁止混为一个 enum;
// 文字+外观语义来自 lib/ui-status.ts,未知值安全回退。危险状态始终有文字,不只靠颜色。
import { computed } from 'vue'
import {
  reviewStateAppearance,
  reviewStateLabel,
  severityAppearance,
  severityLabel,
  sourceLabel,
  taskStatusAppearance,
  taskStatusLabel,
  type StatusAppearance,
} from '../../lib/ui-status'

const props = defineProps<{
  kind: 'task' | 'severity' | 'source' | 'review'
  state: string
}>()

const label = computed(() => {
  switch (props.kind) {
    case 'task':
      return taskStatusLabel(props.state)
    case 'severity':
      return severityLabel(props.state)
    case 'source':
      return sourceLabel(props.state)
    case 'review':
      return reviewStateLabel(props.state)
  }
})

const appearance = computed<StatusAppearance>(() => {
  switch (props.kind) {
    case 'task':
      return taskStatusAppearance(props.state)
    case 'severity':
      return severityAppearance(props.state)
    case 'source':
      return 'neutral'
    case 'review':
      return reviewStateAppearance(props.state)
  }
})
</script>

<style scoped>
.vl-badge {
  display: inline-block;
  border-radius: var(--vl-radius-sm);
  padding: 2px var(--vl-space-2);
  font-size: var(--vl-text-xs);
  line-height: 1.5;
  white-space: nowrap;
}
.vl-badge--neutral {
  color: var(--vl-color-text-secondary);
  background: var(--vl-color-subtle);
}
.vl-badge--info {
  color: var(--vl-color-info);
  background: var(--vl-color-info-bg);
}
.vl-badge--warning {
  color: var(--vl-color-warning);
  background: var(--vl-color-warning-bg);
}
.vl-badge--success {
  color: var(--vl-color-success);
  background: var(--vl-color-success-bg);
}
.vl-badge--danger {
  color: var(--vl-color-danger);
  background: var(--vl-color-danger-bg);
}
</style>
