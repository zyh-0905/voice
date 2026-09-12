<template>
  <div class="vl-empty" data-testid="empty-state">
    <!-- 轻量线稿(风格规范 2.2:空态最多一种原创线稿风格),装饰性 -->
    <svg class="vl-empty__art" viewBox="0 0 96 64" aria-hidden="true" focusable="false">
      <rect x="12" y="10" width="72" height="44" rx="6" class="vl-empty__frame" />
      <path d="M24 26h30M24 34h48M24 42h22" class="vl-empty__line" />
      <circle cx="72" cy="26" r="8" class="vl-empty__lens" />
      <path d="M78 32l8 8" class="vl-empty__handle" />
    </svg>
    <p class="vl-empty__text">{{ text }}</p>
    <p v-if="hint" class="vl-empty__hint">{{ hint }}</p>
    <div v-if="$slots.action" class="vl-empty__action">
      <slot name="action" />
    </div>
  </div>
</template>

<script setup lang="ts">
// EmptyState — 空态/无数据分流(风格规范 9.1:未导入、尚未分析、筛选无结果、无权限
// 是不同状态,文案与下一步动作不同)。线稿为原创几何线型,不使用第三方插画。
defineProps<{
  text: string
  hint?: string
}>()
</script>

<style scoped>
.vl-empty {
  display: grid;
  justify-items: center;
  gap: var(--vl-space-3);
  padding: var(--vl-space-8) var(--vl-space-4);
  text-align: center;
}
.vl-empty__art {
  width: 6rem;
  height: 4rem;
}
.vl-empty__frame,
.vl-empty__line,
.vl-empty__lens,
.vl-empty__handle {
  fill: none;
  stroke: var(--vl-color-brand-line);
  stroke-width: 1.5;
  stroke-linecap: round;
}
.vl-empty__line {
  stroke: var(--vl-color-border);
}
.vl-empty__lens {
  stroke: var(--vl-color-brand);
}
.vl-empty__text {
  margin: 0;
  color: var(--vl-color-text-secondary);
}
.vl-empty__hint {
  margin: 0;
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-muted);
}
.vl-empty__action {
  margin-top: var(--vl-space-2);
}
</style>
