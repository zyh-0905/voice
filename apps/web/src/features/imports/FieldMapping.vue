<template>
  <form class="vl-mapping" data-testid="field-mapping" @submit.prevent="submit">
    <p class="vl-mapping__hint">
      确认字段含义后继续;原始数据在分析前脱敏。每列可以选择「不导入」。
    </p>

    <!-- 工作表选择:§4.3 的顺序是「上传 → 选工作表/映射 → 治理」。
         只有多于一张表时才出现——单表工作簿没有可选的余地。 -->
    <label v-if="sheetNames.length > 1" class="vl-field vl-mapping__sheet">
      <span class="vl-mapping__label">工作表</span>
      <select
        v-model="selectedSheet"
        class="vl-mapping__input"
        data-testid="sheet-select"
        aria-label="选择工作表"
      >
        <option v-for="name in sheetNames" :key="name" :value="name">{{ name }}</option>
      </select>
    </label>

    <p v-if="!rows.length" class="vl-mapping__empty" data-testid="mapping-empty">
      这个批次没有可识别的列,无法建立映射。请返回上一步确认文件内容。
    </p>

    <div v-else class="vl-mapping__grid">
      <label v-for="row in rows" :key="row.source" class="vl-field vl-mapping__field">
        <span class="vl-mapping__source vl-number">{{ row.source }}</span>
        <span class="vl-mapping__arrow" aria-hidden="true">→</span>
        <span class="vl-mapping__label">字段含义</span>
        <select
          v-model="mapped[row.source]"
          class="vl-mapping__input"
          :name="row.source"
          :aria-label="`${row.source} 的目标字段`"
          data-testid="mapping-target"
        >
          <option value="">不导入</option>
          <option v-for="field in standardFields" :key="field.value" :value="field.value">
            {{ field.label }}
          </option>
        </select>
        <span v-if="errors[row.source]" class="vl-mapping__error" data-testid="mapping-field-error">
          {{ errors[row.source] }}
        </span>
      </label>
    </div>

    <label class="vl-field vl-mapping__policy">
      <span class="vl-mapping__label">时间字段策略</span>
      <select v-model="timePolicy" class="vl-mapping__input" data-testid="time-policy" aria-label="时间字段策略">
        <option value="static">静态:缺时间的行仍然导入(标 missing)</option>
        <option value="strict">严格:缺时间的行判无效</option>
      </select>
    </label>

    <p v-if="formError" class="vl-mapping__form-error" data-testid="mapping-form-error" role="alert">
      {{ formError }}
    </p>
    <div class="vl-mapping__actions">
      <VlButton type="submit" data-testid="mapping-next">确认并生成治理报告</VlButton>
    </div>
  </form>
</template>

<script setup lang="ts">
// FieldMapping — 工程计划 W05 / §4.3:映射必填验证;报错聚焦第一个错误字段,不清空用户输入。
//
// **列来自上传响应,不再是写死的三列。** 此前这一屏渲染的是固定的
// call_id / transcript / agent 并就地校验,`emit('next')` **不带任何数据**——
// 用户填的映射被丢弃,而流程看起来完全正常(向导走到下一步、报告也出来了)。
// 现在把真实列名与映射一起交出去,由 ImportPage 送到 /validate。
import { computed, reactive, ref, nextTick, watch } from 'vue'
import VlButton from '../../components/common/VlButton.vue'
import type { StandardField } from '../../types/domain'

const props = defineProps<{
  /** 来源列名,来自上传响应的 preview.headers */
  headers: string[]
  /** XLSX 的全部工作表名;非 XLSX 或单表时为空 */
  sheetNames: string[]
  sheetName: string | null
  /** 同名识别的初值:服务端会按列名自动匹配标准字段 */
  initialMapping?: Record<string, string>
}>()

const emit = defineEmits<{
  next: [payload: { mapping: Record<string, string>; sheetName: string | null; timePolicy: 'strict' | 'static' }]
}>()

// 与服务端 STANDARD_FIELDS 一致(4.2);label 是给人看的,value 是契约
const standardFields: { value: StandardField; label: string }[] = [
  { value: 'content', label: '反馈正文(必填)' },
  { value: 'feedback_id', label: '来源编号' },
  { value: 'created_at', label: '发生时间' },
  { value: 'channel', label: '渠道' },
  { value: 'product', label: '产品' },
  { value: 'rating', label: '评分' },
  { value: 'order_id', label: '订单号' },
  { value: 'status', label: '来源状态' },
]

const rows = computed(() => props.headers.map(source => ({ source })))
const mapped = reactive<Record<string, string>>(buildInitial())
const errors = reactive<Record<string, string>>({})
const formError = ref('')
const selectedSheet = ref<string | null>(props.sheetName)
const timePolicy = ref<'strict' | 'static'>('static')

function buildInitial(): Record<string, string> {
  const initial: Record<string, string> = {}
  // 同名识别:服务端 validate_mapping 对未提供映射时也做这件事,这里只是把
  // 它做在界面上,让用户看得见自动匹配了什么,而不是提交后才发现
  for (const source of props.headers) {
    initial[source] = props.initialMapping?.[source]
      ?? (standardFields.some(f => f.value === source) ? source : '')
  }
  return initial
}

// 换工作表会换掉列,映射要跟着重建——否则会把上一张表的映射提交给新表
watch(() => props.headers, () => {
  Object.keys(mapped).forEach(key => delete mapped[key])
  Object.assign(mapped, buildInitial())
  Object.keys(errors).forEach(key => delete errors[key])
})

function validateField(source: string): boolean {
  if (mapped[source] && !standardFields.some(field => field.value === mapped[source])) {
    errors[source] = '目标字段不在标准字段内'
    return false
  }
  delete errors[source]
  return true
}

function focusFirstError() {
  const first = rows.value.find(row => errors[row.source])
  if (!first) return
  nextTick(() => {
    document.querySelector<HTMLSelectElement>(`select[name="${first.source}"]`)?.focus()
  })
}

function submit() {
  let valid = true
  for (const row of rows.value) if (!validateField(row.source)) valid = false
  // 正文是必填(4.2):映射必须落在 content 上,否则服务端会以 invalid_mapping 拒绝
  const targets = Object.values(mapped).filter(Boolean)
  if (targets.length && !targets.includes('content')) {
    formError.value = '必须把某一列映射到「反馈正文」'
    focusFirstError()
    return
  }
  if (!valid) {
    formError.value = '请先修正映射'
    focusFirstError()
    return
  }
  formError.value = ''
  emit('next', {
    // 只送真正选了目标的列;空值表示「不导入」
    mapping: Object.fromEntries(Object.entries(mapped).filter(([, target]) => !!target)),
    sheetName: selectedSheet.value,
    timePolicy: timePolicy.value,
  })
}
</script>

<style scoped>
.vl-mapping__hint {
  margin: 0 0 var(--vl-space-4);
  color: var(--vl-color-text-muted);
}
.vl-mapping__empty {
  margin: var(--vl-space-4) 0;
  color: var(--vl-color-text-muted);
}
.vl-mapping__grid {
  display: grid;
  gap: var(--vl-space-4);
  grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
}
.vl-mapping__field,
.vl-mapping__sheet,
.vl-mapping__policy {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: var(--vl-space-2);
}
.vl-mapping__sheet,
.vl-mapping__policy {
  display: block;
  margin-bottom: var(--vl-space-4);
  max-width: 28rem;
}
.vl-mapping__label {
  grid-column: 1 / -1;
  display: block;
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
.vl-mapping__input {
  grid-column: 1 / -1;
  min-height: var(--vl-control-height);
  border: 1px solid var(--vl-color-border-control);
  border-radius: var(--vl-radius-control);
  padding: 0 var(--vl-space-3);
  width: 100%;
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
