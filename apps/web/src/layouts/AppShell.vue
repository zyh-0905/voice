<template>
  <div class="vl-shell" data-testid="app-shell">
    <a class="vl-skip-link" href="#vl-main-content">跳到正文</a>

    <aside class="vl-sidebar">
      <div class="vl-sidebar__brand" aria-hidden="true">
        <span class="vl-sidebar__mark" />VoiceLens
      </div>
      <nav class="vl-nav" aria-label="主导航">
        <RouterLink
          v-for="item in navItems"
          :key="item.label"
          class="vl-nav__link"
          active-class="vl-nav__link--active"
          :to="`/p/${projectId}${item.path}`"
        >
          {{ item.label }}
        </RouterLink>
      </nav>
      <RouterLink
        class="vl-nav__link vl-nav__link--settings"
        active-class="vl-nav__link--active"
        :to="`/p/${projectId}/settings`"
      >
        设置
      </RouterLink>
    </aside>

    <div class="vl-shell__body">
      <header class="vl-header">
        <button
          type="button"
          class="vl-header__menu"
          :aria-expanded="navOpen"
          aria-controls="vl-nav-overlay"
          @click="navOpen = !navOpen"
        >
          <el-icon :size="20"><Menu /></el-icon><span>菜单</span>
        </button>
        <ProjectSwitcher :projects="project.projects" :current-project-id="projectId" @change="onProjectChange" />
        <span class="vl-header__location" aria-hidden="true">{{ currentTitle }}</span>
        <DemoNotice v-if="session.isDemo" source-kind="synthetic" :read-only="!canAct" />
        <div class="vl-header__user">
          <span class="vl-header__username">{{ session.user?.name }}</span>
          <VlButton variant="ghost" size="small" @click="logout">退出</VlButton>
        </div>
      </header>
      <main id="vl-main-content" class="vl-main">
        <router-view />
      </main>
    </div>

    <Teleport to="body">
      <div v-if="navOpen" class="vl-overlay" @click.self="navOpen = false">
        <nav id="vl-nav-overlay" class="vl-nav-overlay" aria-label="主导航">
          <RouterLink
            v-for="item in navItems"
            :key="item.label"
            class="vl-nav__link"
            active-class="vl-nav__link--active"
            :to="`/p/${projectId}${item.path}`"
            @click="navOpen = false"
          >
            {{ item.label }}
          </RouterLink>
          <RouterLink
            class="vl-nav__link vl-nav__link--settings"
            active-class="vl-nav__link--active"
            :to="`/p/${projectId}/settings`"
            @click="navOpen = false"
          >
            设置
          </RouterLink>
          <button type="button" class="vl-nav-overlay__close" @click="navOpen = false">关闭菜单</button>
        </nav>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
// AppShell — 风格规范 5.1:桌面 224px 左侧导航 + 64px 顶部栏 + 自适应内容区;
// 顶栏放项目切换、当前位置、合成演示/只读提示和用户菜单;页内主操作不放顶栏。
// 断点:≥1024 常驻侧栏;768-1023 菜单按钮打开模态导航;<768 菜单按钮。
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Menu } from '@element-plus/icons-vue'
import ProjectSwitcher from '../components/common/ProjectSwitcher.vue'
import DemoNotice from '../components/common/DemoNotice.vue'
import VlButton from '../components/common/VlButton.vue'
import { useSessionStore } from '../stores/session'
import { useProjectStore } from '../stores/project'
import { apiClient, clearAccessToken } from '../api/client'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const project = useProjectStore()

const projectId = computed(() => String(route.params.p || project.selectedProjectId))
const currentTitle = computed(() => String(route.meta.title ?? ''))
const canAct = computed(() => (session.user?.role ?? 'VIEWER') !== 'VIEWER')

// 导航名称固定(风格规范 5.1);分析进度作为导入/分析详情路径,不新增导航项
const navItems = [
  { label: '工作台', path: '/overview' },
  { label: '数据导入', path: '/imports' },
  { label: '主题洞察', path: '/topics' },
  { label: '风险复核', path: '/risks' },
  { label: '整改任务', path: '/tasks' },
  { label: '效果复盘', path: '/reviews' },
]

const navOpen = ref(false)
const onKey = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && navOpen.value) navOpen.value = false
}
watch(navOpen, (open) => {
  if (open) window.addEventListener('keydown', onKey)
  else window.removeEventListener('keydown', onKey)
})
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

function onProjectChange(selectedId: string) {
  project.selectProject(selectedId)
  // 切项目后进入新项目工作台;各页面数据层按路由参数取消旧请求
  void router.push(`/p/${selectedId}/overview`)
}

async function logout() {
  // 先通知服务端撤销会话(清 HttpOnly Cookie),再清本地状态
  try {
    await apiClient().logout()
  } catch {
    // 服务端不可达也要完成本地登出
  }
  session.logout()
  clearAccessToken()
  void router.push('/login')
}
</script>

<style scoped>
.vl-sidebar {
  position: sticky;
  top: 0;
  align-self: start;
  height: 100dvh;
  display: flex;
  flex-direction: column;
  border-inline-end: 1px solid var(--vl-color-border);
  background: var(--vl-color-surface);
  padding: var(--vl-space-4) var(--vl-space-3);
}
.vl-sidebar__brand {
  display: flex;
  align-items: center;
  gap: var(--vl-space-2);
  padding: var(--vl-space-2) var(--vl-space-3);
  font-size: var(--vl-text-md);
  font-weight: 600;
}
.vl-sidebar__mark {
  width: 1.5rem;
  height: 1.5rem;
  border-radius: var(--vl-radius-sm);
  background: var(--vl-color-brand);
}
.vl-nav {
  display: flex;
  flex-direction: column;
  gap: var(--vl-space-1);
  margin-top: var(--vl-space-4);
  flex: 1;
}
.vl-nav__link {
  display: block;
  min-height: var(--vl-control-height);
  padding: 10px var(--vl-space-3);
  border-radius: var(--vl-radius-control);
  color: var(--vl-color-text-secondary);
  text-decoration: none;
  font-weight: 500;
  transition: background-color var(--vl-motion-fast) var(--vl-ease);
}
.vl-nav__link:hover {
  background: var(--vl-color-hover);
}
.vl-nav__link--active {
  background: var(--vl-color-brand-soft);
  color: var(--vl-color-brand);
  font-weight: 600;
}
.vl-nav__link--settings {
  margin-top: var(--vl-space-3);
}
.vl-shell__body {
  min-width: 0;
}
.vl-header {
  position: sticky;
  top: 0;
  z-index: var(--vl-z-sticky);
  min-height: var(--vl-header-height);
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--vl-space-3) var(--vl-space-4);
  padding: var(--vl-space-2) var(--vl-space-6);
  background: var(--vl-color-surface);
  border-bottom: 1px solid var(--vl-color-border);
}
.vl-header__menu {
  display: none;
  align-items: center;
  gap: var(--vl-space-1);
  min-height: var(--vl-control-height);
  padding: 0 var(--vl-space-3);
  border: 1px solid var(--vl-color-border-control);
  border-radius: var(--vl-radius-control);
  background: var(--vl-color-surface);
  color: var(--vl-color-text);
  cursor: pointer;
}
.vl-header__location {
  font-size: var(--vl-text-sm);
  color: var(--vl-color-text-muted);
}
.vl-header__user {
  margin-inline-start: auto;
  display: flex;
  align-items: center;
  gap: var(--vl-space-3);
}
.vl-header__username {
  font-size: var(--vl-text-sm);
  color: var(--vl-color-text-secondary);
}
.vl-nav-overlay {
  position: fixed;
  inset-block: 0;
  inset-inline-start: 0;
  z-index: var(--vl-z-modal);
  width: min(80vw, 20rem);
  display: flex;
  flex-direction: column;
  gap: var(--vl-space-1);
  background: var(--vl-color-surface);
  padding: var(--vl-space-4) var(--vl-space-3);
  box-shadow: var(--vl-shadow-float);
}
.vl-nav-overlay__close {
  margin-top: var(--vl-space-4);
  min-height: var(--vl-control-height);
  border: 1px solid var(--vl-color-border-control);
  border-radius: var(--vl-radius-control);
  background: var(--vl-color-surface);
  cursor: pointer;
}
@media (max-width: 1023.98px) {
  .vl-sidebar {
    display: none;
  }
  .vl-header__menu {
    display: inline-flex;
  }
  .vl-header {
    padding: var(--vl-space-2) var(--vl-space-4);
  }
}
</style>
