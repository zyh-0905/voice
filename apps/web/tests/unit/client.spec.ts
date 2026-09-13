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


describe('apiErrorMessage:把服务端错误体折成可读文案', () => {
  // FastAPI 的 detail 多数是 {'code': ...} 结构化对象;直接塞进 Error.message 会显示成
  // '[object Object]',真正的错误码被丢掉
  function stubError(body: unknown, status: number) {
    vi.stubGlobal('fetch', vi.fn(async (url: string) =>
      String(url).includes('/auth/csrf')
        ? jsonResponse({ csrf_token: CSRF_TOKEN })
        : jsonResponse(body, status)))
    return fetchHttpClient('/api')
  }

  it('结构化 detail 不再显示 [object Object]', async () => {
    const err = await stubError({ detail: { code: 'VERSION_CONFLICT' } }, 409)
      .getSettings('p').catch((e: unknown) => e as ApiHttpError)
    expect(err).toBeInstanceOf(ApiHttpError)
    expect((err as ApiHttpError).message).toBe('VERSION_CONFLICT')
  })

  it('带 message 的结构化 detail 同时保留错误码与说明', async () => {
    const err = await stubError({ detail: { code: 'invalid_file', message: 'CSV 表头缺失' } }, 422)
      .getSettings('p').catch((e: unknown) => e as ApiHttpError)
    expect((err as ApiHttpError).message).toBe('invalid_file: CSV 表头缺失')
  })

  it('字符串 detail 保持原样', async () => {
    const err = await stubError({ detail: 'plain reason' }, 400)
      .getSettings('p').catch((e: unknown) => e as ApiHttpError)
    expect((err as ApiHttpError).message).toBe('plain reason')
  })

  it('无 detail 时回落到状态码文案', async () => {
    const err = await stubError({}, 503).getSettings('p').catch((e: unknown) => e as ApiHttpError)
    expect((err as ApiHttpError).message).toBe('Request failed (503)')
  })
})

describe('治理请求必须带上 §4.3 的选项', () => {
  beforeEach(() => { sessionStorage.clear(); vi.restoreAllMocks() })

  it('映射、工作表与时间策略真的送到 /validate', async () => {
    // 此前这里发的是 body: '{}' —— 四个选项在真实模式下一个都不生效,
    // 而向导照常前进、报告照常生成,看不出任何异常。
    const { calls } = stubFetch()
    await fetchHttpClient('/api').health('demo-project', 'ds-1', {
      mapping: { msg: 'content', fid: 'feedback_id' },
      sheet_name: '二月',
      time_policy: 'strict',
    })

    const validate = calls.find(c => c.url.includes('/validate'))
    expect(validate).toBeDefined()
    const sent = JSON.parse(String(validate?.init.body))
    expect(sent).toEqual({
      mapping: { msg: 'content', fid: 'feedback_id' },
      sheet_name: '二月',
      time_policy: 'strict',
    })
  })

  it('没有选项时仍然发一个合法对象,而不是空串', async () => {
    const { calls } = stubFetch()
    await fetchHttpClient('/api').health('demo-project', 'ds-1')

    const validate = calls.find(c => c.url.includes('/validate'))
    expect(JSON.parse(String(validate?.init.body))).toEqual({})
  })

  it('上传结果带回真实列名与工作表清单', async () => {
    // 映射步骤此前渲染的是写死的三列,因为 DatasetPreview 里根本没有列名
    const calls: Array<{ url: string; init: RequestInit }> = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit = {}) => {
      calls.push({ url, init })
      if (String(url).includes('/auth/csrf')) return jsonResponse({ csrf_token: CSRF_TOKEN })
      return jsonResponse({
        id: 'ds-1', name: 'm.xlsx', rows: 2, status: 'uploaded', hasTime: false,
        preview: { headers: ['msg', 'ts'], rows: [{ msg: '甲', ts: '' }],
                   sheet_name: '一月', sheet_names: ['一月', '二月'] },
      })
    }))

    const file = new File(['x'], 'm.xlsx')
    const preview = await fetchHttpClient('/api').upload('demo-project', file)

    expect(preview.headers).toEqual(['msg', 'ts'])
    expect(preview.sheetNames).toEqual(['一月', '二月'])
    expect(preview.sheetName).toBe('一月')
    expect(preview.rows_preview).toEqual([{ msg: '甲', ts: '' }])
  })
})
