import { defineStore } from 'pinia'
import { ref } from 'vue'
type User = { id: string; name: string; email: string; role?: string }
const DEMO_USER: User = { id: 'demo-user', name: 'Demo Reviewer', email: 'demo@voicelens.local', role: 'ANALYST' }
const SESSION_KEY = 'voicelens:session:user'
export const useSessionStore = defineStore('session', () => {
  const stored = typeof window !== 'undefined' ? sessionStorage.getItem(SESSION_KEY) : null
  const user = ref<User | null>(stored ? JSON.parse(stored) as User : null)
  const isDemo = ref(true)
  function login() { user.value = DEMO_USER; if (typeof window !== 'undefined') sessionStorage.setItem(SESSION_KEY, JSON.stringify(DEMO_USER)) }
  function logout() { user.value = null; if (typeof window !== 'undefined') sessionStorage.removeItem(SESSION_KEY) }
  return { user, isDemo, login, logout }
})

