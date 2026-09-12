import {
  ApiHttpError,
  type ApiClient,
  type CorrectionBody,
  type DeletionBody,
  type DeletionTarget,
  type ReviewCreateBody,
  type ReviewWindowInput,
  type RiskReviewBody,
  type TaskConfirmBody,
  type TaskPatchBody,
  type TaskTransitionBody,
  type TopicDetailResponse,
  type ProjectMember,
  type ProjectSettings,
  type ProjectSettingsPatchBody,
} from './client'
import type {
  AiProvenance,
  CpiResult,
  DatasetBatch,
  DatasetPreview,
  EvidenceContext,
  EvidenceQuoteItem,
  ReviewComparability,
  ReviewMetrics,
  ReviewRecord,
  ReviewWindow,
  RiskItem,
  SummaryResponse,
  TaskEvent,
  TaskStatus,
  TaskSummary,
  TopicRow,
  TrendPoint,
} from '../types/domain'

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

/** Deterministic demo client. Supports legacy `upload(file)` and project-scoped `upload(projectId, file)`. */
async function uploadMock(projectOrFile: string | File, fileOrSignal?: File | AbortSignal, _maybeSignal?: AbortSignal): Promise<DatasetPreview> {
  await delay(300)
  const file = typeof projectOrFile === 'string' && fileOrSignal instanceof File ? fileOrSignal : projectOrFile
  const name = typeof file === 'string' ? file : file.name
  return { id: 'demo-1', name, rows: 1248, status: 'ready', hasTime: false }
}

// —— 合成 UI 契约样例(工程计划 7.7 自带样例):仅用于 UI 演示,
// 常显 DemoNotice,不代表任何真实业务结果。后端 /summary 实现后替换。 ——
const SYNTHETIC_SUMMARY: SummaryResponse = {
  project_id: 'demo-project',
  run_id: 'run_demo_001',
  revision: 1,
  denominator: 1000,
  definition_version: 'summary-ui-v1',
  computed_at: '2026-09-09T00:00:00+08:00',
  filters: { start: '2026-08-25T00:00:00+08:00', end: '2026-09-01T00:00:00+08:00', channel: null, product: null },
  insight_metrics: { scope: 'selected_analysis', valid_feedback_count: 1000, topic_count: 8, pending_risk_feedback_count: 12 },
  action_metrics: { scope: 'project_all_runs', active_task_count: 18, overdue_task_count: 4, task_as_of: '2026-09-09T00:00:00+08:00' },
}

function cpi(display: string, provisional = false): CpiResult {
  return {
    display_value: display,
    components: [
      { label: '数量变化', displayValue: display, coverage: 100 },
      { label: '严重度构成', displayValue: provisional ? '暂定' : display, coverage: provisional ? null : 100 },
    ],
    coverage: provisional ? null : 100,
    provisional,
  }
}

function quote(
  feedbackId: string,
  text: string,
  start: number,
  end: number,
  channel: string,
  occurredAt: string,
  rowIndex: number,
): EvidenceQuoteItem {
  return { feedbackId, text, start, end, channel, occurredAt, rowIndex }
}

function provenance(origin: AiProvenance['origin'], needsReview: boolean, reviewer: string | null): AiProvenance {
  return {
    origin,
    needsReview,
    reviewRecord: reviewer ? { reviewer, reviewedAt: '2026-09-08T10:00:00+08:00' } : null,
  }
}

interface SyntheticTopic {
  id: string
  title: string
  feedbackCount: number
  ratio: number
  trend: TopicRow['trend']
  cpiDisplayValue: string | null
  reviewState: TopicRow['reviewState']
  summary: string
  quote: EvidenceQuoteItem
  provenance: AiProvenance
}

// 前 3 条沿用原 demoAnalysis 的物流/退款/产品主题(合成样本);其余为补充合成主题。
const SYNTHETIC_TOPICS: SyntheticTopic[] = [
  {
    id: 'delivery', title: '物流体验', feedbackCount: 218, ratio: 21.8, trend: 'down', cpiDisplayValue: '68', reviewState: 'confirmed',
    summary: '配送等待与物流信息更新是主要关注点。',
    quote: quote('fb_demo_001', '合成样本 DEMO-001:包裹等待了三天,物流信息一直没有更新。', 14, 32, '在线客服', '2026-08-26T09:12:00+08:00', 12),
    provenance: provenance('ai', false, 'demo-user'),
  },
  {
    id: 'refund', title: '退款进度', feedbackCount: 164, ratio: 16.4, trend: 'up', cpiDisplayValue: '82', reviewState: 'pending',
    summary: '反馈关注退款处理时间和状态透明度。',
    quote: quote('fb_demo_002', '合成样本 DEMO-002:申请退款后,希望能看到预计到账时间。', 14, 31, '电话', '2026-08-27T14:30:00+08:00', 37),
    provenance: provenance('ai', true, null),
  },
  {
    id: 'product', title: '产品使用', feedbackCount: 121, ratio: 12.1, trend: 'flat', cpiDisplayValue: '54', reviewState: 'pending',
    summary: '使用引导与功能说明仍有改善空间。',
    quote: quote('fb_demo_003', '合成样本 DEMO-003:第一次使用时没有找到操作说明。', 14, 28, '邮件', '2026-08-28T11:05:00+08:00', 58),
    provenance: provenance('rule', true, null),
  },
  {
    id: 'support', title: '客服响应', feedbackCount: 96, ratio: 9.6, trend: 'up', cpiDisplayValue: '77', reviewState: 'pending',
    summary: '响应速度与问题一次解决率受到关注。',
    quote: quote('fb_demo_004', '合成样本 DEMO-004:排队等待时间较长,转接后问题得到解决。', 14, 28, '在线客服', '2026-08-29T16:40:00+08:00', 81),
    provenance: provenance('ai', true, null),
  },
  {
    id: 'billing', title: '价格与账单', feedbackCount: 87, ratio: 8.7, trend: 'flat', cpiDisplayValue: '61', reviewState: 'confirmed',
    summary: '账单明细与扣费说明需要更清晰。',
    quote: quote('fb_demo_005', '合成样本 DEMO-005:账单金额与预期不符,希望展示明细。', 14, 28, '邮件', '2026-08-30T10:20:00+08:00', 104),
    provenance: provenance('human', false, 'demo-user'),
  },
  {
    id: 'stability', title: '应用稳定性', feedbackCount: 62, ratio: 6.2, trend: 'down', cpiDisplayValue: '73', reviewState: 'pending',
    summary: '闪退与加载失败集中在特定版本。',
    quote: quote('fb_demo_006', '合成样本 DEMO-006:打开应用时出现闪退,重装后恢复。', 14, 26, '在线客服', '2026-08-31T13:15:00+08:00', 129),
    provenance: provenance('ai', true, null),
  },
  {
    id: 'account', title: '账号与登录', feedbackCount: 41, ratio: 4.1, trend: 'new', cpiDisplayValue: null, reviewState: 'pending',
    summary: '新主题,样本较少,待进一步归类。',
    quote: quote('fb_demo_007', '合成样本 DEMO-007:更换手机号后无法登录原有账号。', 14, 26, '电话', '2026-09-01T09:50:00+08:00', 142),
    provenance: provenance('unknown', true, null),
  },
  {
    id: 'unclassified', title: '待归类', feedbackCount: 33, ratio: 3.3, trend: null, cpiDisplayValue: null, reviewState: 'pending',
    summary: '暂未归入已有主题的反馈,保留原文可查看。',
    quote: quote('fb_demo_008', '合成样本 DEMO-008:希望有更多配送方式可以选择。', 14, 24, '在线客服', '2026-09-01T18:25:00+08:00', 160),
    provenance: provenance('rule', true, null),
  },
]

function topicRow(topic: SyntheticTopic): TopicRow {
  const evidence: EvidenceContext = {
    topicId: topic.id,
    topicTitle: topic.title,
    runId: 'run_demo_001',
    revision: 1,
    summary: topic.summary,
    cpi: topic.cpiDisplayValue === null ? null : cpi(topic.cpiDisplayValue, topic.reviewState === 'pending'),
    quotes: [topic.quote],
    aiProvenance: topic.provenance,
  }
  return {
    id: topic.id,
    title: topic.title,
    feedbackCount: topic.feedbackCount,
    denominator: SYNTHETIC_SUMMARY.denominator ?? 1000,
    ratio: topic.ratio,
    trend: topic.trend,
    cpiDisplayValue: topic.cpiDisplayValue,
    reviewState: topic.reviewState,
    evidence,
  }
}

const SYNTHETIC_TREND: TrendPoint[] = [
  { date: '08-26', value: 142 },
  { date: '08-27', value: 151 },
  { date: '08-28', value: null },
  { date: '08-29', value: 158 },
  { date: '08-30', value: 149 },
  { date: '08-31', value: 161 },
  { date: '09-01', value: 155 },
]

const SYNTHETIC_TASKS: TaskSummary[] = [
  { id: 'task-001', title: '退款率异常整改', status: 'IN_PROGRESS', dueAt: '2026-09-08T18:00:00+08:00', overdue: true, owner: '数据团队', priority: 'HIGH', source: '关联风险 R-204' },
  { id: 'task-002', title: '支付失败率复盘', status: 'OPEN', dueAt: '2026-09-15T18:00:00+08:00', overdue: false, owner: '运营团队', priority: 'CRITICAL', source: '关联风险 R-302' },
  { id: 'task-003', title: '字段治理复核', status: 'PENDING_REVIEW', dueAt: '2026-09-20T18:00:00+08:00', overdue: false, owner: '运营团队', priority: 'MEDIUM', source: '关联风险 R-101' },
]

const SYNTHETIC_RISKS: RiskItem[] = [
  { id: 'risk-001', title: '退款率异常', rule: 'R-204 · 近30天', severity: 'HIGH', reviewState: 'pending', status: 'OPEN' },
  { id: 'risk-002', title: '支付失败率突增', rule: 'R-302 · 近24小时', severity: 'CRITICAL', reviewState: 'pending', status: 'OPEN' },
  { id: 'risk-003', title: '订单金额缺失', rule: 'R-101 · 完整性', severity: 'MEDIUM', reviewState: 'confirmed', status: 'IN_PROGRESS' },
]

/** W16 合成项目成员:派发任务的负责人只能来自成员接口;owner-1 沿用既有 E2E 流程。 */
const SYNTHETIC_MEMBERS: ProjectMember[] = [
  { id: 'owner-1', display_name: 'Demo Analyst', role: 'OWNER' },
  { id: 'viewer-1', display_name: 'Demo Viewer', role: 'VIEWER' },
]

function defaultProjectSettings(): ProjectSettings {
  return {
    timezone: 'UTC',
    limits: { max_feedback_rows: 5000, max_upload_bytes: 50 * 1024 * 1024 },
    rules: { min_severity: 'LOW', scan_on_import: true },
    model_available: true,
    version: 1,
  }
}

/** 演示项目设置:默认值与后端 W03 一致;expected_version 过期抛 409 VERSION_CONFLICT。 */
class MockSettingsStore {
  private settings = defaultProjectSettings()

  get(): ProjectSettings {
    return { ...this.settings, limits: { ...this.settings.limits }, rules: { ...this.settings.rules } }
  }

  patch(body: ProjectSettingsPatchBody): ProjectSettings {
    if (Number(body.expected_version) !== this.settings.version) throw new ApiHttpError(409, 'VERSION_CONFLICT')
    const hasChanges = [body.timezone, body.limits, body.rules, body.model_available].some(value => value !== undefined)
    if (!hasChanges) throw new ApiHttpError(422, 'no_fields')
    if (body.timezone !== undefined) this.settings.timezone = body.timezone
    if (body.limits !== undefined) this.settings.limits = { ...body.limits }
    if (body.rules !== undefined) this.settings.rules = { ...body.rules }
    if (body.model_available !== undefined) this.settings.model_available = body.model_available
    this.settings.version += 1
    return this.get()
  }

  reset() {
    this.settings = defaultProjectSettings()
  }
}

const MOCK_SETTINGS_STORE = new MockSettingsStore()

/** 演示任务状态机:与后端 W15 语义一致(草稿不能直接验收、负责人不得自验收、幂等确认)。 */
class MockTaskStore {
  private tasks = new Map<string, TaskSummary & { owner_id?: string | null; acceptance?: string | null; effect_status?: string; events?: TaskEvent[] }>()
  private keys = new Set<string>()
  private seeded = false

  private seed() {
    if (this.seeded) return
    this.seeded = true
    for (const task of SYNTHETIC_TASKS) {
      this.tasks.set(task.id, { ...task, version: 1, events: [] } as never)
    }
  }

  list(): TaskSummary[] {
    this.seed()
    return [...this.tasks.values()].map(t => ({ ...t }))
  }

  detail(taskId: string) {
    this.seed()
    const task = this.tasks.get(taskId)
    if (!task) throw new ApiHttpError(404, 'task_not_found')
    return { task: { ...task }, source_snapshot: task.source ?? null, events: [...(task.events ?? [])], version: Number((task as never as { version: number }).version ?? 1) }
  }

  create(title: string, sourceTopicVersionId: string | null): TaskSummary {
    this.seed()
    const id = `task-draft-${Date.now()}`
    const task = { id, title, status: 'DRAFT' as TaskStatus, dueAt: null, overdue: false, owner: '待分配', priority: 'MEDIUM', source: sourceTopicVersionId ?? '人工创建', version: 1, events: [] }
    this.tasks.set(id, task as never)
    return { ...task }
  }

  private require(taskId: string) {
    this.seed()
    const task = this.tasks.get(taskId)
    if (!task) throw new ApiHttpError(404, 'task_not_found')
    return task
  }

  confirm(taskId: string, body: TaskConfirmBody, idempotencyKey: string) {
    const task = this.require(taskId)
    if (idempotencyKey && this.keys.has(`${taskId}:${idempotencyKey}`)) return { ...task }
    if (task.status !== 'DRAFT') throw new ApiHttpError(409, 'INVALID_TRANSITION')
    if (Number((task as never as { version: number }).version) !== body.expected_version) {
      throw new ApiHttpError(409, 'VERSION_CONFLICT')
    }
    if (!body.owner_id.trim()) throw new ApiHttpError(422, 'field_required')
    if (!body.due_at.trim()) throw new ApiHttpError(422, 'field_required')
    if (!body.acceptance.trim()) throw new ApiHttpError(422, 'field_required')
    Object.assign(task, { status: 'OPEN', owner: body.owner_id, dueAt: body.due_at, acceptance: body.acceptance })
    this.bump(task, 'confirm', '已派发,等待执行')
    if (idempotencyKey) this.keys.add(`${taskId}:${idempotencyKey}`)
    return { ...task }
  }

  patch(taskId: string, body: TaskPatchBody): TaskSummary {
    const task = this.require(taskId)
    const record = task as never as { version: number; state?: string }
    if (body.expected_version !== Number(record.version)) throw new ApiHttpError(409, 'VERSION_CONFLICT')
    const editable = (record.state ?? 'DRAFT') === 'DRAFT'
      ? ['title', 'source', 'priority']
      : ['due_at', 'acceptance', 'priority']
    const changes = Object.entries(body).filter(([key]) => !['expected_version'].includes(key))
    if (!changes.length) throw new ApiHttpError(422, 'no_fields')
    const disallowed = changes.filter(([key]) => !editable.includes(key)).map(([key]) => key)
    if (disallowed.length) throw new ApiHttpError(422, 'field_not_editable')
    for (const [key, value] of changes) {
      if (key === 'due_at') task.dueAt = value as string
      else if (key === 'acceptance') (task as never as { acceptance?: string }).acceptance = value as string
      else (task as never as Record<string, unknown>)[key] = value
    }
    ;(task as never as { version: number }).version = Number(record.version) + 1
    return { ...task }
  }

  transition(taskId: string, body: TaskTransitionBody, idempotencyKey: string) {
    const task = this.require(taskId)
    if (idempotencyKey && this.keys.has(`${taskId}:${idempotencyKey}`)) return { ...task }
    if (Number((task as never as { version: number }).version) !== body.expected_version) {
      throw new ApiHttpError(409, 'VERSION_CONFLICT')
    }
    const allowed: Record<string, Partial<Record<TaskTransitionBody['action'], TaskStatus>>> = {
      OPEN: { start: 'IN_PROGRESS', cancel: 'CANCELLED' },
      IN_PROGRESS: { submit: 'PENDING_REVIEW', cancel: 'CANCELLED' },
      PENDING_REVIEW: { approve: 'CLOSED', reject: 'IN_PROGRESS', cancel: 'CANCELLED' },
      DRAFT: { cancel: 'CANCELLED' },
    }
    const next = allowed[task.status]?.[body.action]
    if (!next) throw new ApiHttpError(409, 'INVALID_TRANSITION')
    task.status = next
    this.bump(task, body.action, body.comment)
    if (idempotencyKey) this.keys.add(`${taskId}:${idempotencyKey}`)
    return { ...task }
  }

  private bump(task: TaskSummary, action: string, comment: string) {
    const record = task as never as { version: number; events: TaskEvent[]; effect_status?: string }
    record.version = Number(record.version) + 1
    record.events = [...(record.events ?? []), { action, actor: 'demo-user', comment, state: task.status }]
    // 关闭任务不自动宣称经营效果改善
    if (task.status === 'CLOSED') record.effect_status = 'NOT_EVALUATED'
  }

  reset() {
    this.seeded = false
    this.tasks.clear()
    this.keys.clear()
  }
}

/** 演示风险裁决:与后端 W14 一致——理由必填、版本冲突、确认不等于事故发生。 */
class MockRiskStore {
  private risks = new Map<string, RiskItem & { version?: number; reviewedBy?: string; reviewReason?: string }>()
  private seeded = false

  private seed() {
    if (this.seeded) return
    this.seeded = true
    for (const risk of SYNTHETIC_RISKS) this.risks.set(risk.id, { ...risk, version: 1 })
  }

  list(): RiskItem[] {
    this.seed()
    return [...this.risks.values()].map(r => ({ ...r }))
  }

  review(riskId: string, body: RiskReviewBody): RiskItem {
    this.seed()
    const risk = this.risks.get(riskId)
    if (!risk) throw new ApiHttpError(404, 'risk_not_found')
    if (!body.reason.trim()) throw new ApiHttpError(422, 'reason_required')
    const version = risk.version ?? 1
    if (body.expected_version !== undefined && body.expected_version !== version) {
      throw new ApiHttpError(409, 'VERSION_CONFLICT')
    }
    const next = body.decision === 'confirmed' ? 'confirmed' : body.decision === 'excluded' ? 'excluded' : 'pending'
    Object.assign(risk, {
      reviewState: next,
      status: next === 'confirmed' ? 'OPEN' : next === 'excluded' ? 'CLOSED' : risk.status,
      version: version + 1,
      reviewedBy: 'demo-user',
      reviewReason: body.reason.trim(),
    })
    return { ...risk }
  }

  reset() {
    this.seeded = false
    this.risks.clear()
  }
}

const MOCK_RISK_STORE = new MockRiskStore()

const MOCK_TASK_STORE = new MockTaskStore()

/** 演示 run 与可识别主题:窗口外的一切按服务端口径拒绝或标记不可比 */
const MOCK_RUN_REVISION = 1
const MOCK_KNOWN_RUNS = new Set(['run_demo_001'])
const MOCK_TOPIC_IDS = new Set(['delivery', 'refund', 'product', 't1'])
/** 演示口径:窗口每持续一天记 30 条反馈,前后窗口占比固定 */
const MOCK_ROWS_PER_DAY = 30

/** 与后端 W17 同口径:占比为百分点,零分母不输出任何变化结论。 */
function compareCounts(before: ReviewWindow, after: ReviewWindow): ReviewMetrics {
  if (before.N <= 0 || after.N <= 0) {
    return {
      count_change: after.n - before.n, share_before_pp: null, share_after_pp: null,
      share_delta_pp: null, relative_share_change: null, comparable: false,
    }
  }
  const shareBefore = (before.n / before.N) * 100
  const shareAfter = (after.n / after.N) * 100
  const deltaPp = shareAfter - shareBefore
  const relative = shareBefore > 0 ? deltaPp / shareBefore : null
  return {
    count_change: after.n - before.n,
    share_before_pp: Math.round(shareBefore * 100) / 100,
    share_after_pp: Math.round(shareAfter * 100) / 100,
    share_delta_pp: Math.round(deltaPp * 100) / 100,
    relative_share_change: relative === null ? null : Math.round(relative * 10000) / 10000,
    comparable: true,
  }
}

/** 两窗之间的可比性理由,与后端 reviews.py 的 _window_reasons 文案一致 */
function windowReasons(before: ReviewWindow, after: ReviewWindow): string[] {
  const bStart = Date.parse(before.start), bEnd = Date.parse(before.end)
  const aStart = Date.parse(after.start), aEnd = Date.parse(after.end)
  if ([bStart, bEnd, aStart, aEnd].some(Number.isNaN)) return ['窗口时间无法解析']
  if (!(bStart < bEnd) || !(aStart < aEnd)) return ['窗口起点必须早于终点']
  const reasons: string[] = []
  if (bEnd - bStart !== aEnd - aStart) reasons.push('前后窗口时长不等')
  if (bStart < aEnd && aStart < bEnd) reasons.push('前后窗口重叠')
  return reasons
}

/** 演示复盘:口径由窗口推导(等长且不重叠才可能可比),低样本保留数量但不给结论。 */
class MockReviewStore {
  private reviews = new Map<string, ReviewRecord>()
  private seeded = false

  private seed() {
    if (this.seeded) return
    this.seeded = true
    const before: ReviewWindow = { start: '2026-08-01T00:00:00+00:00', end: '2026-08-31T00:00:00+00:00', n: 168, N: 1000, untimed: 0 }
    const after: ReviewWindow = { start: '2026-09-01T00:00:00+00:00', end: '2026-10-01T00:00:00+00:00', n: 102, N: 1000, untimed: 0 }
    this.reviews.set('review-001', this.record('review-001', before, after, {
      topicVersionIds: ['t1'], alignmentConfirmed: true, comparability: 'ok', reasons: [],
    }))
    this.reviews.set('review-002', this.record(
      'review-002', before, { ...after, n: 80, N: 500 },
      { topicVersionIds: ['t1'], alignmentConfirmed: true, comparability: 'ok', reasons: [] },
    ))
    this.reviews.set('review-003', this.record(
      'review-003', { ...before, n: 0, N: 0 }, { ...after, n: 12, N: 400 },
      { topicVersionIds: ['t1'], alignmentConfirmed: true, comparability: 'insufficient', reasons: ['窗口内无可比数据(分母为 0)'] },
    ))
  }

  private record(
    id: string, before: ReviewWindow, after: ReviewWindow,
    spec: { topicVersionIds: string[]; alignmentConfirmed: boolean; comparability: ReviewComparability; reasons: string[] },
  ): ReviewRecord {
    // 与后端一致:只要不可比,metrics 即为 null,页面不得回退展示变化数字
    const metrics = spec.comparability === 'insufficient' ? null : compareCounts(before, after)
    return {
      id, project_id: 'demo-project', run_id: 'run_demo_001', revision: MOCK_RUN_REVISION,
      topic_version_ids: spec.topicVersionIds, task_id: null,
      before, after, filters: {}, alignment_confirmed: spec.alignmentConfirmed,
      metrics,
      comparability: spec.comparability,
      reasons: [...spec.reasons],
      effect_status: spec.comparability === 'ok' ? 'OBSERVED_CHANGE' : 'INSUFFICIENT_DATA',
      limitations: spec.reasons.length ? [...spec.reasons] : ['变化是观察到的,不构成因果证明'],
    }
  }

  /** 演示数据没有真实行集:用窗口时长推导 N,再用固定占比推导 n */
  private queryWindow(spec: ReviewWindowInput, share: number): ReviewWindow {
    const start = Date.parse(spec.start), end = Date.parse(spec.end)
    if (Number.isNaN(start) || Number.isNaN(end) || start >= end) {
      return { start: spec.start, end: spec.end, n: 0, N: 0, untimed: 0 }
    }
    const days = (end - start) / 86_400_000
    const N = Math.round(days * MOCK_ROWS_PER_DAY)
    return { start: spec.start, end: spec.end, n: Math.round(N * share), N, untimed: 0 }
  }

  list(): ReviewRecord[] {
    this.seed()
    return [...this.reviews.values()].map(r => ({ ...r }))
  }

  find(id: string): ReviewRecord | undefined {
    this.seed()
    const review = this.reviews.get(id)
    return review ? { ...review } : undefined
  }

  create(body: ReviewCreateBody): ReviewRecord {
    this.seed()
    if (!MOCK_KNOWN_RUNS.has(body.run_id)) throw new ApiHttpError(404, 'analysis_not_found')
    const before = this.queryWindow(body.before, 0.168)
    const after = this.queryWindow(body.after, 0.102)
    const reasons: string[] = []
    if (body.revision !== MOCK_RUN_REVISION) reasons.push(`版本不一致:请求 ${body.revision},当前 ${MOCK_RUN_REVISION}`)
    const unknown = body.topic_version_ids.filter(id => !MOCK_TOPIC_IDS.has(id))
    if (unknown.length) reasons.push(`目标主题不属于该 revision: ${unknown.join(', ')}`)
    reasons.push(...windowReasons(before, after))
    if (!body.alignment_confirmed) reasons.push('目标映射尚未人工确认')
    if (!reasons.length && (before.N === 0 || after.N === 0)) reasons.push('窗口内无可比数据(分母为 0)')
    const comparability: ReviewComparability = reasons.length
      ? 'insufficient'
      : before.N < 50 || after.N < 50 ? 'low_sample' : 'ok'
    if (comparability === 'low_sample') reasons.push('样本量不足(<50),不输出变化结论')
    const id = `review-${Date.now()}`
    const review = this.record(id, before, after, {
      topicVersionIds: [...body.topic_version_ids],
      alignmentConfirmed: body.alignment_confirmed,
      comparability,
      reasons,
    })
    this.reviews.set(id, review)
    return { ...review }
  }

  reset() {
    this.seeded = false
    this.reviews.clear()
  }
}

const MOCK_REVIEW_STORE = new MockReviewStore()

/** 演示主题校正:与后端 W13 一致——乐观锁 409、旧版本保留可按版本查询、新版本标待确认。 */
class MockCorrectionStore {
  private revision = 1
  private history = new Map<number, { topics: Array<Record<string, unknown>>; evidence: Record<string, Array<Record<string, unknown>>> }>()
  private topics: Array<Record<string, unknown>> = []
  private evidence: Record<string, Array<Record<string, unknown>>> = {}
  private seeded = false

  private seed() {
    if (this.seeded) return
    this.seeded = true
    for (const topic of SYNTHETIC_TOPICS.slice(0, 3)) {
      this.topics.push({
        topic_id: topic.id, name: topic.title, summary: topic.summary,
        severity: 'medium', feedback_count: topic.feedbackCount, summary_revalidated: true,
      })
      this.evidence[topic.id] = [
        { feedback_id: topic.quote.feedbackId, source_row: topic.quote.rowIndex ?? 0, quote: topic.quote.text.slice(0, 24), quote_start: 0, quote_end: 24 },
      ]
    }
    // 待归类反馈可供 CREATE
    this.evidence['__unassigned__'] = [
      { feedback_id: 'fb_demo_008', source_row: 160, quote: '合成样本 DEMO-008', quote_start: 0, quote_end: 12 },
    ]
  }

  private snapshot() {
    return {
      topics: this.topics.map(t => ({ ...t })),
      evidence: Object.fromEntries(Object.entries(this.evidence).map(([k, v]) => [k, v.map(e => ({ ...e }))])),
    }
  }

  detail(topicId: string, topicVersionId?: number) {
    this.seed()
    const revision = topicVersionId ?? this.revision
    const state = revision === this.revision ? this.snapshot() : this.history.get(revision)
    if (!state) throw new ApiHttpError(404, 'topic_not_found')
    const topic = state.topics.find(t => t.topic_id === topicId)
    if (!topic) throw new ApiHttpError(404, 'topic_not_found')
    return { topic, evidence: state.evidence[topicId] ?? [], revision }
  }

  correct(topicId: string, body: CorrectionBody) {
    this.seed()
    if (!body.reason?.trim()) throw new ApiHttpError(422, 'reason_required')
    if (body.expected_revision !== this.revision) throw new ApiHttpError(409, 'correction_conflict')
    const affected: string[] = []
    const target = this.topics.find(t => t.topic_id === topicId)
    if (!target) throw new ApiHttpError(404, 'topic_not_found')

    if (body.operation === 'RENAME') {
      if (!body.name?.trim()) throw new ApiHttpError(422, 'name_required')
      target.name = body.name
      target.summary_revalidated = false
      affected.push(topicId)
    } else if (body.operation === 'MERGE') {
      const sources = body.source_topic_ids ?? []
      if (new Set(sources).size < 2) throw new ApiHttpError(422, 'merge_requires_two')
      const merged: Array<Record<string, unknown>> = []
      const seen = new Set<string>()
      for (const sourceId of sources) {
        for (const item of this.evidence[sourceId] ?? []) {
          const key = String(item.feedback_id)
          if (seen.has(key)) continue // MERGE 去重
          seen.add(key)
          merged.push(item)
        }
      }
      const newId = `topic-merged-${this.revision + 1}`
      this.topics = this.topics.filter(t => !sources.includes(String(t.topic_id)))
      for (const sourceId of sources) delete this.evidence[sourceId]
      this.topics.push({ topic_id: newId, name: body.name?.trim() || sources.join('/'), summary: '', severity: 'medium', feedback_count: merged.length, summary_revalidated: false })
      this.evidence[newId] = merged
      affected.push(...sources, newId)
    } else if (body.operation === 'SPLIT') {
      const ids = body.feedback_ids ?? []
      if (!ids.length || !body.name?.trim()) throw new ApiHttpError(422, 'split_requires_targets')
      const all = this.evidence[topicId] ?? []
      const moved = all.filter(e => ids.includes(String(e.feedback_id)))
      if (!moved.length) throw new ApiHttpError(422, 'no_matching_feedback')
      this.evidence[topicId] = all.filter(e => !ids.includes(String(e.feedback_id)))
      target.feedback_count = this.evidence[topicId].length
      const newId = `topic-split-${this.revision + 1}`
      this.topics.push({ topic_id: newId, name: body.name, summary: '', severity: 'medium', feedback_count: moved.length, summary_revalidated: false })
      this.evidence[newId] = moved
      affected.push(topicId, newId)
    } else if (body.operation === 'CREATE') {
      const ids = body.feedback_ids ?? []
      if (!ids.length || !body.name?.trim()) throw new ApiHttpError(422, 'create_requires_targets')
      const pool = this.evidence['__unassigned__'] ?? []
      const picked = pool.filter(e => ids.includes(String(e.feedback_id)))
      if (!picked.length) throw new ApiHttpError(422, 'foreign_feedback')
      this.evidence['__unassigned__'] = pool.filter(e => !ids.includes(String(e.feedback_id)))
      const newId = `topic-created-${this.revision + 1}`
      this.topics.push({ topic_id: newId, name: body.name, summary: '', severity: 'medium', feedback_count: picked.length, summary_revalidated: false })
      this.evidence[newId] = picked
      affected.push(newId)
    } else {
      throw new ApiHttpError(422, 'unsupported_operation')
    }

    this.history.set(this.revision, this.snapshot())
    this.revision += 1
    return { revision: this.revision, affected_topic_ids: affected }
  }
}

const MOCK_CORRECTION_STORE = new MockCorrectionStore()

const SYNTHETIC_BATCHES: DatasetBatch[] = [
  { id: 'ds_demo_001', name: '8 月第 4 周反馈批次', rows: 1248, status: 'ready', createdAt: '2026-08-25T10:00:00+08:00' },
  { id: 'ds_demo_002', name: '8 月第 3 周反馈批次', rows: 1105, status: 'ready', createdAt: '2026-08-18T10:00:00+08:00' },
  { id: 'ds_demo_003', name: '8 月第 2 周反馈批次', rows: 987, status: 'ready', createdAt: '2026-08-11T10:00:00+08:00' },
]

export const mockApi: ApiClient = {
  upload: uploadMock,
  // 与真实实现同形状:治理报告的 6 项计数(见 client.health 的映射)
  async health() {
    await delay(200)
    return { inputRows: 1248, validRows: 1240, invalidRows: 3, duplicateRows: 5, redactedRows: 812, undatedRows: 12 }
  },
  async runAnalysis() {
    await delay(500)
    return { id: 'run-1', status: 'done', total: 1248, progress: 1248 }
  },
  async logout() {
    await delay(100)
  },
  async authConfig() {
    await delay(100)
    return { mode: 'local' as const }
  },
  async loginWithAssertion() {
    await delay(200)
    return {
      access_token: 'demo-token', token_type: 'bearer', expires_in: 3600,
      user: { id: 'demo-user', name: 'Demo Analyst', email: 'demo@voicelens.local', role: 'ANALYST' },
    }
  },
  async login() {
    await delay(200)
    return {
      access_token: 'demo-token',
      token_type: 'bearer',
      expires_in: 3600,
      user: { id: 'demo-user', name: 'Demo Analyst', email: 'demo@voicelens.local', role: 'ANALYST' },
    }
  },
  async createExport(projectId: string, body: { scope: string }, _key: string) {
    await delay(250)
    const now = new Date()
    const expires = new Date(now.getTime() + 24 * 3600 * 1000)
    return {
      id: 'exp_demo_1', project_id: projectId, scope: body.scope, state: 'DONE',
      row_count: SYNTHETIC_BATCHES.reduce((sum, b) => sum + b.rows, 0),
      created_at: now.toISOString(), expires_at: expires.toISOString(),
      expired: false, invalidated: false,
      download_path: `/api/v1/projects/${projectId}/exports/exp_demo_1/download`,
    }
  },
  async downloadExport() {
    await delay(200)
    return new Blob(['dataset_id,row_index,data\n'], { type: 'text/csv;charset=utf-8' })
  },
  async summary(projectId: string) {
    await delay(300)
    // 合成数据按请求项目返回 project_id,任何演示项目都可用(仍须常显演示身份)
    return { ...SYNTHETIC_SUMMARY, project_id: projectId }
  },
  async topics() {
    await delay(300)
    return SYNTHETIC_TOPICS.map(topicRow)
  },
  async trend() {
    await delay(300)
    return SYNTHETIC_TREND
  },
  async taskSummaries() {
    await delay(300)
    return MOCK_TASK_STORE.list()
  },
  async getTask(_projectId: string, taskId: string) {
    await delay(200)
    return MOCK_TASK_STORE.detail(taskId)
  },
  async createTaskDraft(_projectId: string, body: { title: string; source_topic_version_id?: string | null }) {
    await delay(200)
    return MOCK_TASK_STORE.create(body.title, body.source_topic_version_id ?? null)
  },
  async confirmTask(_projectId: string, taskId: string, body: TaskConfirmBody, idempotencyKey: string) {
    await delay(250)
    return MOCK_TASK_STORE.confirm(taskId, body, idempotencyKey)
  },
  async transitionTask(_projectId: string, taskId: string, body: TaskTransitionBody, idempotencyKey: string) {
    await delay(250)
    return MOCK_TASK_STORE.transition(taskId, body, idempotencyKey)
  },
  async listRisks() {
    await delay(300)
    return MOCK_RISK_STORE.list()
  },
  async patchTask(_projectId: string, taskId: string, body: TaskPatchBody) {
    await delay(200)
    return MOCK_TASK_STORE.patch(taskId, body)
  },
  async listMembers() {
    await delay(200)
    return SYNTHETIC_MEMBERS.map(member => ({ ...member }))
  },
  async getSettings() {
    await delay(200)
    return MOCK_SETTINGS_STORE.get()
  },
  async patchSettings(_projectId: string, body: ProjectSettingsPatchBody) {
    await delay(250)
    return MOCK_SETTINGS_STORE.patch(body)
  },
  async getFeedback(_projectId: string, feedbackId: string) {
    await delay(200)
    const quote = SYNTHETIC_TOPICS.flatMap(t => t.quote).find(q => q.feedbackId === feedbackId)
      ?? SYNTHETIC_TOPICS[0]!.quote
    return {
      feedback_id: feedbackId, dataset_id: 'ds_demo_001', dataset_name: '8 月第 4 周反馈批次',
      source_row: quote.rowIndex ?? 0, channel: quote.channel, occurred_at: quote.occurredAt,
      text: quote.text,
      segments: [{ start: 0, end: Array.from(quote.text).length, text: quote.text }],
    }
  },
  async reviewRisk(_projectId: string, riskId: string, body: RiskReviewBody) {
    await delay(250)
    return MOCK_RISK_STORE.review(riskId, body)
  },
  async getTopicDetail(_projectId: string, topicId: string, topicVersionId?: number): Promise<TopicDetailResponse> {
    await delay(200)
    return MOCK_CORRECTION_STORE.detail(topicId, topicVersionId) as TopicDetailResponse
  },
  async correctTopic(_projectId: string, topicId: string, body: CorrectionBody) {
    await delay(250)
    return MOCK_CORRECTION_STORE.correct(topicId, body)
  },
  async listReviews() {
    await delay(300)
    return MOCK_REVIEW_STORE.list()
  },
  async getReview(_projectId: string, reviewId: string) {
    await delay(200)
    const review = MOCK_REVIEW_STORE.find(reviewId)
    if (!review) throw new ApiHttpError(404, 'review_not_found')
    return review
  },
  async createReview(_projectId: string, body: ReviewCreateBody) {
    await delay(250)
    return MOCK_REVIEW_STORE.create(body)
  },
  async recentBatches() {
    await delay(300)
    return SYNTHETIC_BATCHES
  },
  async previewDeletion(_projectId: string, body: DeletionTarget) {
    await delay(200)
    // target_name 必须是目标的真实名称(供用户逐字确认),不是 confirm_name 的回显
    const targetName = body.target_type === 'project'
      ? 'VoiceLens Demo Project'
      : (SYNTHETIC_BATCHES.find(b => b.id === body.target_id)?.name ?? body.target_id)
    return {
      target_type: body.target_type,
      target_id: body.target_id,
      target_name: targetName,
      datasets: body.target_type === 'project' ? SYNTHETIC_BATCHES.length : 1,
      runs: 1, topics: SYNTHETIC_TOPICS.length, tasks: SYNTHETIC_TASKS.length,
      reviews: 2, risks: SYNTHETIC_RISKS.length,
      invalidates_reports: body.target_type === 'dataset',
    }
  },
  async executeDeletion(_projectId: string, body: DeletionBody) {
    await delay(300)
    return {
      job_id: `del_${body.target_id.slice(0, 8)}`, state: 'DONE',
      target_type: body.target_type, target_id: body.target_id,
      steps: [
        { name: 'tombstone', status: 'done' }, { name: 'cancel_jobs', status: 'done' },
        { name: 'purge_runs', status: 'done' }, { name: 'purge_datasets', status: 'done' },
        { name: 'verify', status: 'done' },
      ],
      removed: { datasets: 1, runs: 1, topics: SYNTHETIC_TOPICS.length, tasks: 0, reviews: 0, risks: 0 },
    }
  },
}
