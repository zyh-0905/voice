<template>
  <el-dialog
    :model-value="open"
    title="人工校正"
    width="560px"
    :close-on-click-modal="false"
    append-to-body
    @update:model-value="(value: boolean) => { if (!value) emit('close') }"
  >
    <p class="vl-correction__hint">
      校正会创建新版本 revision,v1 及之前的版本保留可查;并发校正只有一个成功。
    </p>

    <div class="vl-field vl-correction__field">
      <label for="vl-correction-op">校正操作</label>
      <select id="vl-correction-op" v-model="operation" class="vl-correction__input" data-testid="correction-operation">
        <option value="RENAME">重命名主题</option>
        <option value="MERGE">合并主题</option>
        <option value="SPLIT">拆分主题</option>
        <option value="CREATE">从待归类创建</option>
      </select>
    </div>

    <div v-if="operation === 'RENAME' || operation === 'SPLIT' || operation === 'CREATE'" class="vl-field vl-correction__field">
      <label for="vl-correction-name">主题名称</label>
      <input id="vl-correction-name" v-model="name" class="vl-correction__input" data-testid="correction-name" placeholder="输入校正后的主题名称" />
    </div>

    <div v-if="operation === 'MERGE'" class="vl-field vl-correction__field">
      <label for="vl-correction-sources">合并来源(按住 Shift 多选,至少两个)</label>
      <select id="vl-correction-sources" v-model="sourceIds" multiple class="vl-correction__input" data-testid="correction-sources" size="3">
        <option v-for="topic in siblingTopics" :key="topic.id" :value="topic.id">{{ topic.title }}</option>
      </select>
    </div>

    <div v-if="operation === 'SPLIT' || operation === 'CREATE'" class="vl-field vl-correction__field">
      <label for="vl-correction-feedback">反馈 ID(逗号分隔)</label>
      <input id="vl-correction-feedback" v-model="feedbackIds" class="vl-correction__input" data-testid="correction-feedback" placeholder="fp_1, fp_2" />
    </div>

    <div class="vl-field vl-correction__field">
      <label for="vl-correction-reason">校正理由(必填)</label>
      <textarea id="vl-correction-reason" v-model="reason" rows="3" class="vl-correction__input" data-testid="correction-reason" placeholder="说明人工核对后的判断依据" />
      <span v-if="error" class="vl-correction__error" data-testid="correction-error" role="alert">{{ error }}</span>
    </div>

    <p v-if="conflict" class="vl-correction__conflict" data-testid="correction-conflict" role="alert">
      主题已被其他人校正到新版本,请关闭后重新加载再操作(你填写的内容不会被清空)。
    </p>

    <template #footer>
      <div class="vl-correction__actions">
        <VlButton variant="secondary" @click="emit('close')">取消</VlButton>
        <VlButton variant="primary" :loading="pending" data-testid="correction-submit" @click="submit">提交校正</VlButton>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
// CorrectionDialog — 工程计划 W13:校正走明确表单(RENAME/MERGE/SPLIT/CREATE),
// 理由必填;409 保留本地输入提示重新加载;不做无记录自动合并。
import { computed, ref, watch } from 'vue'
import VlButton from '../../components/common/VlButton.vue'
import { ApiHttpError, type CorrectionBody, type CorrectionOperation } from '../../api/client'

const props = defineProps<{
  open: boolean
  topicId: string
  topicTitle: string
  revision: number
  siblingTopics: Array<{ id: string; title: string }>
}>()

const emit = defineEmits<{
  submit: [body: CorrectionBody]
  close: []
}>()

const operation = ref<CorrectionOperation>('RENAME')
const name = ref('')
const reason = ref('')
const feedbackIds = ref('')
const sourceIds = ref<string[]>([])
const error = ref('')
const conflict = ref(false)
const pending = ref(false)

watch(() => props.open, (open) => {
  if (open) {
    operation.value = 'RENAME'
    name.value = props.topicTitle
    reason.value = ''
    feedbackIds.value = ''
    sourceIds.value = []
    error.value = ''
    conflict.value = false
    pending.value = false
  }
})

const parsedFeedbackIds = computed(() => feedbackIds.value.split(',').map(s => s.trim()).filter(Boolean))

function validate(): string {
  if (!reason.value.trim()) return '校正理由为必填项'
  if (operation.value === 'MERGE' && new Set(sourceIds.value).size < 2) return '合并至少需要选择两个来源主题'
  if ((operation.value === 'RENAME' || operation.value === 'SPLIT' || operation.value === 'CREATE') && !name.value.trim()) return '主题名称为必填项'
  if (operation.value === 'SPLIT' && !parsedFeedbackIds.value.length) return '拆分需要指定反馈 ID'
  if (operation.value === 'CREATE' && !parsedFeedbackIds.value.length) return '创建主题需要指定待归类反馈 ID'
  return ''
}

function submit() {
  const message = validate()
  if (message) {
    error.value = message
    return
  }
  error.value = ''
  pending.value = true
  const body: CorrectionBody = {
    operation: operation.value,
    expected_revision: props.revision,
    reason: reason.value.trim(),
    name: name.value.trim() || null,
    source_topic_ids: operation.value === 'MERGE' ? [...sourceIds.value] : undefined,
    feedback_ids: operation.value === 'SPLIT' || operation.value === 'CREATE' ? parsedFeedbackIds.value : undefined,
  }
  emit('submit', body)
}

/** 由父组件在 409/其他失败时回写状态,保留用户已填内容 */
function reportFailure(err: unknown) {
  pending.value = false
  if (err instanceof ApiHttpError && err.status === 409) {
    conflict.value = true
    return
  }
  if (err instanceof ApiHttpError && err.status === 422) {
    error.value = '服务端拒绝了此次校正,请检查参数'
    return
  }
  error.value = err instanceof Error ? err.message : '校正失败,请稍后重试'
}
function reportSuccess() {
  pending.value = false
}

defineExpose({ reportFailure, reportSuccess })
</script>

<style scoped>
.vl-correction__hint {
  margin: 0 0 var(--vl-space-4);
  color: var(--vl-color-text-muted);
  font-size: var(--vl-text-sm);
}
.vl-correction__field {
  display: block;
  margin-bottom: var(--vl-space-4);
}
.vl-correction__field label {
  display: block;
  margin-bottom: var(--vl-space-1);
  font-size: var(--vl-text-sm);
}
.vl-correction__input {
  width: 100%;
  min-height: var(--vl-control-height);
  border: 1px solid var(--vl-color-border-control);
  border-radius: var(--vl-radius-control);
  padding: 0 var(--vl-space-3);
  font: inherit;
}
textarea.vl-correction__input {
  padding: var(--vl-space-2) var(--vl-space-3);
}
.vl-correction__error {
  display: block;
  margin-top: var(--vl-space-1);
  color: var(--vl-color-danger);
  font-size: var(--vl-text-xs);
}
.vl-correction__conflict {
  margin: 0;
  padding: var(--vl-space-2) var(--vl-space-3);
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-warning-bg);
  color: var(--vl-color-warning);
  font-size: var(--vl-text-xs);
}
.vl-correction__actions {
  display: flex;
  gap: var(--vl-space-3);
  justify-content: flex-end;
}
</style>
