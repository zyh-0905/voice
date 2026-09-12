<template>
  <div class="vl-page">
    <PageHeader :title="task?.title ?? '任务详情'" description="草稿派发、执行提交与独立验收是不同动作;负责人不得自验收。">
      <template #actions>
        <VlButton variant="ghost" @click="goBack">返回任务列表</VlButton>
      </template>
    </PageHeader>

    <AsyncState :status="status" :message="error ?? undefined" empty-message="任务不存在或已被删除。">
      <template #error>
        <p class="vl-task-detail__error">暂时无法获取任务,请稍后重试。</p>
        <VlButton variant="secondary" @click="load">重试</VlButton>
      </template>

      <div v-if="task" class="vl-task-detail">
        <VlPanel title="任务信息">
          <dl class="vl-task-detail__meta">
            <dt>状态</dt>
            <dd data-testid="task-state"><StatusBadge kind="task" :state="task.status" /></dd>
            <dt>负责人</dt>
            <dd data-testid="task-owner">{{ task.owner ?? task.owner_id ?? '未指定' }}</dd>
            <dt>截止时间</dt>
            <dd class="vl-number" data-testid="task-due">{{ displayDate(task.dueAt) }}</dd>
            <dt>优先级</dt>
            <dd><StatusBadge kind="severity" :state="task.priority ?? 'MEDIUM'" /></dd>
            <dt>来源</dt>
            <dd>{{ detail?.source_snapshot ?? task.source ?? '—' }}</dd>
            <dt>验收标准</dt>
            <dd data-testid="task-acceptance">{{ task.acceptance ?? '—' }}</dd>
            <dt>效果状态</dt>
            <dd>
              <span data-testid="task-effect">{{ effectLabel }}</span>
              <span v-if="task.effect_status === 'NOT_EVALUATED'" class="vl-task-detail__hint">(执行验收不等于经营效果被证实)</span>
            </dd>
          </dl>

          <template #actions>
            <VlButton
              v-if="primaryAction"
              :variant="primaryAction.variant"
              :disabled="!canAct"
              :data-testid="primaryAction.testid"
              @click="onPrimary"
            >
              {{ primaryAction.label }}
            </VlButton>
            <VlButton
              v-if="secondaryAction"
              variant="ghost"
              :disabled="!canAct"
              :data-testid="secondaryAction.testid"
              @click="onSecondary"
            >
              {{ secondaryAction.label }}
            </VlButton>
          </template>
        </VlPanel>

        <VlPanel title="流转记录" description="记录真实发生的动作,不从当前状态倒推">
          <TaskTimeline :events="detail?.events ?? []" />
        </VlPanel>
      </div>
    </AsyncState>

    <HumanReviewDialog
      :open="dialog.open"
      :title="dialog.title"
      :description="dialog.description"
      :fields="dialog.fields"
      :confirm-label="dialog.confirmLabel"
      :require-comment="dialog.requireComment"
      :comment-label="dialog.commentLabel"
      :comment-placeholder="dialog.commentPlaceholder"
      :conflict-message="dialog.conflictMessage"
      :pending="pending"
      @confirm="onDialogConfirm"
      @close="closeDialog"
    >
      <template v-if="dialog.spec?.kind === 'confirm'" #form>
        <div class="vl-field vl-confirm-form__field">
          <label for="vl-task-owner">负责人</label>
          <input id="vl-task-owner" v-model="owner" data-testid="task-owner-input" class="vl-confirm-form__input" placeholder="选择或输入负责人" />
          <span v-if="formError" class="vl-confirm-form__error" data-testid="owner-validation-error">{{ formError }}</span>
        </div>
        <div class="vl-field vl-confirm-form__field">
          <label for="vl-task-due">截止时间</label>
          <input id="vl-task-due" v-model="dueAt" type="date" data-testid="task-due-input" class="vl-confirm-form__input" />
        </div>
        <div class="vl-field vl-confirm-form__field">
          <label for="vl-task-acceptance">验收标准</label>
          <input id="vl-task-acceptance" v-model="acceptance" data-testid="task-acceptance-input" class="vl-confirm-form__input" placeholder="可验证的完成标准" />
        </div>
      </template>
    </HumanReviewDialog>
  </div>
</template>

<script setup lang="ts">
// TaskDetailPage — 工程计划 W16:草稿派发 / 提交执行 / 独立验收是不同主动作;
// 409 版本冲突保留本地输入(不静默覆盖);VIEWER 只读。
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '../../components/common/PageHeader.vue'
import VlPanel from '../../components/common/VlPanel.vue'
import VlButton from '../../components/common/VlButton.vue'
import StatusBadge from '../../components/common/StatusBadge.vue'
import AsyncState from '../../components/common/AsyncState.vue'
import TaskTimeline from '../../components/common/TaskTimeline.vue'
import HumanReviewDialog from '../../components/common/HumanReviewDialog.vue'
import { ApiHttpError, apiClient, type TaskTransitionBody } from '../../api/client'
import { useSessionStore } from '../../stores/session'
import { effectStatusLabel } from '../../lib/ui-status'
import type { TaskDetail } from '../../types/domain'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const client = apiClient()

const projectId = computed(() => String(route.params.p))
const taskId = computed(() => String(route.params.t))
const canAct = computed(() => (session.user?.role ?? 'VIEWER') !== 'VIEWER')

const status = ref<'idle' | 'loading' | 'success' | 'empty' | 'error'>('idle')
const error = ref('')
const detail = ref<TaskDetail | null>(null)
const task = computed(() => detail.value?.task ?? null)
const pending = ref(false)

const effectLabel = computed(() => {
  const value = task.value?.effect_status
  return value ? effectStatusLabel(value) : '尚未复盘'
})

async function load() {
  status.value = 'loading'
  try {
    detail.value = await client.getTask(projectId.value, taskId.value)
    status.value = 'success'
  } catch (err) {
    if (err instanceof ApiHttpError && err.status === 404) {
      status.value = 'empty'
      return
    }
    status.value = 'error'
    error.value = err instanceof Error ? err.message : String(err)
  }
}
onMounted(load)

function displayDate(value: string | null | undefined): string {
  return value ? value.slice(0, 10) : '—'
}

// —— 主动作:每种状态只有一个明确动作(文案即具体行为) ——
interface ActionSpec { label: string; testid: string; variant: 'primary' | 'danger' | 'secondary'; kind: 'confirm' | 'transition'; action?: TaskTransitionBody['action']; requireComment: boolean }

const primaryAction = computed<ActionSpec | null>(() => {
  const state = task.value?.status
  if (!canAct.value || !state) return null
  switch (state) {
    case 'DRAFT':
      return { label: '确认创建任务', testid: 'task-confirm', variant: 'primary', kind: 'confirm', requireComment: false }
    case 'OPEN':
      return { label: '开始执行', testid: 'task-start', variant: 'primary', kind: 'transition', action: 'start', requireComment: false }
    case 'IN_PROGRESS':
      return { label: '提交执行材料', testid: 'task-submit-review', variant: 'primary', kind: 'transition', action: 'submit', requireComment: true }
    case 'PENDING_REVIEW':
      return { label: '通过执行验收', testid: 'task-approve', variant: 'primary', kind: 'transition', action: 'approve', requireComment: true }
    default:
      return null
  }
})

const secondaryAction = computed<ActionSpec | null>(() => {
  const state = task.value?.status
  if (!canAct.value || state !== 'PENDING_REVIEW') return null
  return { label: '退回重做', testid: 'task-reject', variant: 'secondary', kind: 'transition', action: 'reject', requireComment: true }
})

const dialog = ref({
  open: false, title: '', description: '', confirmLabel: '确认', requireComment: false,
  commentLabel: '说明', commentPlaceholder: '说明本次操作的依据', conflictMessage: '',
  fields: [] as Array<{ label: string; value: string }>, spec: null as ActionSpec | null,
})

const owner = ref('')
const dueAt = ref('')
const acceptance = ref('')
const formError = ref('')

function onPrimary() {
  const spec = primaryAction.value
  if (spec) openDialog(spec)
}
function onSecondary() {
  const spec = secondaryAction.value
  if (spec) openDialog(spec)
}

function openDialog(spec: ActionSpec) {
  formError.value = ''
  owner.value = task.value?.owner ?? ''
  dueAt.value = task.value?.dueAt?.slice(0, 10) ?? ''
  acceptance.value = task.value?.acceptance ?? ''
  dialog.value = {
    open: true,
    title: spec.label,
    description: spec.kind === 'confirm'
      ? '确认后生成正式任务;负责人、期限与验收标准必须明确。'
      : '该动作会写入流转记录,请确认依据充分。',
    confirmLabel: spec.label,
    requireComment: spec.requireComment,
    commentLabel: spec.kind === 'confirm' ? '派发说明' : '操作说明',
    commentPlaceholder: spec.kind === 'confirm' ? '说明派发依据' : '说明本次操作的依据',
    conflictMessage: '',
    fields: spec.kind === 'confirm'
      ? [
          { label: '任务', value: task.value?.title ?? '' },
          { label: '来源', value: String(detail.value?.source_snapshot ?? task.value?.source ?? '—') },
        ]
      : [
          { label: '任务', value: task.value?.title ?? '' },
          { label: '负责人', value: String(task.value?.owner ?? '未指定') },
          { label: '验收标准', value: String(task.value?.acceptance ?? '—') },
        ],
    spec,
  }
}

function closeDialog() {
  dialog.value = { ...dialog.value, open: false }
}

async function onDialogConfirm(comment: string) {
  const spec = dialog.value.spec
  if (!spec) return
  if (spec.kind === 'confirm') {
    // 可修复的「负责人未选」保留对话框可点击以触发校验,不清空其他字段
    if (!owner.value.trim() || !dueAt.value.trim() || !acceptance.value.trim()) {
      formError.value = '请填写负责人、期限与验收标准'
      return
    }
  }
  pending.value = true
  try {
    const idempotencyKey = `${taskId.value}-${spec.testid}-${task.value?.status}-${Date.now()}`
    if (spec.kind === 'confirm') {
      await client.confirmTask(projectId.value, taskId.value, {
        expected_version: detail.value?.version ?? 1,
        owner_id: owner.value.trim(),
        due_at: dueAt.value.trim(),
        acceptance: acceptance.value.trim(),
      }, idempotencyKey)
    } else if (spec.action) {
      await client.transitionTask(projectId.value, taskId.value, {
        action: spec.action, expected_version: detail.value?.version ?? 1, comment, material_refs: [],
      }, idempotencyKey)
    }
    closeDialog()
    await load()
  } catch (err) {
    if (err instanceof ApiHttpError && err.status === 409) {
      // 版本冲突:保留本地输入,提示用户基于最新数据重新操作
      dialog.value = { ...dialog.value, conflictMessage: '任务已被其他人更新,请关闭后重新查看最新状态再操作(你填写的内容不会被清空)。' }
    } else if (err instanceof ApiHttpError && err.status === 422) {
      formError.value = '请补全必填字段后重试'
    } else {
      formError.value = '操作失败,请稍后重试'
    }
  } finally {
    pending.value = false
  }
}

function goBack() {
  void router.push(`/p/${projectId.value}/tasks`)
}
</script>

<style scoped>
.vl-task-detail {
  display: grid;
  gap: var(--vl-space-4);
}
.vl-task-detail__meta {
  display: grid;
  grid-template-columns: 6rem 1fr;
  gap: var(--vl-space-2) var(--vl-space-3);
  margin: 0;
  font-size: var(--vl-text-sm);
}
.vl-task-detail__meta dt {
  color: var(--vl-color-text-muted);
}
.vl-task-detail__meta dd {
  margin: 0;
}
.vl-task-detail__hint {
  margin-inline-start: var(--vl-space-2);
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
.vl-task-detail__error {
  color: var(--vl-color-danger);
}
.vl-confirm-form__field {
  display: block;
  margin-top: var(--vl-space-4);
}
.vl-confirm-form__field label {
  display: block;
  margin-bottom: var(--vl-space-1);
  font-size: var(--vl-text-sm);
}
.vl-confirm-form__input {
  width: 100%;
  min-height: var(--vl-control-height);
  border: 1px solid var(--vl-color-border-control);
  border-radius: var(--vl-radius-control);
  padding: 0 var(--vl-space-3);
  font: inherit;
}
.vl-confirm-form__error {
  display: block;
  margin-top: var(--vl-space-1);
  color: var(--vl-color-danger);
  font-size: var(--vl-text-xs);
}
</style>
