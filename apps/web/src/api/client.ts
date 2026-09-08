import type {DatasetPreview,ImportHealth,AnalysisRun} from '../types/domain'

export interface ApiClient {
  upload(file: File, signal?: AbortSignal): Promise<DatasetPreview>
  health(id: string, signal?: AbortSignal): Promise<ImportHealth>
  runAnalysis(id: string, signal?: AbortSignal): Promise<AnalysisRun>
}

export interface ApiErrorBody { detail?: string; message?: string }
export class ApiHttpError extends Error {
  constructor(public readonly status: number, message: string, public readonly body?: ApiErrorBody) {
    super(message)
    this.name = 'ApiHttpError'
  }
}

/** Real HTTP implementation. The mock client remains the default for demo pages. */
export function fetchHttpClient(baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1'): ApiClient {
  const base = baseUrl.replace(/\/$/, '')
  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(`${base}${path}`, { ...init, headers: { Accept: 'application/json', ...(init.headers || {}) } })
    if (!response.ok) {
      let body: ApiErrorBody | undefined
      try { body = await response.json() } catch { /* non-json error */ }
      throw new ApiHttpError(response.status, body?.detail || body?.message || `Request failed (${response.status})`, body)
    }
    return response.json() as Promise<T>
  }
  return {
    upload(file, signal) {
      const form = new FormData(); form.append('file', file)
      return request<DatasetPreview>('/datasets/upload', { method: 'POST', body: form, signal })
    },
    health(id, signal) { return request<ImportHealth>(`/datasets/${encodeURIComponent(id)}/health`, { signal }) },
    runAnalysis(id, signal) { return request<AnalysisRun>('/analysis/runs', { method: 'POST', body: JSON.stringify({ dataset_id: id }), headers: { 'Content-Type': 'application/json' }, signal }) },
  }
}
