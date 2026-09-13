// stores/project.ts — 项目列表与当前项目。
// 列表来自 GET /projects(经 apiClient(),mock 模式同样返回演示项目),
// 不再在前端硬编码:真实模式下硬编码数组会让切项目、权限过滤全部失真。
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { apiClient, type ProjectSummary } from '../api/client'

export type ProjectsStatus = 'idle' | 'loading' | 'success' | 'empty' | 'error'

export const useProjectStore = defineStore('project', () => {
  const projects = ref<ProjectSummary[]>([])
  const projectsStatus = ref<ProjectsStatus>('idle')
  const projectsError = ref('')
  const selectedProjectId = ref(sessionStorage.getItem('voicelens:project') || 'demo-project')
  const selectedProject = computed(() => projects.value.find(p => p.id === selectedProjectId.value) ?? projects.value[0])

  function selectProject(id: string) {
    selectedProjectId.value = id
    sessionStorage.setItem('voicelens:project', id)
  }

  /** 拉取有权限的项目;原先选中的项目已删除/无权访问时回退到第一项,避免路由停在打不开的项目 */
  async function loadProjects() {
    projectsStatus.value = 'loading'
    projectsError.value = ''
    try {
      const items = await apiClient().listProjects()
      projects.value = items
      if (items.length && !items.some(p => p.id === selectedProjectId.value)) {
        selectProject(items[0].id)
      }
      projectsStatus.value = items.length ? 'success' : 'empty'
    } catch (err) {
      projectsStatus.value = 'error'
      projectsError.value = err instanceof Error ? err.message : String(err)
    }
  }

  return { projects, projectsStatus, projectsError, selectedProjectId, selectedProject, selectProject, loadProjects }
})
