<template>
  <section class="vl-panel vl-panel-component">
    <header v-if="title || description || $slots.actions" class="vl-panel-component__header">
      <div class="vl-panel-component__heading">
        <h2 v-if="title" class="vl-panel-component__title">{{ title }}</h2>
        <p v-if="description" class="vl-panel-component__desc">{{ description }}</p>
      </div>
      <div v-if="$slots.actions" class="vl-panel-component__actions">
        <slot name="actions" />
      </div>
    </header>
    <slot />
  </section>
</template>

<script setup lang="ts">
// VlPanel — 风格规范 6.1:白底、1px 边框、12px 圆角;标题/说明/正文/操作插槽;不嵌套三层白卡。
defineProps<{
  title?: string
  description?: string
}>()
</script>

<style scoped>
.vl-panel-component__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--vl-space-4);
  margin-bottom: var(--vl-space-4);
}
.vl-panel-component__heading {
  min-width: 0;
}
.vl-panel-component__title {
  margin: 0;
  font-size: var(--vl-text-md);
  line-height: var(--vl-space-6);
  font-weight: 600;
}
.vl-panel-component__desc {
  margin: var(--vl-space-2) 0 0;
  font-size: var(--vl-text-sm);
  color: var(--vl-color-text-muted);
}
.vl-panel-component__actions {
  display: flex;
  gap: var(--vl-space-2);
  flex-wrap: wrap;
  justify-content: flex-end;
}
</style>
