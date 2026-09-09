import { defineStore } from 'pinia'
import { ref } from 'vue'
type User = { id: string; name: string; email: string; role?: string }
const DEMO_USER: User = { id: 'demo-user', name: 'Demo Reviewer', email: 'demo@voicelens.local', role: 'ANALYST' }
const SESSION_KEY = 'voicelens:session:user'
export const useSessionStore = defineStore('session', () => {
  const stored = typeof window !== 'undefined' ? window.sessionStorage.getItem(SESSION_KEY) : null
  let parsed: User | null = null
  if (stored) {
    try { parsed = JSON.parse(stored) as User } catch { parsed = null }
  }
  const user = ref<User | null>(parsed)
  const isDemo = ref(true)
  function login() {
    user.value = DEMO_USER
    if (typeof window !== 'undefined') window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(DEMO_USER))
  }
  function logout() {
    user.value = null
    if (typeof window !== 'undefined') window.sessionStorage.removeItem(SESSION_KEY)
  }
  return { user, isDemo, login, logout }
})

