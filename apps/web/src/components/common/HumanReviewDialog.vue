<template>
  <el-dialog
    :model-value="open"
    :title="title"
    width="520px"
    :close-on-click-modal="false"
    append-to-body
    @update:model-value="(value: boolean) => { if (!value) emit('close') }"
  >
    <p v-if="description" class="vl-review-dialog__desc">{{ description }}</p>
    <dl v-if="fields.length" class="vl-review-dialog__fields">
      <template v-for="field in fields" :key="field.label">
        <dt>{{ field.label }}</dt>
        <dd>{{ field.value }}</dd>
      </template>
    </dl>

    <!-- 调用方注入必填表单(如草稿派发的负责人/期限/验收标准) -->
    <slot name="form" />

    <div v-if="showComment" class="vl-field vl-review-dialog__comment">
      <label :for="commentId">{{ commentLabel }}</label>
      <textarea
        :id="commentId"
        v-model="comment"
        rows="3"
        class="vl-review-dialog__input"
        data-testid="review-dialog-comment"
        :placeholder="commentPlaceholder"
        @input="error = ''"
      />
      <span v-if="error" class="vl-review-dialog__error" data-testid="review-dialog-error" role="alert">{{ error }}</span>
    </div>

    <p v-if="conflictMessage" class="vl-review-dialog__conflict" data-testid="review-dialog-conflict" role="alert">
      {{ conflictMessage }}
    </p>

    <template #footer>
      <div class="vl-review-dialog__actions">
        <VlButton variant="secondary" @click="emit('close')">取消</VlButton>
        <VlButton
          :variant="confirmVariant"
          :loading="pending"
          data-testid="review-dialog-confirm"
          @click="submit"
        >
          {{ confirmLabel }}
        </VlButton>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
// HumanReviewDialog — 风格规范 6.5/9.4:主按钮写具体动作(「确认创建任务」「确认风险」
// 「通过执行验收」等);必填校验、冲突时保留本地输入(不静默清空)。
import { computed, ref, watch } from 'vue'
import VlButton from './VlButton.vue'

const props = withDefaults(
  defineProps<{
    open: boolean
    title: string
    description?: string
    fields?: Array<{ label: string; value: string }>
    confirmLabel: string
    confirmVariant?: 'primary' | 'danger'
    requireComment?: boolean
    commentLabel?: string
    commentPlaceholder?: string
    /** 409/版本冲突提示:保留用户已填内容,由用户决定是否重试 */
    conflictMessage?: string
    pending?: boolean
  }>(),
  {
    fields: () => [],
    confirmVariant: 'primary',
    requireComment: false,
    commentLabel: '说明',
    commentPlaceholder: '说明本次操作的依据',
    pending: false,
  },
)

const emit = defineEmits<{
  confirm: [comment: string]
  close: []
}>()

const comment = ref('')
const error = ref('')
const commentId = `vl-review-comment-${Math.random().toString(36).slice(2, 8)}`
const showComment = computed(() => props.requireComment || Boolean(props.commentPlaceholder))

watch(() => props.open, (open) => {
  if (open) {
    comment.value = ''
    error.value = ''
  }
})

function submit() {
  if (props.requireComment && !comment.value.trim()) {
    error.value = `${props.commentLabel}为必填项`
    return
  }
  emit('confirm', comment.value.trim())
}
</script>

<style scoped>
.vl-review-dialog__desc {
  margin: 0 0 var(--vl-space-4);
  color: var(--vl-color-text-secondary);
}
.vl-review-dialog__fields {
  margin: 0 0 var(--vl-space-4);
  display: grid;
  grid-template-columns: 6rem 1fr;
  gap: var(--vl-space-2) var(--vl-space-3);
  font-size: var(--vl-text-sm);
}
.vl-review-dialog__fields dt {
  color: var(--vl-color-text-muted);
}
.vl-review-dialog__fields dd {
  margin: 0;
}
.vl-review-dialog__comment label {
  display: block;
  margin-bottom: var(--vl-space-2);
}
.vl-review-dialog__input {
  width: 100%;
  border: 1px solid var(--vl-color-border-control);
  border-radius: var(--vl-radius-control);
  padding: var(--vl-space-2) var(--vl-space-3);
  font: inherit;
}
.vl-review-dialog__error {
  display: block;
  margin-top: var(--vl-space-1);
  color: var(--vl-color-danger);
  font-size: var(--vl-text-xs);
}
.vl-review-dialog__conflict {
  margin: var(--vl-space-3) 0 0;
  padding: var(--vl-space-2) var(--vl-space-3);
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-warning-bg);
  color: var(--vl-color-warning);
  font-size: var(--vl-text-xs);
}
.vl-review-dialog__actions {
  display: flex;
  gap: var(--vl-space-3);
  justify-content: flex-end;
}
</style>
