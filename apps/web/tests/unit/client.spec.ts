import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fetchHttpClient, setAccessToken, clearAccessToken } from '../../src/api/client'
describe('http auth', () => {
  beforeEach(() => { sessionStorage.clear(); vi.restoreAllMocks() })
  it('injects bearer token from session storage', async () => {
    setAccessToken('abc'); vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({id:'d'}), {status:200, headers:{'Content-Type':'application/json'}})))
    await fetchHttpClient('/api').health('d')
    expect((fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1].headers.Authorization).toBe('Bearer abc')
    clearAccessToken()
  })
})
