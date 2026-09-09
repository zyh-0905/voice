<template>
  <div class="vl-page">
    <PageHeader title="选择项目" description="选择一个项目进入工作台。仅展示你有权限访问的项目。" />
    <ul class="vl-projects">
      <li v-for="project in projects.projects" :key="project.id" class="vl-projects__item">
        <button type="button" class="vl-project-card" data-testid="project-card" @click="enter(project.id)">
          <span class="vl-project-card__name">{{ project.name }}</span>
          <span v-if="project.description" class="vl-project-card__desc">{{ project.description }}</span>
          <span class="vl-project-card__meta">
            <span class="vl-project-card__role">角色:{{ roleLabel }}</span>
            <DemoNotice source-kind="synthetic" />
          </span>
        </button>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
// ProjectsView — 风格规范第 7 节 /projects:简洁项目列表/小卡片,显示角色、项目名、真实/演示身份。
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectStore } from '../stores/project'
import { useSessionStore } from '../stores/session'
import PageHeader from '../components/common/PageHeader.vue'
import DemoNotice from '../components/common/DemoNotice.vue'

const router = useRouter()
const projects = useProjectStore()
const session = useSessionStore()

const roleLabel = computed(() => (session.user?.role === 'VIEWER' ? '只读' : '可分析'))

function enter(projectId: string) {
  projects.selectProject(projectId)
  void router.push(`/p/${projectId}/overview`)
}
</script>

<style scoped>
.vl-projects {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr));
  gap: var(--vl-space-4);
}
.vl-project-card {
  width: 100%;
  text-align: start;
  display: flex;
  flex-direction: column;
  gap: var(--vl-space-2);
  border: 1px solid var(--vl-color-border);
  border-radius: var(--vl-radius-panel);
  background: var(--vl-color-surface);
  padding: var(--vl-space-5);
  cursor: pointer;
  box-shadow: var(--vl-shadow-panel);
  transition: border-color var(--vl-motion-fast) var(--vl-ease);
}
.vl-project-card:hover,
.vl-project-card:focus-visible {
  border-color: var(--vl-color-brand);
}
.vl-project-card__name {
  font-size: var(--vl-text-md);
  font-weight: 600;
}
.vl-project-card__desc {
  font-size: var(--vl-text-sm);
  color: var(--vl-color-text-muted);
}
.vl-project-card__meta {
  display: flex;
  align-items: center;
  gap: var(--vl-space-3);
  margin-top: var(--vl-space-2);
}
.vl-project-card__role {
  font-size: var(--vl-text-xs);
  color: var(--vl-color-text-secondary);
}
</style>
