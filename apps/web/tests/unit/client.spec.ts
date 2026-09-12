import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ApiHttpError, fetchHttpClient, setAccessToken, clearAccessToken } from '../../src/api/client'

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

/** 路由桩:按 URL 片段返回对应响应,用于成员/设置契约断言 */
function stubRoutes(routes: Array<{ match: string; body: unknown; status?: number }>) {
  const calls: Array<{ url: string; init: RequestInit }> = []
  const mock = vi.fn(async (url: string, init: RequestInit = {}) => {
    calls.push({ url, init })
    if (String(url).includes('/auth/csrf')) return jsonResponse({ csrf_token: CSRF_TOKEN })
    const route = routes.find(item => String(url).includes(item.match))
    return jsonResponse(route?.body ?? {}, route?.status ?? 200)
  })
  vi.stubGlobal('fetch', mock)
  return { calls, mock }
}

describe('http client project members & settings', () => {
  beforeEach(() => { sessionStorage.clear(); vi.restoreAllMocks() })

  it('成员列表解包 {items,total} 并对项目 id 编码', async () => {
    const { calls } = stubRoutes([{
      match: '/members',
      body: { items: [{ id: 'owner-1', display_name: 'Demo Analyst', role: 'OWNER' }], total: 1 },
    }])
    const members = await fetchHttpClient('/api').listMembers('demo project')
    expect(members).toEqual([{ id: 'owner-1', display_name: 'Demo Analyst', role: 'OWNER' }])
    expect(calls.find(c => c.url.includes('/members'))?.url).toBe('/api/projects/demo%20project/members')
  })

  it('读取设置走 GET 且不取 CSRF 令牌', async () => {
    const settings = {
      timezone: 'UTC',
      limits: { max_feedback_rows: 5000, max_upload_bytes: 1024 },
      rules: { min_severity: 'LOW', scan_on_import: true },
      model_available: true,
      version: 1,
    }
    const { calls } = stubRoutes([{ match: '/settings', body: settings }])
    const result = await fetchHttpClient('/api').getSettings('demo-project')
    expect(result).toEqual(settings)
    expect(calls.some(c => c.url.includes('/auth/csrf'))).toBe(false)
    expect(calls.find(c => c.url.includes('/settings'))?.init.method).toBeUndefined()
  })

  it('保存设置发送 PATCH 与 CSRF 头,不携带幂等键(expected_version 即守卫)', async () => {
    const { calls } = stubRoutes([{ match: '/settings', body: { version: 2 } }])
    await fetchHttpClient('/api').patchSettings('demo-project', { expected_version: 1, timezone: 'Asia/Shanghai' })
    const call = calls.find(c => c.url.includes('/settings'))
    const headers = call?.init.headers as Record<string, string>
    expect(call?.init.method).toBe('PATCH')
    expect(headers['X-CSRF-Token']).toBe(CSRF_TOKEN)
    expect(headers['Idempotency-Key']).toBeUndefined()
    expect(JSON.parse(String(call?.init.body))).toEqual({ expected_version: 1, timezone: 'Asia/Shanghai' })
  })

  it('409 版本冲突映射为 ApiHttpError(status=409)', async () => {
    stubRoutes([{ match: '/settings', body: { detail: { code: 'VERSION_CONFLICT' } }, status: 409 }])
    const failure = await fetchHttpClient('/api')
      .patchSettings('demo-project', { expected_version: 1, timezone: 'UTC' })
      .catch((err: unknown) => err)
    expect(failure).toBeInstanceOf(ApiHttpError)
    expect((failure as ApiHttpError).status).toBe(409)
  })
})
