import type {
  AnalysisRun,
  DatasetBatch,
  DatasetPreview,
  ImportHealthView,
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

export type CorrectionOperation = 'RENAME' | 'MERGE' | 'SPLIT' | 'CREATE'

export interface CorrectionBody {
  operation: CorrectionOperation
  expected_revision: number
  name?: string | null
  source_topic_ids?: string[]
  feedback_ids?: string[]
  reason: string
}

export interface TopicDetailResponse {
  topic: { topic_id: string; name: string; summary: string; severity: string; feedback_count: number; summary_revalidated?: boolean }
  evidence: Array<{ feedback_id: string; source_row: number; quote: string; quote_start: number; quote_end: number }>
  revision: number
}

export interface DeletionTarget {
  target_type: 'project' | 'dataset'
  target_id: string
}

export interface TaskPatchBody {
  expected_version: number
  title?: string
  source?: string
  priority?: string
  due_at?: string
  acceptance?: string
}

// —— W03 项目成员与项目设置 ——

export type ProjectMemberRole = 'OWNER' | 'EDITOR' | 'VIEWER'

export interface ProjectMember {
  id: string
  display_name: string
  role: ProjectMemberRole
}

export interface ProjectSettingsLimits {
  max_feedback_rows: number
  max_upload_bytes: number
}

export interface ProjectSettingsRules {
  min_severity: string
  scan_on_import: boolean
}

export interface ProjectSettings {
  timezone: string
  limits: ProjectSettingsLimits
  rules: ProjectSettingsRules
  model_available: boolean
  version: number
}

export interface ProjectSettingsPatchBody {
  expected_version: number
  timezone?: string
  limits?: ProjectSettingsLimits
  rules?: ProjectSettingsRules
  model_available?: boolean
}

export interface FeedbackSource {
  feedback_id: string
  dataset_id: string
  dataset_name: string
  source_row: number
  channel: string | null
  occurred_at: string | null
  text: string
  segments: Array<{ start: number; end: number; text: string }>
}

export interface ExportJob {
  id: string
  project_id: string
  scope: string
  state: string
  row_count: number | null
  created_at: string
  expires_at: string
  expired: boolean
  invalidated: boolean
  download_path: string
}

export interface DeletionBody extends DeletionTarget {
  /** 仅执行删除需要:用户逐字输入的目标名称 */
  confirm_name: string
}

export interface DeletionPreview {
  target_type: 'project' | 'dataset'
  target_id: string
  target_name: string
  datasets: number
  runs: number
  topics: number
  tasks: number
  reviews: number
  risks: number
  invalidates_reports?: boolean
}

export interface DeletionReceipt {
  job_id: string
  state: string
  target_type: string
  target_id: string
  steps: Array<{ name: string; status: string }>
  removed: Record<string, number>
}

export interface RiskReviewBody {
  decision: 'confirmed' | 'excluded' | 'reopened'
  reason: string
  expected_version?: number
}

/** 计划 7.5/8.7:窗口只给边界;n/N 由服务端从 run 推导,调用方不得提供 */
export interface ReviewWindowInput {
  start: string
  end: string
}

export interface ReviewCreateBody {
  task_id?: string | null
  run_id: string
  revision: number
  topic_version_ids: string[]
  before: ReviewWindowInput
  after: ReviewWindowInput
  /** 两个窗口共用的渠道/产品条件;不传表示不筛选 */
  filters?: Record<string, string | null>
  alignment_confirmed: boolean
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

export interface AuthConfig {
  mode: 'local' | 'oidc'
  issuer?: string
  audience?: string
  assertion_endpoint?: string
}

export interface ApiClient {
  upload(file: File, signal?: AbortSignal): Promise<DatasetPreview>
  upload(projectId: string, file: File, signal?: AbortSignal): Promise<DatasetPreview>
  /** POST /datasets/{id}/validate:完成治理校验并把批次转为 READY,返回 6 项治理计数 */
  health(id: string, signal?: AbortSignal): Promise<ImportHealthView>
  health(projectId: string, id: string, signal?: AbortSignal): Promise<ImportHealthView>
  runAnalysis(id: string, signal?: AbortSignal): Promise<AnalysisRun>
  runAnalysis(projectId: string, id: string, signal?: AbortSignal): Promise<AnalysisRun>
  /** POST /auth/login,返回真实 access_token 与用户 */
  login(username: string, password: string): Promise<LoginResponse>
  /** POST /auth/logout,服务端撤销会话并清除 Cookie */
  logout(): Promise<void>
  /** GET /auth/config,返回当前身份提供商模式(local / oidc) */
  authConfig(): Promise<AuthConfig>
  /** POST /auth/token,用外部身份提供商的断言换取本平台会话 */
  loginWithAssertion(assertion: string): Promise<LoginResponse>
  /** 工程计划 7.7:行动首页只读聚合 */
  summary(projectId: string, signal?: AbortSignal): Promise<SummaryResponse>
  topics(projectId: string, signal?: AbortSignal): Promise<TopicRow[]>
  trend(projectId: string, signal?: AbortSignal): Promise<TrendPoint[]>
  taskSummaries(projectId: string, signal?: AbortSignal): Promise<TaskSummary[]>
  getTask(projectId: string, taskId: string, signal?: AbortSignal): Promise<TaskDetail>
  createTaskDraft(projectId: string, body: { title: string; source_topic_version_id?: string | null }): Promise<TaskSummary>
  confirmTask(projectId: string, taskId: string, body: TaskConfirmBody, idempotencyKey: string): Promise<TaskSummary>
  transitionTask(projectId: string, taskId: string, body: TaskTransitionBody, idempotencyKey: string): Promise<TaskSummary>
  patchTask(projectId: string, taskId: string, body: TaskPatchBody): Promise<TaskSummary>
  /** W16:项目成员列表;任务负责人只能从此列表选择 */
  listMembers(projectId: string, signal?: AbortSignal): Promise<ProjectMember[]>
  /** W03/7.2:项目设置(时区、限额、规则、模型可用性) */
  getSettings(projectId: string, signal?: AbortSignal): Promise<ProjectSettings>
  /** W03/7.2:写入项目设置(仅 OWNER);expected_version 过期返回 409,不做幂等键 */
  patchSettings(projectId: string, body: ProjectSettingsPatchBody): Promise<ProjectSettings>
  getFeedback(projectId: string, feedbackId: string, signal?: AbortSignal): Promise<FeedbackSource>
  listRisks(projectId: string, signal?: AbortSignal): Promise<RiskItem[]>
  reviewRisk(projectId: string, riskId: string, body: RiskReviewBody): Promise<RiskItem>
  getTopicDetail(projectId: string, topicId: string, topicVersionId?: number, signal?: AbortSignal): Promise<TopicDetailResponse>
  correctTopic(projectId: string, topicId: string, body: CorrectionBody): Promise<{ revision: number; affected_topic_ids: string[] }>
  listReviews(projectId: string, signal?: AbortSignal): Promise<ReviewRecord[]>
  getReview(projectId: string, reviewId: string, signal?: AbortSignal): Promise<ReviewRecord>
  createReview(projectId: string, body: ReviewCreateBody): Promise<ReviewRecord>
  recentBatches(projectId: string, signal?: AbortSignal): Promise<DatasetBatch[]>
  previewDeletion(projectId: string, body: DeletionTarget): Promise<DeletionPreview>
  executeDeletion(projectId: string, body: DeletionBody, idempotencyKey: string): Promise<DeletionReceipt>
  /** POST /exports 创建导出任务(24h 失效) */
  createExport(projectId: string, body: { scope: string }, idempotencyKey: string): Promise<ExportJob>
  /** 下载导出文件:每次重新鉴权,过期/失效返回 410 */
  downloadExport(projectId: string, exportId: string): Promise<Blob>
}

/** 按 VITE_USE_MOCK 选择真实/mock 客户端;所有页面与 composable 统一走此入口 */
export function apiClient(): ApiClient {
  return import.meta.env.VITE_USE_MOCK !== 'false' ? mockApi : fetchHttpClient()
}

export interface ApiErrorDetail { code?: string; message?: string; [key: string]: unknown }
export interface ApiErrorBody { detail?: string | ApiErrorDetail; message?: string }

/** 把服务端的错误体折成一行可读文案。
 *
 * FastAPI 的 `detail` 多数是 `{'code': 'VERSION_CONFLICT'}` 这类结构化对象,直接
 * 塞进 `Error.message` 会显示成 `[object Object]`——真正的错误码被丢掉,排查时只
 * 能看到一条没信息的消息。字符串 detail 仍然原样使用。
 */
export function apiErrorMessage(body: ApiErrorBody | undefined, status: number): string {
  const detail = body?.detail
  if (typeof detail === 'string' && detail) return detail
  if (detail && typeof detail === 'object') {
    const parts = [detail.code, detail.message].filter(
      (part): part is string => typeof part === 'string' && part.length > 0,
    )
    if (parts.length) return parts.join(': ')
  }
  return body?.message || `Request failed (${status})`
}
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

const CSRF_COOKIE = 'vl_csrf'
const CSRF_HEADER = 'X-CSRF-Token'
// /auth/csrf 负责签发令牌,登录自身在服务端按环境判定是否强制,两者都无需预先取令牌
const URL_IS_CSRF_FREE = /^\/auth\/(csrf|login)$/

function readCsrfCookie(): string | null {
  if (typeof document === 'undefined') return null
  const match = document.cookie.split(';').map(part => part.trim()).find(part => part.startsWith(`${CSRF_COOKIE}=`))
  return match ? decodeURIComponent(match.slice(CSRF_COOKIE.length + 1)) : null
}

/** Real HTTP implementation. The mock client remains the default for demo pages. */
export function fetchHttpClient(baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1'): ApiClient {
  const base = baseUrl.replace(/\/$/, '')
  let csrfToken: string | null = null

  async function ensureCsrf(): Promise<void> {
    if (csrfToken) return
    const response = await fetch(`${base}/auth/csrf`, { credentials: 'include', headers: { Accept: 'application/json' } })
    if (response.ok) {
      const body = await response.json() as { csrf_token?: string }
      csrfToken = body.csrf_token ?? readCsrfCookie()
    }
  }

  function isUnsafe(method: string | undefined): boolean {
    return ['POST', 'PUT', 'PATCH', 'DELETE'].includes((method ?? 'GET').toUpperCase())
  }

  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const method = (init.method ?? 'GET').toUpperCase()
    // Cookie 会话的写请求需要双提交 CSRF 令牌;读请求与 Bearer 客户端不需要
    if (isUnsafe(method) && !URL_IS_CSRF_FREE.test(path)) {
      await ensureCsrf()
    }
    const token = getAccessToken()
    const csrf = csrfToken ?? readCsrfCookie()
    const unsafe = isUnsafe(method) && !URL_IS_CSRF_FREE.test(path)
    const response = await fetch(`${base}${path}`, {
      ...init,
      credentials: 'include',
      headers: {
        Accept: 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(unsafe && csrf ? { [CSRF_HEADER]: csrf } : {}),
        ...(init.headers || {}),
      },
    })
    if (!response.ok) {
      let body: ApiErrorBody | undefined
      try { body = await response.json() } catch { /* non-json error */ }
      throw new ApiHttpError(response.status, apiErrorMessage(body, response.status), body)
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
    async health(projectOrId: string, idOrSignal?: string | AbortSignal, maybeSignal?: AbortSignal) {
      const projectId = typeof idOrSignal === 'string' ? projectOrId : 'demo-project'
      const id = typeof idOrSignal === 'string' ? idOrSignal : projectOrId
      const signal = typeof idOrSignal === 'string' ? maybeSignal : idOrSignal
      // POST /datasets/{id}/validate 同时完成校验(批次转入 READY)并返回治理统计。
      // 消费方(导入向导的治理报告)要的是 6 项计数,而服务端把它们放在 preview.stats
      // 里,所以在这里映射一次——否则 mock 与真实各返回一种形状,报告只能靠写死的常量。
      const body = await request<{ preview?: { stats?: Record<string, number> } }>(
        `${project(projectId)}/datasets/${encodeURIComponent(id)}/validate`,
        { method: 'POST', body: '{}', headers: { 'Content-Type': 'application/json' }, signal },
      )
      const stats = body.preview?.stats ?? {}
      return {
        inputRows: stats.total ?? 0,
        validRows: stats.valid ?? 0,
        invalidRows: stats.invalid ?? 0,
        duplicateRows: stats.duplicate ?? 0,
        redactedRows: stats.redacted ?? 0,
        undatedRows: stats.missing_time ?? 0,
      }
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
    async logout() {
      await ensureCsrf()
      const csrf = csrfToken ?? readCsrfCookie()
      await fetch(`${base}/auth/logout`, {
        method: 'POST',
        credentials: 'include',
        headers: { Accept: 'application/json', ...(csrf ? { [CSRF_HEADER]: csrf } : {}) },
      })
    },
    authConfig() {
      return request<AuthConfig>('/auth/config')
    },
    loginWithAssertion(assertion: string) {
      return request<LoginResponse>('/auth/token', {
        method: 'POST', body: JSON.stringify({ assertion }), headers: { 'Content-Type': 'application/json' },
      })
    },
    createExport(projectId: string, body: { scope: string }, idempotencyKey: string) {
      return request<ExportJob>(`${project(projectId)}/exports`, {
        method: 'POST', body: JSON.stringify(body),
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
      })
    },
    async downloadExport(projectId: string, exportId: string) {
      const token = getAccessToken()
      const response = await fetch(
        `${base}${project(projectId)}/exports/${encodeURIComponent(exportId)}/download`,
        { credentials: 'include', headers: { Accept: 'text/csv', ...(token ? { Authorization: `Bearer ${token}` } : {}) } },
      )
      if (!response.ok) {
        // 410 表示导出已过期或失效:提示重新导出,而不是重试旧链接
        throw new ApiHttpError(response.status, response.status === 410 ? 'export_expired' : `Export failed (${response.status})`)
      }
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
    previewDeletion(projectId: string, body: DeletionTarget) {
      return request<DeletionPreview>(`${project(projectId)}/deletions/preview`, {
        method: 'POST', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' },
      })
    },
    executeDeletion(projectId: string, body: DeletionBody, idempotencyKey: string) {
      return request<DeletionReceipt>(`${project(projectId)}/deletions`, {
        method: 'POST', body: JSON.stringify(body),
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
      })
    },
    patchTask(projectId: string, taskId: string, body: TaskPatchBody) {
      return request<TaskSummary>(`${project(projectId)}/tasks/${encodeURIComponent(taskId)}`, {
        method: 'PATCH', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' },
      })
    },
    listMembers(projectId: string, signal?: AbortSignal) {
      return list<ProjectMember>(`${project(projectId)}/members`, signal)
    },
    getSettings(projectId: string, signal?: AbortSignal) {
      return request<ProjectSettings>(`${project(projectId)}/settings`, { signal })
    },
    patchSettings(projectId: string, body: ProjectSettingsPatchBody) {
      return request<ProjectSettings>(`${project(projectId)}/settings`, {
        method: 'PATCH', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' },
      })
    },
    getFeedback(projectId: string, feedbackId: string, signal?: AbortSignal) {
      return request<FeedbackSource>(`${project(projectId)}/feedback/${encodeURIComponent(feedbackId)}`, { signal })
    },
    reviewRisk(projectId: string, riskId: string, body: RiskReviewBody) {
      return request<RiskItem>(`${project(projectId)}/risks/${encodeURIComponent(riskId)}/reviews`, {
        method: 'POST', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' },
      })
    },
    getTopicDetail(projectId: string, topicId: string, topicVersionId?: number, signal?: AbortSignal) {
      const query = topicVersionId === undefined ? '' : `?topic_version_id=${topicVersionId}`
      return request<TopicDetailResponse>(`${project(projectId)}/topics/${encodeURIComponent(topicId)}${query}`, { signal })
    },
    correctTopic(projectId: string, topicId: string, body: CorrectionBody) {
      return request<{ revision: number; affected_topic_ids: string[] }>(
        `${project(projectId)}/topics/${encodeURIComponent(topicId)}/corrections`,
        { method: 'POST', body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } },
      )
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
