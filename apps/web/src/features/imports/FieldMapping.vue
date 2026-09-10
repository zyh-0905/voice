<template>
  <form class="vl-mapping" data-testid="field-mapping" @submit.prevent="submit">
    <p class="vl-mapping__hint">确认字段含义后继续;原始数据在分析前脱敏。</p>
    <div class="vl-mapping__grid">
      <label v-for="row in rows" :key="row.source" class="vl-field vl-mapping__field">
        <span class="vl-mapping__source vl-number">{{ row.source }}</span>
        <span class="vl-mapping__arrow" aria-hidden="true">→</span>
        <span class="vl-mapping__label">字段含义</span>
        <input
          v-model="mapped[row.source]"
          class="vl-mapping__input"
          :name="row.source"
          :aria-label="`${row.source} 的目标字段`"
          placeholder="请输入目标字段名"
          @blur="validateField(row.source)"
        />
        <span v-if="errors[row.source]" class="vl-mapping__error" data-testid="mapping-field-error">{{ errors[row.source] }}</span>
      </label>
    </div>
    <p v-if="formError" class="vl-mapping__form-error" data-testid="mapping-form-error" role="alert">{{ formError }}</p>
    <div class="vl-mapping__actions">
      <VlButton type="submit" data-testid="mapping-next">确认并生成治理报告</VlButton>
    </div>
  </form>
</template>

<script setup lang="ts">
// FieldMapping — 工程计划 W05:映射必填验证;报错聚焦第一个错误字段,不清空用户输入。
import { reactive, ref, nextTick } from 'vue'
import VlButton from '../../components/common/VlButton.vue'

const emit = defineEmits<{ next: [] }>()

const rows = [
  { source: 'call_id', default: '通话 ID' },
  { source: 'transcript', default: '转写文本' },
  { source: 'agent', default: '坐席' },
]

const mapped = reactive<Record<string, string>>(Object.fromEntries(rows.map(r => [r.source, r.default])))
const errors = reactive<Record<string, string>>({})
const formError = ref('')

function validateField(source: string): boolean {
  if (!mapped[source].trim()) {
    errors[source] = '该字段必须指定目标名称'
    return false
  }
  delete errors[source]
  return true
}

function focusFirstError() {
  const first = rows.find(r => errors[r.source])
  if (!first) return
  nextTick(() => {
    const el = document.querySelector<HTMLInputElement>(`input[name="${first.source}"]`)
    el?.focus()
  })
}

function submit() {
  let valid = true
  for (const row of rows) if (!validateField(row.source)) valid = false
  if (!valid) {
    formError.value = '请先补全必填字段'
    focusFirstError()
    return
  }
  formError.value = ''
  emit('next')
}
</script>

<style scoped>
.vl-mapping__hint {
  margin: 0 0 var(--vl-space-4);
  color: var(--vl-color-text-muted);
}
.vl-mapping__grid {
  display: grid;
  gap: var(--vl-space-4);
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
}
.vl-mapping__field {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: var(--vl-space-2);
}
.vl-mapping__label {
  grid-column: 1 / -1;
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
.vl-mapping__input {
  grid-column: 1 / -1;
  min-height: var(--vl-control-height);
  border: 1px solid var(--vl-color-border-control);
  border-radius: var(--vl-radius-control);
  padding: 0 var(--vl-space-3);
}
.vl-mapping__error {
  grid-column: 1 / -1;
  color: var(--vl-color-danger);
  font-size: var(--vl-text-xs);
}
.vl-mapping__form-error {
  margin: var(--vl-space-4) 0 0;
  color: var(--vl-color-danger);
}
.vl-mapping__actions {
  margin-top: var(--vl-space-5);
}
</style>
