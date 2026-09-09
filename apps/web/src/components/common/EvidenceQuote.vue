<template>
  <figure class="vl-quote" data-testid="evidence-quote">
    <blockquote class="vl-evidence-text">
      <span>{{ parts.before }}</span><mark class="vl-quote__mark">{{ parts.highlighted }}</mark><span>{{ parts.after }}</span>
    </blockquote>
    <figcaption class="vl-quote__meta">
      <span v-if="quote.rowIndex !== null">源行号 {{ quote.rowIndex }}</span>
      <span v-if="quote.channel">渠道:{{ quote.channel }}</span>
      <span v-if="quote.occurredAt">时间:{{ quote.occurredAt }}</span>
      <span class="vl-quote__id">反馈 {{ quote.feedbackId }}</span>
    </figcaption>
  </figure>
</template>

<script setup lang="ts">
// EvidenceQuote — 风格规范 6.4/9.4:纯文本渲染,禁止 v-html;
// offset 按 Unicode 字符处理(Array.from),不把 UTF-16 code unit 索引当作服务端字符索引;
// 拼回的完整文本必须与原文一致(见 tests/unit/evidence-quote.spec.ts)。
import { computed } from 'vue'
import type { EvidenceQuoteItem } from '../../types/domain'

const props = defineProps<{
  quote: EvidenceQuoteItem
}>()

const parts = computed(() => {
  const chars = Array.from(props.quote.text)
  const start = Math.max(0, Math.min(chars.length, props.quote.start))
  const end = Math.max(start, Math.min(chars.length, props.quote.end))
  return {
    before: chars.slice(0, start).join(''),
    highlighted: chars.slice(start, end).join(''),
    after: chars.slice(end).join(''),
  }
})
</script>

<style scoped>
.vl-quote {
  margin: 0 0 var(--vl-space-4);
  border-left: 3px solid var(--vl-color-brand-line);
  padding-inline-start: var(--vl-space-3);
}
.vl-quote blockquote {
  margin: 0;
}
.vl-quote__mark {
  background: var(--vl-color-brand-soft);
  color: var(--vl-color-text);
}
.vl-quote__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--vl-space-2) var(--vl-space-4);
  margin-top: var(--vl-space-2);
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
.vl-quote__id {
  font-family: var(--vl-font-mono);
}
</style>
