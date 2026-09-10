<template>
  <div class="vl-page">
    <PageHeader
      title="主题洞察"
      :description="`在 run/revision 内核对主题证据、CPI 与复核状态。主题数 ${total} 个。`"
    >
      <template #actions>
        <VlButton variant="ghost" data-testid="view-unclassified" @click="filterUnclassified = !filterUnclassified">
          {{ filterUnclassified ? '查看全部主题' : '查看待归类' }}
        </VlButton>
      </template>
    </PageHeader>

    <AsyncState
      :status="status"
      :message="error ?? undefined"
      :refreshing="refreshing"
      empty-message="暂无已归类主题,仍可查看风险候选与待归类反馈"
    >
      <template #error>
        <p class="vl-topics-error">暂时无法获取主题,请稍后重试。</p>
        <VlButton variant="secondary" @click="reload()">重试</VlButton>
      </template>
      <template #forbidden>
        <p class="vl-topics-error">当前角色无权查看此项目主题。</p>
      </template>

      <div class="vl-table-scroll">
        <table class="vl-topic-table" data-testid="topic-table">
          <thead>
            <tr>
              <th scope="col">主题</th>
              <th scope="col" class="vl-topic-table__num">反馈 n/N</th>
              <th scope="col" class="vl-topic-table__num">占比</th>
              <th scope="col">趋势</th>
              <th scope="col" class="vl-topic-table__num">CPI</th>
              <th scope="col">复核状态</th>
              <th scope="col"><span class="vl-sr-only">操作</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="topic in visible" :key="topic.id" :data-resource-id="topic.id">
              <th scope="row" class="vl-topic-table__title">{{ topic.title }}</th>
              <td class="vl-topic-table__num vl-number">{{ topic.feedbackCount }} / {{ formatCount(topic.denominator) }}</td>
              <td class="vl-topic-table__num vl-number">{{ topic.ratio.toFixed(1) }}%</td>
              <td><span class="vl-topic-table__trend vl-number">{{ trendLabel(topic.trend) }}</span></td>
              <td class="vl-topic-table__num vl-number">{{ topic.cpiDisplayValue ?? '—' }}</td>
              <td><StatusBadge kind="review" :state="topic.reviewState" /></td>
              <td>
                <VlButton variant="ghost" size="small" @click="openEvidence(topic)">查看证据</VlButton>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </AsyncState>

    <div v-if="selected" class="vl-topics__evidence">
      <EvidencePanel :evidence="selected" :run-label="runLabel" @close="closeEvidence" />
    </div>
  </div>
</template>

<script setup lang="ts">
// TopicsPage — 工程计划 W12:高效主题表(非卡片墙),服务端排序/分页契约先行;
// 待归类筛选独立;证据侧栏复用 Overview 的证据联动。
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '../components/common/PageHeader.vue'
import VlButton from '../components/common/VlButton.vue'
import AsyncState from '../components/common/AsyncState.vue'
import StatusBadge from '../components/common/StatusBadge.vue'
import EvidencePanel from '../components/common/EvidencePanel.vue'
import { useTopicsData } from '../composables/useTopicsData'
import type { EvidenceContext, TopicRow, TopicTrend } from '../types/domain'

const route = useRoute()
const projectId = computed(() => String(route.params.p))
const { topics, total, status, refreshing, error, reload } = useTopicsData(projectId)
const filterUnclassified = ref(false)

const visible = computed(() => (filterUnclassified.value ? topics.value.filter(t => t.id === 'unclassified') : topics.value))
const selected = ref<EvidenceContext | null>(null)
const runLabel = computed(() => selected.value ? `${selected.value.runId} · revision ${selected.value.revision}` : '')

function openEvidence(topic: TopicRow) {
  selected.value = topic.evidence
}
function closeEvidence() {
  selected.value = null
}

function formatCount(value: number): string {
  return new Intl.NumberFormat('zh-CN').format(value)
}
function trendLabel(trend: TopicTrend): string {
  switch (trend) {
    case 'up': return '上升'
    case 'down': return '下降'
    case 'flat': return '平稳'
    case 'new': return '新增'
    default: return '—'
  }
}
</script>

<style scoped>
.vl-topic-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
}
.vl-topic-table thead th {
  padding: var(--vl-space-3);
  background: var(--vl-color-subtle);
  font-size: var(--vl-text-sm);
  font-weight: 600;
}
.vl-topic-table tbody th,
.vl-topic-table tbody td {
  padding: var(--vl-space-3);
  border-bottom: 1px solid var(--vl-color-border);
  vertical-align: top;
}
.vl-topic-table__title {
  font-weight: 600;
  white-space: nowrap;
}
.vl-topic-table__num {
  text-align: right;
  white-space: nowrap;
}
.vl-topic-table__trend {
  color: var(--vl-color-text-secondary);
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
.vl-topics__evidence {
  margin-top: var(--vl-space-4);
}
.vl-topics-error {
  color: var(--vl-color-danger);
}
</style>
