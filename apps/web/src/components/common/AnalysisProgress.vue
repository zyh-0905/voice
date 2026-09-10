<template>
  <div class="vl-import-progress" :data-stage="stage">
    <div class="vl-import-progress__track" role="presentation">
      <span
        v-for="item in items"
        :key="item.key"
        class="vl-import-progress__step"
        :class="{
          'vl-import-progress__step--active': item.key === stage,
          'vl-import-progress__step--done': item.key !== stage && doneKeys.has(item.key),
        }"
        :style="{ width: `${100 / items.length}%` }"
      >{{ item.label }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
// AnalysisProgress(导入进度)— 工程计划 W05/W06:只有真实 total 才显示百分比,
// 阶段改变才播报;不伪造定时进度。
import { computed } from 'vue'

const props = defineProps<{
  stage: string
  completed: number | null
  total: number | null
}>()

const items = [
  { key: 'queued', label: '排队中' },
  { key: 'running', label: '分析中' },
  { key: 'done', label: '已完成' },
]

const percent = computed(() =>
  props.total && props.total > 0 && props.completed !== null
    ? Math.round((props.completed / props.total) * 100)
    : null,
)
const doneKeys = computed(() => new Set(items.slice(0, items.findIndex(i => i.key === props.stage) + 1).map(i => i.key)))
</script>

<style scoped>
.vl-import-progress__track {
  display: flex;
  gap: var(--vl-space-2);
}
.vl-import-progress__step {
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-subtle);
  color: var(--vl-color-text-muted);
  text-align: center;
  font-size: var(--vl-text-xs);
  padding: var(--vl-space-2) 0;
}
.vl-import-progress__step--active {
  background: var(--vl-color-brand-soft);
  color: var(--vl-color-brand);
  font-weight: 600;
}
.vl-import-progress__step--done {
  background: var(--vl-color-success-bg);
  color: var(--vl-color-success);
}
</style>
