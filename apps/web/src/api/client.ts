import type {DatasetPreview,ImportHealth,AnalysisRun} from '../types/domain'

export interface ApiClient {
  upload(file: File, signal?: AbortSignal): Promise<DatasetPreview>
  upload(projectId: string, file: File, signal?: AbortSignal): Promise<DatasetPreview>
  health(id: string, signal?: AbortSignal): Promise<ImportHealth>
  health(projectId: string, id: string, signal?: AbortSignal): Promise<ImportHealth>
  runAnalysis(id: string, signal?: AbortSignal): Promise<AnalysisRun>
  runAnalysis(projectId: string, id: string, signal?: AbortSignal): Promise<AnalysisRun>
}

export interface ApiErrorBody { detail?: string; message?: string }
export class ApiHttpError extends Error {
  constructor(public readonly status: number, message: string, public readonly body?: ApiErrorBody) {
    super(message)
    this.name = 'ApiHttpError'
  }
}
const ACCESS_TOKEN_KEY = 'voicelens:access_token'
export function setAccessToken(token: string): void { if (typeof window !== 'undefined') window.sessionStorage.setItem(ACCESS_TOKEN_KEY, token) }
export function clearAccessToken(): void { if (typeof window !== 'undefined') window.sessionStorage.removeItem(ACCESS_TOKEN_KEY) }
function getAccessToken(): string | null { return typeof window === 'undefined' ? null : window.sessionStorage.getItem(ACCESS_TOKEN_KEY) }

/** Real HTTP implementation. The mock client remains the default for demo pages. */
export function fetchHttpClient(baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1'): ApiClient {
  const base = baseUrl.replace(/\/$/, '')
  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const token = getAccessToken()
    const response = await fetch(`${base}${path}`, { ...init, headers: { Accept: 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(init.headers || {}) } })
    if (!response.ok) {
      let body: ApiErrorBody | undefined
      try { body = await response.json() } catch { /* non-json error */ }
      throw new ApiHttpError(response.status, body?.detail || body?.message || `Request failed (${response.status})`, body)
    }
    return response.json() as Promise<T>
  }
  return {
    upload(projectOrFile: string | File, fileOrSignal?: File | AbortSignal, maybeSignal?: AbortSignal) {
      const projectId = typeof projectOrFile === 'string' ? projectOrFile : 'demo-project'
      const file = (typeof projectOrFile === 'string' ? fileOrSignal : projectOrFile) as File
      const signal = typeof projectOrFile === 'string' ? maybeSignal : fileOrSignal as AbortSignal | undefined
      const form = new FormData(); form.append('file', file)
      form.append('consent', 'true')
      return request<DatasetPreview>(`/projects/${encodeURIComponent(projectId)}/datasets`, { method: 'POST', body: form, signal })
    },
    health(projectOrId: string, idOrSignal?: string | AbortSignal, maybeSignal?: AbortSignal) {
      const projectId = typeof idOrSignal === 'string' ? projectOrId : 'demo-project'
      const id = typeof idOrSignal === 'string' ? idOrSignal : projectOrId
      const signal = typeof idOrSignal === 'string' ? maybeSignal : idOrSignal
      return request<ImportHealth>(`/projects/${encodeURIComponent(projectId)}/datasets/${encodeURIComponent(id)}/validate`, { method: 'POST', body: '{}', headers: {'Content-Type':'application/json'}, signal })
    },
    runAnalysis(projectOrId: string, idOrSignal?: string | AbortSignal, maybeSignal?: AbortSignal) {
      const projectId = typeof idOrSignal === 'string' ? projectOrId : 'demo-project'
      const id = typeof idOrSignal === 'string' ? idOrSignal : projectOrId
      const signal = typeof idOrSignal === 'string' ? maybeSignal : idOrSignal
      return request<AnalysisRun>(`/projects/${encodeURIComponent(projectId)}/analyses`, { method: 'POST', body: JSON.stringify({ dataset_ids: [id] }), headers: { 'Content-Type': 'application/json' }, signal })
    },
  }
}
