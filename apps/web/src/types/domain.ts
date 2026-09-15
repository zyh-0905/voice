export interface DatasetPreview {
  id: string
  name: string
  rows: number
  status: string
  hasTime: boolean
  /** 来源列名(脱敏预览的表头)。向导据此渲染映射步骤——此前那一屏是写死的三列。 */
  headers: string[]
  /** 上传时的脱敏预览行(最多 20 行,4.3) */
  rows_preview: DatasetRow[]
  /** XLSX 的全部工作表名;单表或非 XLSX 时为空 */
  sheetNames: string[]
  /** 当前选中的工作表(4.3) */
  sheetName: string | null
}

/** 工程计划 4.2 的标准反馈字段:映射目标只能是它们 */
export type StandardField = 'feedback_id' | 'content' | 'created_at' | 'channel'
  | 'product' | 'rating' | 'order_id' | 'order_ref' | 'status'

export type DatasetRow = Record<string, string>

/** 治理请求:§4.3 的映射、工作表、时区与时间策略都要送到服务端。
 *
 * 此前向导发的是空对象,于是四个选项在真实与 mock 两种模式下都不生效。 */
export interface ValidateBody {
  mapping?: Record<string, string>
  sheet_name?: string
  time_policy?: 'strict' | 'static'
  timezone?: string
}
export interface ImportHealth {
  completeness: number
  piiMasked: boolean
  timeFieldMissing: number
}
/** 工程计划 W05:上传→治理→分析后由服务端返回的批次健康视图 */
export interface ImportHealthView {
  inputRows: number
  validRows: number
  invalidRows: number
  duplicateRows: number
  redactedRows: number
  undatedRows: number
}
/** worker.py 的状态机:queued→running→done/error,cancel 可落在任一非终态。 */
export type AnalysisRunStatus = 'queued' | 'running' | 'done' | 'error' | 'cancelled'

/** 轮询只在非终态继续;终态必须停下来,否则页面会一直打后端。 */
export const TERMINAL_RUN_STATUSES: readonly AnalysisRunStatus[] = ['done', 'error', 'cancelled']

export interface AnalysisRun {
  id: string
  status: AnalysisRunStatus
  /** 服务端阶段名(analyzing/completed/…),仅用于展示细粒度文案 */
  stage?: string
  /** 本次 run 冻结的反馈条数(5.3「输入固定」),进度分母 */
  total?: number
  progress?: number
  error?: string
  /** 创建时冻结的批次;刷新后据此把 URL 里的 dataset 认回它对应的 run */
  dataset_ids?: string[]
}

// —— 工程计划 7.7:行动首页只读聚合契约 ——

export interface SummaryFilters {
  start: string | null
  end: string | null
  channel: string | null
  product: string | null
}

export interface InsightMetrics {
  scope: 'selected_analysis'
  valid_feedback_count: number | null
  topic_count: number | null
  pending_risk_feedback_count: number | null
}

export interface ActionMetrics {
  scope: 'project_all_runs'
  active_task_count: number
  overdue_task_count: number
  task_as_of: string
}

export interface SummaryResponse {
  project_id: string
  run_id: string | null
  revision: number | null
  denominator: number | null
  definition_version: string
  computed_at: string
  filters: SummaryFilters
  insight_metrics: InsightMetrics
  action_metrics: ActionMetrics
}

// —— 主题表与证据 ——

export type TopicTrend = 'up' | 'down' | 'flat' | 'new' | null
export type TopicReviewState = 'pending' | 'confirmed' | 'excluded'

export interface EvidenceQuoteItem {
  feedbackId: string
  /** 脱敏原文 */
  text: string
  /** Unicode 字符 offset(非 UTF-16 code unit) */
  start: number
  end: number
  channel: string | null
  occurredAt: string | null
  rowIndex: number | null
}

export interface CpiComponent {
  label: string
  displayValue: string
  coverage: number | null
}

export interface CpiResult {
  display_value: string
  components: CpiComponent[]
  coverage: number | null
  provisional: boolean
}

export type AiOrigin = 'ai' | 'rule' | 'human' | 'unknown'

export interface AiProvenance {
  origin: AiOrigin
  needsReview: boolean
  reviewRecord: { reviewer: string; reviewedAt: string } | null
}

export interface EvidenceContext {
  topicId: string
  topicTitle: string
  runId: string
  revision: number
  summary: string
  cpi: CpiResult | null
  quotes: EvidenceQuoteItem[]
  aiProvenance: AiProvenance
}

export interface TopicRow {
  id: string
  title: string
  feedbackCount: number
  denominator: number
  /** 占有效反馈比例(0-100);多标签主题可合计超过 100 */
  ratio: number
  trend: TopicTrend
  cpiDisplayValue: string | null
  reviewState: TopicReviewState
  evidence: EvidenceContext
  /** 该主题当前 revision 的版本行 id(7.5 复盘契约的 topic_version_ids 来源);演示回退行可能缺省 */
  versionId?: string | null
}

// —— 趋势、待办与批次 ——

export interface TrendPoint {
  date: string
  value: number | null
}

export type TaskStatus = 'DRAFT' | 'OPEN' | 'IN_PROGRESS' | 'PENDING_REVIEW' | 'CLOSED' | 'CANCELLED'

export interface TaskSummary {
  id: string
  title: string
  status: TaskStatus
  dueAt: string | null
  overdue: boolean
  /** 真实 /tasks 契约扩展字段(演示数据同源) */
  owner?: string
  priority?: string
  source?: string
}

/** 复盘度量(W17 契约):百分点差值而非百分比混用;分母为 0 不可比 */
export interface ReviewMetrics {
  count_change: number | null
  share_before_pp: number | null
  share_after_pp: number | null
  share_delta_pp: number | null
  relative_share_change: number | null
  comparable: boolean
}

/** 复盘可比性(计划 7.5):ok 可比;insufficient 不可比;low_sample 保留数量但不给结论 */
export type ReviewComparability = 'ok' | 'insufficient' | 'low_sample'

/** 复盘的单个窗口:边界 + 服务端推导的 n/N + 无法确定发生时间的行数;半开区间 [start, end) */
export interface ReviewWindow {
  start: string
  end: string
  n: number
  N: number
  untimed: number
}

/** 复盘记录(GET /reviews/{r}):固定统计结果 + 分母 + 版本 + 可比性与原因;
 *  不可比时 metrics 为 null,不得回退展示任何变化数字。 */
export interface ReviewRecord {
  id: string
  project_id: string
  run_id: string
  revision: number
  topic_version_ids: string[]
  task_id: string | null
  before: ReviewWindow
  after: ReviewWindow
  filters: Record<string, string | null>
  alignment_confirmed: boolean
  metrics: ReviewMetrics | null
  comparability: ReviewComparability
  reasons: string[]
  effect_status: 'INSUFFICIENT_DATA' | 'OBSERVED_CHANGE'
  limitations: string[]
}

/** 任务事件(状态机流转记录,W15 契约;5.2 起落在 task_events 表里)。
 *
 * `from_state` 是 5.2 新增的:JSON 版本只记目标状态,时间线看着能猜改之前是什么,
 * 但猜不出——而那正是时间线的价值所在。
 */
export interface TaskEvent {
  action: string
  from_state: TaskStatus
  to_state: TaskStatus
  actor_id?: string | null
  comment_redacted?: string | null
  created_at?: string | null
}

/** 任务详情(GET /tasks/{t}):task + 来源快照 + 事件 + 版本 */
export interface TaskDetail {
  task: TaskSummary & {
    owner_id?: string | null
    acceptance?: string | null
    effect_status?: string
    events?: TaskEvent[]
  }
  /** 来源**指针**:主题版本 id 或 'manual'。不是快照——指针在源数据被删后就悬空了。 */
  source: string | null
  /** 固定的来源证据快照(5.2 的 task_evidence):创建任务时复制,不随源数据变化 */
  evidence_snapshot: TaskEvidenceSnapshot[]
  events: TaskEvent[]
  version: number
}

/** 风险队列:规则命中候选,severity 与复核状态分开;候选不是已确认事故 */
export interface RiskItem {
  id: string
  title: string
  rule: string
  severity: string
  reviewState: 'pending' | 'confirmed' | 'excluded'
  status: string
  /** 乐观锁版本(6.5):裁决必须带上,服务端按此条件更新;缺失即 422 */
  version: number
}

export interface DatasetBatch {
  id: string
  name: string
  rows: number
  status: string
  createdAt: string
}

/** 任务的固定来源证据快照;删源数据时会被一并清理(10.4)。 */
export interface TaskEvidenceSnapshot {
  feedback_id: string
  topic_version_id: string | null
  quote_redacted: string
}
