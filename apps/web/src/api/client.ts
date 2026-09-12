import type {
  AnalysisRun,
  DatasetBatch,
  DatasetPreview,
  ImportHealth,
  ReviewRecord,
  RiskItem,
  SummaryResponse,
  TaskDetail,
  TaskSummary,
  TopicRow,
  TrendPoint,
} from '../types/domain'
import { mockApi } from './mock'

export interface TaskConfirmBody {
  expected_version: number
  owner_id: string
  due_at: string
  acceptance: string
}

export interface TaskTransitionBody {
  action: 'start' | 'submit' | 'approve' | 'reject' | 'cancel'
  expected_version: number
  comment: string
  material_refs?: string[]
}

export interface ReviewCreateBody {
  task_id?: string | null
  run_id: string
  revision: number
  topic_version_ids: string[]
  n_before: number
  N_before: number
  n_after: number
  N_after: number
}

export interface LoginUser {
  id: string
  name: string
  email: string
  role: string
}

export interface LoginResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: LoginUser
}

export interface ApiClient {
  upload(file: File, signal?: AbortSignal): Promise<DatasetPreview>
  upload(projectId: string, file: File, signal?: AbortSignal): Promise<DatasetPreview>
  health(id: string, signal?: AbortSignal): Promise<ImportHealth>
  health(projectId: string, id: string, signal?: AbortSignal): Promise<ImportHealth>
  runAnalysis(id: string, signal?: AbortSignal): Promise<AnalysisRun>
  runAnalysis(projectId: string, id: string, signal?: AbortSignal): Promise<AnalysisRun>
  /** POST /auth/login,返回真实 access_token 与用户 */
  login(username: string, password: string): Promise<LoginResponse>
  /** 工程计划 7.7:行动首页只读聚合 */
  summary(projectId: string, signal?: AbortSignal): Promise<SummaryResponse>
  topics(projectId: string, signal?: AbortSignal): Promise<TopicRow[]>
  trend(projectId: string, signal?: AbortSignal): Promise<TrendPoint[]>
  taskSummaries(projectId: string, signal?: AbortSignal): Promise<TaskSummary[]>
  getTask(projectId: string, taskId: string, signal?: AbortSignal): Promise<TaskDetail>
  createTaskDraft(projectId: string, body: { title: string; source_topic_version_id?: string | null }): Promise<TaskSummary>
  confirmTask(projectId: string, taskId: string, body: TaskConfirmBody, idempotencyKey: string): Promise<TaskSummary>
  transitionTask(projectId: string, taskId: string, body: TaskTransitionBody, idempotencyKey: string): Promise<TaskSummary>
  listRisks(projectId: string, signal?: AbortSignal): Promise<RiskItem[]>
  listReviews(projectId: string, signal?: AbortSignal): Promise<ReviewRecord[]>
  getReview(projectId: string, reviewId: string, signal?: AbortSignal): Promise<ReviewRecord>
  createReview(projectId: string, body: ReviewCreateBody): Promise<ReviewRecord>
  recentBatches(projectId: string, signal?: AbortSignal): Promise<DatasetBatch[]>
  /** GET /exports/redacted.csv,返回脱敏导出文件 */
  exportRedactedCsv(projectId: string, signal?: AbortSignal): Promise<Blob>
}

/** 按 VITE_USE_MOCK 选择真实/mock 客户端;所有页面与 composable 统一走此入口 */
export function apiClient(): ApiClient {
  return import.meta.env.VITE_USE_MOCK !== 'false' ? mockApi : fetchHttpClient()
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
  /** 列表端点沿用服务端 {items, total} 分页信封;最终契约以 OpenAPI 为准。 */
  async function list<T>(path: string, signal?: AbortSignal): Promise<T[]> {
    const response = await request<{ items: T[] } | T[]>(path, { signal })
    return Array.isArray(response) ? response : response.items
  }
  const project = (projectId: string) => `/projects/${encodeURIComponent(projectId)}`
  return {
    upload(projectOrFile: string | File, fileOrSignal?: File | AbortSignal, maybeSignal?: AbortSignal) {
      const projectId = typeof projectOrFile === 'string' ? projectOrFile : 'demo-project'
      const file = (typeof projectOrFile === 'string' ? fileOrSignal : projectOrFile) as File
      const signal = typeof projectOrFile === 'string' ? maybeSignal : fileOrSignal as AbortSignal | undefined
      const form = new FormData(); form.append('file', file)
      form.append('consent', 'true')
      return request<DatasetPreview>(`${project(projectId)}/datasets`, { method: 'POST', body: form, signal })
    },
    health(projectOrId: string, idOrSignal?: string | AbortSignal, maybeSignal?: AbortSignal) {
      const projectId = typeof idOrSignal === 'string' ? projectOrId : 'demo-project'
      const id = typeof idOrSignal === 'string' ? idOrSignal : projectOrId
      const signal = typeof idOrSignal === 'string' ? maybeSignal : idOrSignal
      return request<ImportHealth>(`${project(projectId)}/datasets/${encodeURIComponent(id)}/validate`, { method: 'POST', body: '{}', headers: { 'Content-Type': 'application/json' }, signal })
    },
    runAnalysis(projectOrId: string, idOrSignal?: string | AbortSignal, maybeSignal?: AbortSignal) {
      const projectId = typeof idOrSignal === 'string' ? projectOrId : 'demo-project'
      const id = typeof idOrSignal === 'string' ? idOrSignal : projectOrId
      const signal = typeof idOrSignal === 'string' ? maybeSignal : idOrSignal
      return request<AnalysisRun>(`${project(projectId)}/analyses`, { method: 'POST', body: JSON.stringify({ dataset_ids: [id] }), headers: { 'Content-Type': 'application/json' }, signal })
    },
    login(username: string, password: string) {
      return request<LoginResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }), headers: { 'Content-Type': 'application/json' } })
    },
    async exportRedactedCsv(projectId: string, signal?: AbortSignal) {
      const token = getAccessToken()
      const response = await fetch(`${base}${project(projectId)}/exports/redacted.csv`, {
        signal,
        headers: { Accept: 'text/csv', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      })
      if (!response.ok) throw new ApiHttpError(response.status, `Export failed (${response.status})`)
      return response.blob()
    },
    summary(projectId: string, signal?: AbortSignal) {
      return request<SummaryResponse>(`${project(projectId)}/summary`, { signal })
    },
    topics(projectId: string, signal?: AbortSignal) {
      return list<TopicRow>(`${project(projectId)}/topics`, signal)
    },
    trend(projectId: string, signal?: AbortSignal) {
      return list<TrendPoint>(`${project(projectId)}/trend`, signal)
    },
    taskSummaries(projectId: string, signal?: AbortSignal) {
      return list<TaskSummary>(`${project(projectId)}/tasks`, signal)
    },
    getTask(projectId: string, taskId: string, signal?: AbortSignal) {
      return request<TaskDetail>(`${project(projectId)}/tasks/${encodeURIComponent(taskId)}`, { signal })
    },
    createTaskDraft(projectId: string, body: { title: string; source_topic_version_id?: string | null }) {
      return request<TaskSummary>(`${project(projectId)}/tasks/drafts`, {
        method: 'POST', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' },
      })
    },
    confirmTask(projectId: string, taskId: string, body: TaskConfirmBody, idempotencyKey: string) {
      return request<TaskSummary>(`${project(projectId)}/tasks/${encodeURIComponent(taskId)}/confirm`, {
        method: 'POST', body: JSON.stringify(body),
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
      })
    },
    transitionTask(projectId: string, taskId: string, body: TaskTransitionBody, idempotencyKey: string) {
      return request<TaskSummary>(`${project(projectId)}/tasks/${encodeURIComponent(taskId)}/transition`, {
        method: 'POST', body: JSON.stringify(body),
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
      })
    },
    listRisks(projectId: string, signal?: AbortSignal) {
      return list<RiskItem>(`${project(projectId)}/risks`, signal)
    },
    listReviews(projectId: string, signal?: AbortSignal) {
      return list<ReviewRecord>(`${project(projectId)}/reviews`, signal)
    },
    getReview(projectId: string, reviewId: string, signal?: AbortSignal) {
      return request<ReviewRecord>(`${project(projectId)}/reviews/${encodeURIComponent(reviewId)}`, { signal })
    },
    createReview(projectId: string, body: ReviewCreateBody) {
      return request<ReviewRecord>(`${project(projectId)}/reviews`, {
        method: 'POST', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' },
      })
    },
    async recentBatches(projectId: string, signal?: AbortSignal) {
      // 后端数据集实体为 snake_case 规范形状,此处映射为前端 DatasetBatch 契约
      const rows = await list<Record<string, unknown>>(`${project(projectId)}/datasets`, signal)
      return rows.map((it) => ({
        id: String(it.id ?? ''),
        name: String(it.name ?? it.id ?? ''),
        rows: Number(it.rows ?? 0),
        status: String(it.status ?? ''),
        createdAt: String(it.created_at ?? ''),
      })) as DatasetBatch[]
    },
  }
}
