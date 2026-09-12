<template>
  <div class="vl-evidence-content">
    <p class="vl-evidence-content__context">{{ runLabel }}</p>
    <AiProvenanceBadge :provenance="evidence.aiProvenance" />
    <section class="vl-evidence-content__section">
      <h3 class="vl-evidence-content__heading">摘要</h3>
      <p class="vl-evidence-content__summary">{{ evidence.summary }}</p>
    </section>
    <section class="vl-evidence-content__section">
      <h3 class="vl-evidence-content__heading">CPI 分项</h3>
      <CpiBreakdown :cpi="evidence.cpi" />
    </section>
    <section class="vl-evidence-content__section">
      <h3 class="vl-evidence-content__heading">原文与来源</h3>
      <div v-for="quote in evidence.quotes" :key="quote.feedbackId" class="vl-evidence-content__quote">
        <EvidenceQuote :quote="quote" />
        <VlButton variant="ghost" size="small" data-testid="evidence-open-source" @click="openSource(quote.feedbackId)">
          查看源反馈
        </VlButton>
      </div>
      <p v-if="sourceError" class="vl-evidence-content__error" data-testid="evidence-source-error" role="alert">{{ sourceError }}</p>
    </section>
    <section v-if="source" class="vl-evidence-content__section" data-testid="evidence-source">
      <h3 class="vl-evidence-content__heading">源反馈</h3>
      <p class="vl-evidence-text">{{ source.text }}</p>
      <p class="vl-evidence-content__source-meta">
        <span class="vl-number">源行 {{ source.source_row }}</span>
        <span v-if="source.channel">渠道:{{ source.channel }}</span>
        <span v-if="source.occurred_at">时间:{{ source.occurred_at.slice(0, 16).replace('T', ' ') }}</span>
        <span>{{ source.dataset_name }}</span>
        <span>分块 {{ source.segments.length }} 段</span>
      </p>
    </section>

    <div v-if="$slots.actions" class="vl-evidence-content__actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
// EvidenceContent — 证据内容(风格规范 6.4 顺序):主题和版本 → AI/人工来源 → 摘要 →
// CPI 分项 → 原文/源行号/渠道/可信时间 → 操作。EvidencePanel 与 EvidenceDrawer 共用,
// 不重复挂载两份可交互内容。
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { apiClient, type FeedbackSource } from '../../api/client'
import VlButton from './VlButton.vue'
import type { EvidenceContext } from '../../types/domain'
import AiProvenanceBadge from './AiProvenanceBadge.vue'
import CpiBreakdown from './CpiBreakdown.vue'
import EvidenceQuote from './EvidenceQuote.vue'

defineProps<{
  evidence: EvidenceContext
  /** 如「run_demo_001 · revision 1」 */
  runLabel: string
}>()

// 证据源查询:只取脱敏全文与分块,不请求原始文件
const route = useRoute()
const source = ref<FeedbackSource | null>(null)
const sourceError = ref('')

async function openSource(feedbackId: string) {
  sourceError.value = ''
  try {
    source.value = await apiClient().getFeedback(String(route.params.p), feedbackId)
  } catch {
    sourceError.value = '来源已不可用;不能据此确认新任务'
    source.value = null
  }
}
</script>

<style scoped>
.vl-evidence-content__context {
  margin: 0 0 var(--vl-space-3);
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
  font-family: var(--vl-font-mono);
}
.vl-evidence-content__section {
  margin-top: var(--vl-space-4);
}
.vl-evidence-content__heading {
  margin: 0 0 var(--vl-space-2);
  font-size: var(--vl-text-sm);
  font-weight: 600;
}
.vl-evidence-content__summary {
  margin: 0;
  font-size: var(--vl-text-sm);
}
.vl-evidence-content__quote {
  margin-bottom: var(--vl-space-2);
}
.vl-evidence-content__source-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--vl-space-2) var(--vl-space-4);
  margin: var(--vl-space-2) 0 0;
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
.vl-evidence-content__error {
  margin: var(--vl-space-2) 0 0;
  color: var(--vl-color-warning);
  font-size: var(--vl-text-xs);
}
.vl-evidence-content__actions {
  margin-top: var(--vl-space-5);
  display: flex;
  gap: var(--vl-space-2);
}
</style>
