<template>
  <header class="vl-page-header">
    <div class="vl-page-header__text">
      <div class="vl-page-header__heading">
        <span v-if="icon" class="vl-page-header__icon" aria-hidden="true">
          <el-icon :size="20"><component :is="icon" /></el-icon>
        </span>
        <h1 class="vl-page-header__title" data-testid="page-title">{{ title }}</h1>
      </div>
      <p v-if="description" class="vl-page-header__desc">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="vl-page-header__actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup lang="ts">
// PageHeader — 风格规范 6.1:一个 h1,标题 26px、说明 14px,标题区下距 24px,右侧主操作,窄屏换行。
// v1.2:可选语义图标(渐变图标块),统一各页标题观感。
import type { Component } from 'vue'

defineProps<{
  title: string
  description?: string
  icon?: Component
}>()
</script>

<style scoped>
.vl-page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--vl-space-4);
  margin-bottom: var(--vl-space-6);
}
.vl-page-header__text {
  min-width: 0;
}
.vl-page-header__heading {
  display: flex;
  align-items: center;
  gap: var(--vl-space-3);
}
.vl-page-header__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2.25rem;
  height: 2.25rem;
  border-radius: var(--vl-radius-control);
  background: var(--vl-gradient-brand-soft);
  color: var(--vl-color-brand-ink);
  box-shadow: var(--vl-highlight-inset);
  flex: none;
}
.vl-page-header__title {
  margin: 0;
  font-size: var(--vl-text-xl);
  line-height: 2.25rem;
  font-weight: 600;
}
.vl-page-header__desc {
  margin: var(--vl-space-2) 0 0;
  font-size: var(--vl-text-sm);
  color: var(--vl-color-text-muted);
}
.vl-page-header__actions {
  display: flex;
  align-items: center;
  gap: var(--vl-space-3);
  flex-wrap: wrap;
  justify-content: flex-end;
}
@media (max-width: 767px) {
  .vl-page-header {
    flex-direction: column;
  }
  .vl-page-header__actions {
    justify-content: flex-start;
  }
}
</style>
