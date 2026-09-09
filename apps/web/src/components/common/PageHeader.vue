<template>
  <header class="vl-page-header">
    <div class="vl-page-header__text">
      <h1 class="vl-page-header__title" data-testid="page-title">{{ title }}</h1>
      <p v-if="description" class="vl-page-header__desc">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="vl-page-header__actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup lang="ts">
// PageHeader — 风格规范 6.1:一个 h1,标题 26px、说明 14px,标题区下距 24px,右侧主操作,窄屏换行。
defineProps<{
  title: string
  description?: string
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
