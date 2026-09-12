// lib/ui-status.ts — 服务端枚举的中文标签与外观语义(风格规范 8.1/9.4)。
// 只做「显示」映射,不定义业务转换;未知值安全回退,不抛错、不猜测。

export type StatusAppearance = 'neutral' | 'info' | 'warning' | 'success' | 'danger'

const TASK_STATUS_LABELS: Record<string, { label: string; appearance: StatusAppearance }> = {
  DRAFT: { label: '草稿·待确认', appearance: 'neutral' },
  OPEN: { label: '待开始', appearance: 'info' },
  IN_PROGRESS: { label: '进行中', appearance: 'info' },
  PENDING_REVIEW: { label: '待验收', appearance: 'warning' },
  CLOSED: { label: '执行已验收', appearance: 'success' },
  CANCELLED: { label: '已取消', appearance: 'neutral' },
}

export function taskStatusLabel(state: string): string {
  return TASK_STATUS_LABELS[state]?.label ?? state
}

export function taskStatusAppearance(state: string): StatusAppearance {
  return TASK_STATUS_LABELS[state]?.appearance ?? 'neutral'
}

const SEVERITY_LABELS: Record<string, { label: string; appearance: StatusAppearance }> = {
  NONE: { label: '无', appearance: 'neutral' },
  LOW: { label: '低', appearance: 'info' },
  MEDIUM: { label: '中', appearance: 'warning' },
  HIGH: { label: '高', appearance: 'danger' },
  CRITICAL: { label: '严重', appearance: 'danger' },
}

export function severityLabel(severity: string): string {
  return SEVERITY_LABELS[severity]?.label ?? severity
}

export function severityAppearance(severity: string): StatusAppearance {
  return SEVERITY_LABELS[severity]?.appearance ?? 'neutral'
}

/** AiProvenanceBadge 来源标签(风格规范 6.5/8.3 固定文案) */
const SOURCE_LABELS: Record<string, string> = {
  ai: 'AI 建议',
  rule: '规则候选',
  human: '人工修订',
  unknown: '来源未提供',
}

export function sourceLabel(origin: string): string {
  return SOURCE_LABELS[origin] ?? origin
}

const EFFECT_STATUS_LABELS: Record<string, string> = {
  NOT_EVALUATED: '尚未复盘',
  INSUFFICIENT_DATA: '数据不足',
  OBSERVED_CHANGE: '观察到变化',
}

export function effectStatusLabel(status: string): string {
  return EFFECT_STATUS_LABELS[status] ?? status
}

/** 复盘可比性(计划 7.5):ok/insufficient/low_sample 的中文说明 */
const COMPARABILITY_LABELS: Record<string, string> = {
  ok: '可比',
  insufficient: '无法比较',
  low_sample: '样本量不足',
}

export function comparabilityLabel(value: string): string {
  return COMPARABILITY_LABELS[value] ?? value
}

const REVIEW_STATE_LABELS: Record<string, { label: string; appearance: StatusAppearance }> = {
  pending: { label: '待复核', appearance: 'warning' },
  confirmed: { label: '已确认', appearance: 'success' },
  excluded: { label: '已排除', appearance: 'neutral' },
}

export function reviewStateLabel(state: string): string {
  return REVIEW_STATE_LABELS[state]?.label ?? state
}

export function reviewStateAppearance(state: string): StatusAppearance {
  return REVIEW_STATE_LABELS[state]?.appearance ?? 'neutral'
}
