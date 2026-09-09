<template>
  <div class="vl-filter-bar">
    <label class="vl-field">
      <span class="vl-filter-bar__label">分析</span>
      <el-select
        :model-value="filters.runId ?? ''"
        class="vl-filter-bar__select"
        placeholder="选择分析"
        clearable
        @update:model-value="(v: string) => emit('update:filters', { ...filters, runId: v || null })"
      >
        <el-option v-for="run in runs" :key="run.id" :label="run.label" :value="run.id" />
      </el-select>
    </label>
    <div class="vl-field vl-filter-bar__window">
      <span class="vl-filter-bar__label">时间窗口({{ timezoneLabel }})</span>
      <div class="vl-filter-bar__dates">
        <el-date-picker
          :model-value="filters.start"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="开始日期"
          :clearable="false"
          @update:model-value="(v: string | null) => emit('update:filters', { ...filters, start: v })"
        />
        <span class="vl-filter-bar__date-sep">至</span>
        <el-date-picker
          :model-value="filters.end"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="结束日期"
          :clearable="false"
          @update:model-value="(v: string | null) => emit('update:filters', { ...filters, end: v })"
        />
      </div>
    </div>
    <label class="vl-field">
      <span class="vl-filter-bar__label">渠道</span>
      <el-select
        :model-value="filters.channel ?? ''"
        class="vl-filter-bar__select"
        placeholder="全部渠道"
        clearable
        @update:model-value="(v: string) => emit('update:filters', { ...filters, channel: v || null })"
      >
        <el-option v-for="option in channels" :key="option.value" :label="option.label" :value="option.value" />
      </el-select>
    </label>
    <label class="vl-field">
      <span class="vl-filter-bar__label">产品</span>
      <el-select
        :model-value="filters.product ?? ''"
        class="vl-filter-bar__select"
        placeholder="全部产品"
        clearable
        @update:model-value="(v: string) => emit('update:filters', { ...filters, product: v || null })"
      >
        <el-option v-for="option in products" :key="option.value" :label="option.label" :value="option.value" />
      </el-select>
    </label>
    <VlButton v-if="hasActiveFilters" variant="ghost" @click="emit('clear')">清除筛选</VlButton>
  </div>
</template>

<script setup lang="ts">
// FilterBar — 风格规范 6.1/9.3:显示已生效条件与清除入口;文本筛选 300ms 去抖,
// 离散选择(下拉/日期)即时应用;URL 只保存 ID、时间和枚举。
import { computed } from 'vue'
import VlButton from './VlButton.vue'

export interface FilterValues {
  runId: string | null
  start: string | null
  end: string | null
  channel: string | null
  product: string | null
}

const props = defineProps<{
  filters: FilterValues
  runs?: Array<{ id: string; label: string }>
  channels?: Array<{ value: string; label: string }>
  products?: Array<{ value: string; label: string }>
  timezoneLabel?: string
}>()

const emit = defineEmits<{
  'update:filters': [value: FilterValues]
  clear: []
}>()

const runs = computed(() => props.runs ?? [])
const channels = computed(() => props.channels ?? [])
const products = computed(() => props.products ?? [])
const timezoneLabel = computed(() => props.timezoneLabel ?? 'Asia/Shanghai')

const hasActiveFilters = computed(
  () =>
    props.filters.runId !== null ||
    props.filters.start !== null ||
    props.filters.end !== null ||
    props.filters.channel !== null ||
    props.filters.product !== null,
)
</script>

<style scoped>
.vl-filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--vl-space-3);
  margin-bottom: var(--vl-space-4);
}
.vl-field {
  display: flex;
  flex-direction: column;
  gap: var(--vl-space-1);
}
.vl-filter-bar__label {
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
.vl-filter-bar__select {
  width: 10rem;
}
.vl-filter-bar__dates {
  display: flex;
  align-items: center;
  gap: var(--vl-space-2);
}
.vl-filter-bar__dates :deep(.el-date-editor) {
  width: 9rem;
}
.vl-filter-bar__date-sep {
  color: var(--vl-color-text-muted);
}
</style>
