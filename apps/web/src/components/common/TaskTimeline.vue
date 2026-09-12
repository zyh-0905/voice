<template>
  <ol v-if="events.length" class="vl-timeline" data-testid="task-timeline">
    <li v-for="(event, index) in events" :key="index" class="vl-timeline__item">
      <span class="vl-timeline__dot" aria-hidden="true" />
      <div class="vl-timeline__body">
        <p class="vl-timeline__head">
          <span class="vl-timeline__action">{{ actionLabel(event.action) }}</span>
          <StatusBadge kind="task" :state="event.state" />
        </p>
        <p class="vl-timeline__meta">{{ event.actor || '系统' }}<template v-if="event.comment"> · {{ event.comment }}</template></p>
      </div>
    </li>
  </ol>
  <p v-else class="vl-timeline__empty">暂无流转记录</p>
</template>

<script setup lang="ts">
// TaskTimeline — 风格规范 9.4:不从当前状态伪造过去记录;执行验收不是效果证明。
import type { TaskEvent } from '../../types/domain'
import StatusBadge from './StatusBadge.vue'

defineProps<{
  events: TaskEvent[]
}>()

const ACTION_LABELS: Record<string, string> = {
  confirm: '确认派发',
  start: '开始执行',
  submit: '提交执行材料',
  approve: '通过执行验收',
  reject: '退回重做',
  cancel: '取消任务',
}

function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action
}
</script>

<style scoped>
.vl-timeline {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: var(--vl-space-3);
}
.vl-timeline__item {
  display: flex;
  gap: var(--vl-space-3);
}
.vl-timeline__dot {
  width: 0.5rem;
  height: 0.5rem;
  margin-top: 0.5rem;
  border-radius: 50%;
  background: var(--vl-color-brand);
  flex: none;
}
.vl-timeline__body {
  min-width: 0;
}
.vl-timeline__head {
  margin: 0;
  display: flex;
  align-items: center;
  gap: var(--vl-space-2);
}
.vl-timeline__action {
  font-size: var(--vl-text-sm);
  font-weight: 600;
}
.vl-timeline__meta {
  margin: var(--vl-space-1) 0 0;
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
.vl-timeline__empty {
  margin: 0;
  color: var(--vl-color-text-muted);
}
</style>
