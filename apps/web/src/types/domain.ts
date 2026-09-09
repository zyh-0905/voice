export interface DatasetPreview {
  id: string
  name: string
  rows: number
  status: string
  hasTime: boolean
}
export interface ImportHealth {
  completeness: number
  piiMasked: boolean
  timeFieldMissing: number
}
export interface AnalysisRun {
  id: string
  status: 'queued' | 'running' | 'done' | 'error'
  total?: number
  progress?: number
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
}

export interface DatasetBatch {
  id: string
  name: string
  rows: number
  status: string
  createdAt: string
}
