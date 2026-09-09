<template>
  <aside class="vl-evidence-panel" data-testid="evidence-panel" aria-labelledby="vl-evidence-title">
    <header class="vl-evidence-panel__header">
      <h2 id="vl-evidence-title" class="vl-evidence-panel__title" tabindex="-1">{{ evidence.topicTitle }}</h2>
      <button type="button" class="vl-evidence-panel__close" data-testid="evidence-close" @click="emit('close')">
        关闭证据
      </button>
    </header>
    <EvidenceContent :evidence="evidence" :run-label="runLabel" />
  </aside>
</template>

<script setup lang="ts">
// EvidencePanel — 风格规范 6.4/9.5:桌面 360px 非模态 aside;
// 不锁背景、不加 aria-modal、不陷阱焦点;标题可聚焦,提供「回到列表」与关闭入口。
import type { EvidenceContext } from '../../types/domain'
import EvidenceContent from './EvidenceContent.vue'

defineProps<{
  evidence: EvidenceContext
  runLabel: string
}>()

const emit = defineEmits<{
  close: []
}>()
</script>

<style scoped>
.vl-evidence-panel {
  min-width: 0;
  border: 1px solid var(--vl-color-border);
  border-radius: var(--vl-radius-panel);
  background: var(--vl-color-surface);
  padding: var(--vl-space-5);
  box-shadow: var(--vl-shadow-panel);
}
.vl-evidence-panel__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--vl-space-3);
  margin-bottom: var(--vl-space-3);
}
.vl-evidence-panel__title {
  margin: 0;
  font-size: var(--vl-text-md);
  line-height: var(--vl-space-6);
  font-weight: 600;
}
.vl-evidence-panel__close {
  border: none;
  background: none;
  padding: var(--vl-space-1) 0;
  font-size: var(--vl-text-xs);
  color: var(--vl-color-brand);
  cursor: pointer;
  min-height: var(--vl-control-height-compact);
}
</style>
