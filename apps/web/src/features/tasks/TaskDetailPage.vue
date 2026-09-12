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

      <section v-if="editing" class="vl-panel vl-task-detail__edit" data-testid="task-edit-form">
        <h2 class="vl-task-detail__edit-title">编辑草稿</h2>
        <p class="vl-task-detail__hint">草稿阶段可改标题、来源与优先级;派发后改为可调期限与验收标准。</p>
        <div class="vl-field vl-confirm-form__field">
          <label for="vl-task-edit-title">标题</label>
          <input id="vl-task-edit-title" v-model="editForm.title" class="vl-confirm-form__input" data-testid="task-edit-title" />
        </div>
        <div class="vl-field vl-confirm-form__field">
          <label for="vl-task-edit-source">来源</label>
          <input id="vl-task-edit-source" v-model="editForm.source" class="vl-confirm-form__input" data-testid="task-edit-source" />
        </div>
        <div class="vl-field vl-confirm-form__field">
          <label for="vl-task-edit-priority">优先级</label>
          <select id="vl-task-edit-priority" v-model="editForm.priority" class="vl-confirm-form__input" data-testid="task-edit-priority">
            <option value="LOW">低</option>
            <option value="MEDIUM">中</option>
            <option value="HIGH">高</option>
            <option value="CRITICAL">严重</option>
          </select>
        </div>
        <p v-if="editError" class="vl-task-detail__error" data-testid="task-edit-error" role="alert">{{ editError }}</p>
        <div class="vl-confirm-form__actions">
          <VlButton variant="secondary" @click="editing = false">取消</VlButton>
          <VlButton variant="primary" :loading="saving" data-testid="task-edit-save" @click="saveEdit">保存修改</VlButton>
        </div>
      </section>

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
              v-if="task?.status === 'DRAFT' && canAct"
              variant="secondary"
              data-testid="task-edit"
              @click="startEdit"
            >
              编辑草稿
            </VlButton>
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
          <!-- W16:负责人只能从项目成员接口选择,不提供自由文本兜底 -->
          <select
            id="vl-task-owner"
            v-model="owner"
            data-testid="task-owner-input"
            class="vl-confirm-form__input"
            :disabled="membersStatus !== 'success'"
          >
            <option value="">{{ membersStatus === 'loading' ? '正在加载成员…' : '请选择负责人' }}</option>
            <option v-for="member in members" :key="member.id" :value="member.id">{{ member.display_name }}</option>
          </select>
          <span v-if="formError" class="vl-confirm-form__error" data-testid="owner-validation-error">{{ formError }}</span>
          <span v-if="membersStatus === 'error'" class="vl-confirm-form__error" data-testid="task-owner-error" role="alert">{{ membersError }}</span>
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
import { ApiHttpError, apiClient, type ProjectMember, type TaskTransitionBody } from '../../api/client'
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

// W16:负责人候选项只来自成员接口;成功后复用,加载失败在对话框内明示(不回退自由文本)
const members = ref<ProjectMember[]>([])
const membersStatus = ref<'idle' | 'loading' | 'success' | 'error'>('idle')
const membersError = ref('')

async function loadMembers() {
  if (membersStatus.value === 'loading' || membersStatus.value === 'success') return
  membersStatus.value = 'loading'
  membersError.value = ''
  try {
    members.value = await client.listMembers(projectId.value)
    membersStatus.value = 'success'
  } catch (err) {
    membersStatus.value = 'error'
    membersError.value = err instanceof Error ? err.message : '无法获取项目成员,请重试'
  }
}

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
  owner.value = task.value?.owner_id ?? ''
  dueAt.value = task.value?.dueAt?.slice(0, 10) ?? ''
  acceptance.value = task.value?.acceptance ?? ''
  // 派发对话框需要成员列表;其余动作不含负责人字段
  if (spec.kind === 'confirm') void loadMembers()
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
    // 成员列表不可用时不允许派发:不回退到自由文本,也不静默通过
    if (membersStatus.value === 'error') {
      formError.value = `成员列表加载失败:${membersError.value}`
      return
    }
    if (membersStatus.value !== 'success') {
      formError.value = '成员列表加载中,请稍候再试'
      return
    }
    // 可修复的「负责人未选」保留对话框可点击以触发校验,不清空其他字段
    if (!owner.value.trim() || !dueAt.value.trim() || !acceptance.value.trim()) {
      formError.value = '请选择负责人并填写期限与验收标准'
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

// 草稿编辑:409 保留本地输入,由用户决定是否重新加载
const editing = ref(false)
const saving = ref(false)
const editError = ref('')
const editForm = ref({ title: '', source: '', priority: 'MEDIUM' })

function startEdit() {
  if (!task.value) return
  editForm.value = {
    title: task.value.title,
    source: String(task.value.source ?? ''),
    priority: task.value.priority ?? 'MEDIUM',
  }
  editError.value = ''
  editing.value = true
}

async function saveEdit() {
  if (!detail.value) return
  saving.value = true
  editError.value = ''
  try {
    await client.patchTask(projectId.value, taskId.value, {
      expected_version: detail.value.version,
      title: editForm.value.title.trim(),
      source: editForm.value.source.trim(),
      priority: editForm.value.priority,
    })
    editing.value = false
    await load()
  } catch (err) {
    if (err instanceof ApiHttpError && err.status === 409) {
      editError.value = '任务已被他人更新,请重新加载后再保存(你填写的内容不会被清空)'
    } else if (err instanceof ApiHttpError && err.status === 422) {
      editError.value = '当前状态不允许修改这些字段'
    } else {
      editError.value = err instanceof Error ? err.message : '保存失败'
    }
  } finally {
    saving.value = false
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
.vl-task-detail__edit-title {
  margin: 0 0 var(--vl-space-2);
  font-size: var(--vl-text-md);
}
.vl-task-detail__edit {
  margin-bottom: var(--vl-space-4);
}
.vl-confirm-form__actions {
  display: flex;
  gap: var(--vl-space-3);
  margin-top: var(--vl-space-4);
}
.vl-confirm-form__error {
  display: block;
  margin-top: var(--vl-space-1);
  color: var(--vl-color-danger);
  font-size: var(--vl-text-xs);
}
</style>
