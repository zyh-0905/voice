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
      <EvidenceQuote v-for="quote in evidence.quotes" :key="quote.feedbackId" :quote="quote" />
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
import type { EvidenceContext } from '../../types/domain'
import AiProvenanceBadge from './AiProvenanceBadge.vue'
import CpiBreakdown from './CpiBreakdown.vue'
import EvidenceQuote from './EvidenceQuote.vue'

defineProps<{
  evidence: EvidenceContext
  /** 如「run_demo_001 · revision 1」 */
  runLabel: string
}>()
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
.vl-evidence-content__actions {
  margin-top: var(--vl-space-5);
  display: flex;
  gap: var(--vl-space-2);
}
</style>
