<template>
  <el-select
    class="vl-project-switcher"
    data-testid="project-switcher"
    :model-value="currentProjectId"
    aria-label="切换项目"
    @update:model-value="(value: string) => emit('change', value)"
  >
    <el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" />
  </el-select>
</template>

<script setup lang="ts">
// ProjectSwitcher — 风格规范 9.4:change 后调用方须取消旧请求、清理旧项目敏感视图。
defineProps<{
  projects: Array<{ id: string; name: string }>
  currentProjectId: string
}>()

const emit = defineEmits<{
  change: [projectId: string]
}>()
</script>

<style scoped>
.vl-project-switcher {
  width: 13rem;
}
</style>
