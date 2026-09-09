import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import AppShell from '../layouts/AppShell.vue'
import { useSessionStore } from '../stores/session'
import { useProjectStore } from '../stores/project'

// 兼容旧入口:/overview → /p/{selectedProjectId}/overview(默认 demo-project)
function toOverview(): string {
  const project = useProjectStore()
  return `/p/${project.selectedProjectId}/overview`
}

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: toOverview },
  { path: '/overview', redirect: toOverview },
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue') },
  { path: '/projects', name: 'projects', component: () => import('../views/ProjectsView.vue') },
  {
    path: '/p/:p',
    component: AppShell,
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: (to) => `${to.path}/overview` },
      { path: 'overview', name: 'overview', component: () => import('../views/OverviewView.vue'), meta: { title: '工作台' } },
      { path: 'imports', name: 'imports', component: () => import('../features/imports/ImportPage.vue'), meta: { title: '数据导入' } },
      { path: 'analysis', name: 'analysis', component: () => import('../features/analysis/AnalysisProgress.vue'), meta: { title: '分析进度' } },
      { path: 'topics', name: 'topics', component: () => import('../views/TopicsPlaceholderView.vue'), meta: { title: '主题洞察' } },
      { path: 'risks', name: 'risks', component: () => import('../features/risks/RisksPage.vue'), meta: { title: '风险复核' } },
      { path: 'tasks', name: 'tasks', component: () => import('../features/tasks/TasksPage.vue'), meta: { title: '整改任务' } },
      { path: 'reviews', name: 'reviews', component: () => import('../features/reviews/ReviewsPage.vue'), meta: { title: '效果复盘' } },
      { path: 'settings', name: 'settings', component: () => import('../features/settings/SettingsPage.vue'), meta: { title: '设置' } },
      { path: 'exports', name: 'exports', component: () => import('../features/exports/ExportsPage.vue'), meta: { title: '导出' } },
    ],
  },
]

// StyleLab 仅 development/test 注册,生产默认构建不含该路由(风格规范 11.1)
if (import.meta.env.DEV || import.meta.env.MODE === 'test') {
  routes.push({ path: '/__dev/style-lab', name: 'style-lab', component: () => import('../features/dev/StyleLabPage.vue') })
}

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to) => {
  if (to.meta.requiresAuth && !useSessionStore().user) return '/login'
})

export default router
