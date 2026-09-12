import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fetchHttpClient, setAccessToken, clearAccessToken } from '../../src/api/client'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

const CSRF_TOKEN = 'csrf-token-1'

/** fetch 桩:区分 CSRF 引导与业务请求,并记录调用 */
function stubFetch() {
  const calls: Array<{ url: string; init: RequestInit }> = []
  const mock = vi.fn(async (url: string, init: RequestInit = {}) => {
    calls.push({ url, init })
    if (String(url).includes('/auth/csrf')) return jsonResponse({ csrf_token: CSRF_TOKEN })
    return jsonResponse({ id: 'd' })
  })
  vi.stubGlobal('fetch', mock)
  return { calls, mock }
}

describe('http client auth', () => {
  beforeEach(() => { sessionStorage.clear(); vi.restoreAllMocks() })

  it('注入会话存储中的 bearer 令牌', async () => {
    setAccessToken('abc')
    const { calls } = stubFetch()
    await fetchHttpClient('/api').health('d')
    const health = calls.find(c => c.url.includes('/datasets/'))
    expect((health?.init.headers as Record<string, string>).Authorization).toBe('Bearer abc')
    clearAccessToken()
  })

  it('写请求先取 CSRF 令牌并放入头部', async () => {
    const { calls } = stubFetch()
    await fetchHttpClient('/api').createTaskDraft('demo-project', { title: '草稿' })
    expect(calls.some(c => c.url.includes('/auth/csrf'))).toBe(true)
    const write = calls.find(c => c.url.includes('/tasks/drafts'))
    const headers = write?.init.headers as Record<string, string>
    expect(headers['X-CSRF-Token']).toBe(CSRF_TOKEN)
    expect(write?.init.credentials).toBe('include')
  })

  it('读请求不取 CSRF 令牌', async () => {
    const { calls } = stubFetch()
    await fetchHttpClient('/api').summary('demo-project')
    expect(calls.some(c => c.url.includes('/auth/csrf'))).toBe(false)
  })

  it('登录自身不预先取令牌(服务端按环境判定)', async () => {
    const { calls } = stubFetch()
    await fetchHttpClient('/api').login('demo', 'demo')
    expect(calls.some(c => c.url.includes('/auth/csrf'))).toBe(false)
    expect(calls.some(c => c.url.includes('/auth/login'))).toBe(true)
  })
})
