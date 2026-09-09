import { defineStore } from 'pinia'
import { ref } from 'vue'

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
  const isDemo = ref(true)

  function apply(next: User) {
    user.value = next
    if (typeof window !== 'undefined') window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(next))
  }
  function login() { apply(DEMO_USER) }
  function loginAsViewer() { apply(DEMO_VIEWER) }
  function logout() {
    user.value = null
    if (typeof window !== 'undefined') window.sessionStorage.removeItem(SESSION_KEY)
  }
  return { user, isDemo, login, loginAsViewer, logout }
})
