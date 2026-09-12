<template>
  <div class="vl-page">
    <PageHeader :title="topic?.name ?? '主题详情'" :description="`revision ${revision} · 共 ${topic?.feedback_count ?? 0} 条证据`">
      <template #actions>
        <VlButton variant="ghost" @click="goBack">返回主题列表</VlButton>
        <VlButton v-if="canAct" variant="primary" data-testid="topic-correct" @click="correctionOpen = true">人工校正</VlButton>
      </template>
    </PageHeader>

    <div v-if="viewingOldRevision" class="vl-topic-detail__banner" data-testid="topic-old-revision">
      正在查看历史版本 revision {{ revision }};当前版本为 revision {{ currentRevision }}。
      <VlButton variant="ghost" size="small" @click="loadCurrent">查看当前版本</VlButton>
    </div>

    <AsyncState :status="status" :message="error ?? undefined" empty-message="主题不存在或已被删除。">
      <template #error>
        <p class="vl-topic-detail__error">暂时无法获取主题,请稍后重试。</p>
        <VlButton variant="secondary" @click="loadCurrent">重试</VlButton>
      </template>

      <div v-if="topic" class="vl-topic-detail">
        <VlPanel title="主题摘要">
          <p v-if="topic.summary_revalidated === false" class="vl-topic-detail__pending" data-testid="topic-pending-revalidation">
            该版本摘要尚未重新验证,请勿直接引用旧结论。
          </p>
          <p class="vl-topic-detail__summary">{{ topic.summary || '暂无摘要' }}</p>
          <dl class="vl-topic-detail__meta">
            <dt>严重度</dt>
            <dd><StatusBadge kind="severity" :state="topic.severity" /></dd>
            <dt>证据数</dt>
            <dd class="vl-number">{{ topic.feedback_count }}</dd>
          </dl>
        </VlPanel>

        <VlPanel title="证据与来源" description="每条证据可定位源行与脱敏片段;正文只读纯文本">
          <ul v-if="detail?.evidence.length" class="vl-topic-detail__evidence" data-testid="topic-evidence">
            <li v-for="item in detail.evidence" :key="item.feedback_id" class="vl-topic-detail__evidence-item">
              <p class="vl-evidence-text">{{ item.quote }}</p>
              <p class="vl-topic-detail__evidence-meta">
                <span class="vl-number">源行 {{ item.source_row }}</span>
                <span class="vl-number">片段 {{ item.quote_start }}-{{ item.quote_end }}</span>
                <span>{{ item.feedback_id }}</span>
              </p>
            </li>
          </ul>
          <p v-else class="vl-topic-detail__empty">该版本没有关联证据。</p>
        </VlPanel>
      </div>
    </AsyncState>

    <CorrectionDialog
      ref="correctionDialog"
      :open="correctionOpen"
      :topic-id="topicId"
      :topic-title="topic?.name ?? ''"
      :revision="revision"
      :sibling-topics="siblingTopics"
      @submit="onCorrect"
      @close="correctionOpen = false"
    />
  </div>
</template>

<script setup lang="ts">
// TopicDetailPage — 工程计划 W13:摘要 → 证据;原文失效/旧版本/证据不足分别呈现;
// 校正走 CorrectionDialog(不可变版本、乐观锁);历史版本可查且明确标注。
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '../../components/common/PageHeader.vue'
import VlPanel from '../../components/common/VlPanel.vue'
import VlButton from '../../components/common/VlButton.vue'
import StatusBadge from '../../components/common/StatusBadge.vue'
import AsyncState from '../../components/common/AsyncState.vue'
import CorrectionDialog from './CorrectionDialog.vue'
import { ApiHttpError, apiClient, type CorrectionBody } from '../../api/client'
import { useSessionStore } from '../../stores/session'
import { useTopicsData } from '../../composables/useTopicsData'
import type { TopicDetailResponse } from '../../api/client'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const client = apiClient()

const projectId = computed(() => String(route.params.p))
const topicId = computed(() => String(route.params.t))
const canAct = computed(() => (session.user?.role ?? 'VIEWER') !== 'VIEWER')

const status = ref<'idle' | 'loading' | 'success' | 'empty' | 'error'>('idle')
const error = ref('')
const detail = ref<TopicDetailResponse | null>(null)
const revision = ref(Number(route.query.revision ?? 0) || 0)
const currentRevision = ref(0)
const topic = computed(() => detail.value?.topic ?? null)
const correctionOpen = ref(false)

const { topics, reload: reloadTopics } = useTopicsData(projectId)
const siblingTopics = computed(() => topics.value.map(t => ({ id: t.id, title: t.title })))
const viewingOldRevision = computed(() => currentRevision.value > 0 && revision.value > 0 && revision.value !== currentRevision.value)

async function loadCurrent() {
  revision.value = 0
  await load()
}

async function load() {
  status.value = 'loading'
  try {
    detail.value = await client.getTopicDetail(projectId.value, topicId.value, revision.value || undefined)
    revision.value = detail.value.revision
    // 记录当前 revision 以便标注「正在查看历史版本」
    if (!currentRevision.value || !viewingOldRevision.value) {
      const latest = await client.getTopicDetail(projectId.value, topicId.value)
      currentRevision.value = latest.revision
    }
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
watch(topicId, () => { revision.value = 0; currentRevision.value = 0; void load() })

const correctionDialog = ref<InstanceType<typeof CorrectionDialog> | null>(null)

async function onCorrect(body: CorrectionBody) {
  try {
    await client.correctTopic(projectId.value, topicId.value, body)
    correctionDialog.value?.reportSuccess()
    correctionOpen.value = false
    revision.value = 0
    currentRevision.value = 0
    await load()
    reloadTopics()
  } catch (err) {
    // 409/422 等失败由对话框就地提示,保留用户已填内容
    correctionDialog.value?.reportFailure(err)
  }
}

function goBack() {
  void router.push(`/p/${projectId.value}/topics`)
}
</script>

<style scoped>
.vl-topic-detail {
  display: grid;
  gap: var(--vl-space-4);
}
.vl-topic-detail__banner {
  display: flex;
  align-items: center;
  gap: var(--vl-space-3);
  margin-bottom: var(--vl-space-4);
  padding: var(--vl-space-2) var(--vl-space-3);
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-warning-bg);
  color: var(--vl-color-warning);
  font-size: var(--vl-text-sm);
}
.vl-topic-detail__pending {
  margin: 0 0 var(--vl-space-3);
  padding: var(--vl-space-2) var(--vl-space-3);
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-warning-bg);
  color: var(--vl-color-warning);
  font-size: var(--vl-text-xs);
}
.vl-topic-detail__summary {
  margin: 0 0 var(--vl-space-4);
}
.vl-topic-detail__meta {
  display: grid;
  grid-template-columns: 6rem 1fr;
  gap: var(--vl-space-2) var(--vl-space-3);
  margin: 0;
  font-size: var(--vl-text-sm);
}
.vl-topic-detail__meta dt {
  color: var(--vl-color-text-muted);
}
.vl-topic-detail__meta dd {
  margin: 0;
}
.vl-topic-detail__evidence {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: var(--vl-space-4);
}
.vl-topic-detail__evidence-item {
  border-left: 3px solid var(--vl-color-brand-line);
  padding-inline-start: var(--vl-space-3);
}
.vl-topic-detail__evidence-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--vl-space-2) var(--vl-space-4);
  margin: var(--vl-space-2) 0 0;
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
.vl-topic-detail__empty {
  margin: 0;
  color: var(--vl-color-text-muted);
}
.vl-topic-detail__error {
  color: var(--vl-color-danger);
}
</style>
