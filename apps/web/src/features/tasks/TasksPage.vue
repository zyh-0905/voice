<template>
  <div class="vl-page">
    <PageHeader title="整改任务" description="状态/负责人/逾期筛选;草稿→派发→执行→提交→验收分离,不可自验收。">
      <template #actions>
        <VlButton v-if="canAct" variant="primary" data-testid="create-task-draft" @click="createDraft">
          创建任务
        </VlButton>
      </template>
    </PageHeader>


    <AsyncState :status="status" :message="error ?? undefined" empty-message="当前筛选下没有任务。">
      <div class="vl-tasks__filters">
        <div class="vl-field">
          <label class="vl-tasks__label" for="vl-tasks-state">状态</label>
          <select id="vl-tasks-state" v-model="stateFilter" class="vl-tasks__select">
            <option value="">全部</option>
            <option value="unclosed">未关闭</option>
            <option value="DRAFT">草稿·待确认</option>
            <option value="OPEN">待开始</option>
            <option value="IN_PROGRESS">进行中</option>
            <option value="PENDING_REVIEW">待验收</option>
            <option value="CLOSED">执行已验收</option>
            <option value="CANCELLED">已取消</option>
          </select>
        </div>
        <div class="vl-field">
          <label class="vl-tasks__label" for="vl-tasks-overdue">逾期</label>
          <select id="vl-tasks-overdue" v-model="overdueFilter" class="vl-tasks__select">
            <option value="">全部</option>
            <option value="overdue">仅逾期</option>
          </select>
        </div>
      </div>

      <div class="vl-table-scroll">
        <table class="vl-task-table" data-testid="task-table">
          <thead>
            <tr>
              <th scope="col">任务</th>
              <th scope="col">负责人</th>
              <th scope="col">截止时间</th>
              <th scope="col">状态</th>
              <th scope="col">优先级</th>
              <th scope="col"><span class="vl-sr-only">操作</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="task in visible" :key="task.id" :data-resource-id="task.id">
              <th scope="row" class="vl-task-table__title">
                {{ task.title }}
                <span class="vl-task-table__source">{{ task.source ?? '' }}</span>
              </th>
              <td>{{ task.owner ?? '—' }}</td>
              <td class="vl-number">{{ displayDate(task.dueAt) }}</td>
              <td>
                <span v-if="task.overdue" class="vl-task-table__overdue">已逾期</span>
                <StatusBadge kind="task" :state="task.status" />
              </td>
              <td><StatusBadge kind="severity" :state="task.priority ?? 'MEDIUM'" /></td>
              <td class="vl-task-table__actions">
                <VlButton variant="ghost" size="small" data-testid="task-open" @click="openTask(task)">查看详情</VlButton>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </AsyncState>
  </div>
</template>

<script setup lang="ts">
// TasksPage — 工程计划 W16:高效任务表(非卡片),「未关闭」是筛选组合不是新状态;
// 首版不提供拖拽;草稿确认/提交/验收是不同主动作(演示以推进示意),不能自验收。
// 真实模式:列表来自 GET /tasks,推进/创建待服务端状态机端点,不做误导性乐观更新。
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '../../stores/session'
import { apiClient } from '../../api/client'
import PageHeader from '../../components/common/PageHeader.vue'
import VlButton from '../../components/common/VlButton.vue'
import StatusBadge from '../../components/common/StatusBadge.vue'
import AsyncState from '../../components/common/AsyncState.vue'
import type { TaskStatus, TaskSummary } from '../../types/domain'

const session = useSessionStore()
const canAct = computed(() => (session.user?.role ?? 'VIEWER') !== 'VIEWER')
const client = apiClient()

const route = useRoute()
const router = useRouter()
const projectId = computed(() => String(route.params.p))

const items = ref<TaskSummary[]>([])
const status = ref<'idle' | 'loading' | 'success' | 'empty' | 'error'>('idle')
const error = ref('')
const stateFilter = ref('')
const overdueFilter = ref('')

async function loadTasks() {
  status.value = 'loading'
  try {
    items.value = await client.taskSummaries(projectId.value)
    status.value = items.value.length ? 'success' : 'empty'
  } catch (err) {
    status.value = 'error'
    error.value = err instanceof Error ? err.message : String(err)
  }
}
onMounted(loadTasks)

const visible = computed(() => {
  let list = items.value
  if (stateFilter.value === 'unclosed') {
    list = list.filter(t => ['OPEN', 'IN_PROGRESS', 'PENDING_REVIEW'].includes(t.status))
  } else if (stateFilter.value) {
    list = list.filter(t => t.status === stateFilter.value)
  }
  if (overdueFilter.value === 'overdue') list = list.filter(t => t.overdue)
  return list
})

function displayDate(value: string | null): string {
  return value ? value.slice(0, 10) : '—'
}

function openTask(task: TaskSummary) {
  // 状态流转在详情页经服务端状态机执行,列表只做导航
  void router.push(`/p/${projectId.value}/tasks/${task.id}`)
}

async function createDraft() {
  // 写路径走同一数据源并重新读取:避免本地 push 被稍后返回的列表响应覆盖
  try {
    await client.createTaskDraft(projectId.value, { title: '新建整改草稿' })
    await loadTasks()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  }
}
</script>

<style scoped>
.vl-tasks__filters {
  display: flex;
  gap: var(--vl-space-4);
  margin-bottom: var(--vl-space-4);
}
.vl-tasks__label {
  display: block;
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
  margin-bottom: var(--vl-space-1);
}
.vl-tasks__select {
  min-height: var(--vl-control-height);
  border: 1px solid var(--vl-color-border-control);
  border-radius: var(--vl-radius-control);
  padding: 0 var(--vl-space-3);
}
.vl-task-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}
.vl-task-table thead th {
  padding: var(--vl-space-3);
  background: var(--vl-color-subtle);
  font-size: var(--vl-text-sm);
  font-weight: 600;
}
.vl-task-table tbody th,
.vl-task-table tbody td {
  padding: var(--vl-space-3);
  border-bottom: 1px solid var(--vl-color-border);
  vertical-align: top;
}
.vl-task-table__title {
  font-weight: 600;
}
.vl-task-table__source {
  display: block;
  font-size: var(--vl-text-xs);
  font-weight: 400;
  color: var(--vl-color-text-muted);
}
.vl-task-table__overdue {
  margin-inline-end: var(--vl-space-2);
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-danger-bg);
  color: var(--vl-color-danger);
  padding: 2px var(--vl-space-2);
  font-size: var(--vl-text-xs);
}
.vl-sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
