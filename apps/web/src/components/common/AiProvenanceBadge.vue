<template>
  <div class="vl-ai-provenance" data-testid="ai-provenance">
    <span class="vl-ai-provenance__badge">{{ sourceLabel(provenance.origin) }}</span>
    <span v-if="provenance.needsReview" class="vl-ai-provenance__hint">AI 建议,需核对原文</span>
    <button type="button" class="vl-ai-provenance__toggle" :aria-expanded="expanded" @click="expanded = !expanded">
      {{ expanded ? '收起来源与限制' : '来源与限制' }}
    </button>
    <dl v-if="expanded" class="vl-ai-provenance__details">
      <template v-if="provenance.reviewRecord">
        <dt>人工确认</dt>
        <dd>{{ provenance.reviewRecord.reviewer }} · {{ provenance.reviewRecord.reviewedAt }}</dd>
      </template>
      <template v-else>
        <dt>人工确认</dt>
        <dd>无人工审核记录,不代表已确认</dd>
      </template>
      <dt>限制</dt>
      <dd>建议与候选均需对照原文核验,不作为业务结论。</dd>
    </dl>
  </div>
</template>

<script setup lang="ts">
// AiProvenanceBadge — 风格规范 6.5/9.5:「AI 建议/规则候选/人工修订/来源未提供」;
// needs_review=false 不是人工确认凭据,没有审核事件不显示「人工已确认」。
import { ref } from 'vue'
import { sourceLabel } from '../../lib/ui-status'
import type { AiProvenance } from '../../types/domain'

defineProps<{
  provenance: AiProvenance
}>()

const expanded = ref(false)
</script>

<style scoped>
.vl-ai-provenance {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--vl-space-2);
}
.vl-ai-provenance__badge {
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-subtle);
  color: var(--vl-color-text-secondary);
  padding: 2px var(--vl-space-2);
  font-size: var(--vl-text-xs);
}
.vl-ai-provenance__hint {
  font-size: var(--vl-text-xs);
  color: var(--vl-color-warning);
}
.vl-ai-provenance__toggle {
  border: none;
  background: none;
  padding: 0;
  font-size: var(--vl-text-xs);
  color: var(--vl-color-brand);
  cursor: pointer;
  min-height: var(--vl-control-height-compact);
}
.vl-ai-provenance__details {
  flex-basis: 100%;
  margin: var(--vl-space-2) 0 0;
  padding: var(--vl-space-3);
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-subtle);
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-secondary);
}
.vl-ai-provenance__details dt {
  font-weight: 600;
  margin-top: var(--vl-space-1);
}
.vl-ai-provenance__details dd {
  margin: 0;
}
</style>
