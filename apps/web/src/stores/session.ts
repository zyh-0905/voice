import { defineStore } from 'pinia'
import { ref } from 'vue'

import { isMockMode } from '../api/client'

export type UserRole = 'ANALYST' | 'VIEWER'
export interface User { id: string; name: string; email: string; role: UserRole }

export const DEMO_USER: User = { id: 'demo-user', name: 'Demo Analyst', email: 'demo@voicelens.local', role: 'ANALYST' }
export const DEMO_VIEWER: User = { id: 'viewer-user', name: 'Demo Viewer', email: 'viewer@voicelens.local', role: 'VIEWER' }

const SESSION_KEY = 'voicelens:session:user'

export const useSessionStore = defineStore('session', () => {
  const stored = typeof window !== 'undefined' ? window.sessionStorage.getItem(SESSION_KEY) : null
  let parsed: User | null = null
  if (stored) {
    try { parsed = JSON.parse(stored) as User } catch { parsed = null }
  }
  const user = ref<User | null>(parsed)
  // 演示标记只在演示:mock 构建(默认)为 true;真实 API 构建不再挂「合成演示数据」
  // 横幅——真实数据被标成演示与演示数据冒充真实是同一个错(UI 规范:演示常显标记)。
  const isDemo = ref(isMockMode())

  function apply(next: User) {
    user.value = next
    if (typeof window !== 'undefined') window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(next))
  }
  function login() { apply(DEMO_USER) }
  function loginAsViewer() { apply(DEMO_VIEWER) }
  /** 真实登录:用后端返回的用户身份写入会话 */
  function loginAs(next: User) { apply(next) }
  function logout() {
    user.value = null
    if (typeof window !== 'undefined') window.sessionStorage.removeItem(SESSION_KEY)
  }
  return { user, isDemo, login, loginAsViewer, loginAs, logout }
})
