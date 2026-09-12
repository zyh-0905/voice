// ui-status.spec.ts — 业务 enum 的中文标签与未知来源安全回退(风格规范 8.1/12.1)。
import { expect, test } from 'vitest'
import {
  comparabilityLabel,
  effectStatusLabel,
  reviewStateAppearance,
  reviewStateLabel,
  severityAppearance,
  severityLabel,
  sourceLabel,
  taskStatusAppearance,
  taskStatusLabel,
} from '../../src/lib/ui-status'

test('任务状态标签符合固定文案映射', () => {
  expect(taskStatusLabel('DRAFT')).toBe('草稿·待确认')
  expect(taskStatusLabel('OPEN')).toBe('待开始')
  expect(taskStatusLabel('IN_PROGRESS')).toBe('进行中')
  expect(taskStatusLabel('PENDING_REVIEW')).toBe('待验收')
  expect(taskStatusLabel('CLOSED')).toBe('执行已验收')
  expect(taskStatusLabel('CANCELLED')).toBe('已取消')
})

test('PENDING_REVIEW 不能显示为「已人工确认」', () => {
  expect(taskStatusLabel('PENDING_REVIEW')).not.toContain('已人工确认')
})

test('CLOSED 不显示因果改善结论', () => {
  expect(taskStatusLabel('CLOSED')).toBe('执行已验收')
  expect(taskStatusLabel('CLOSED')).not.toContain('改善')
  expect(taskStatusAppearance('CLOSED')).toBe('success')
})

test('severity 标签与外观', () => {
  expect(severityLabel('CRITICAL')).toBe('严重')
  expect(severityLabel('HIGH')).toBe('高')
  expect(severityLabel('MEDIUM')).toBe('中')
  expect(severityLabel('LOW')).toBe('低')
  expect(severityLabel('NONE')).toBe('无')
  expect(severityAppearance('CRITICAL')).toBe('danger')
  expect(severityAppearance('MEDIUM')).toBe('warning')
})

test('来源标签固定文案', () => {
  expect(sourceLabel('ai')).toBe('AI 建议')
  expect(sourceLabel('rule')).toBe('规则候选')
  expect(sourceLabel('human')).toBe('人工修订')
  expect(sourceLabel('unknown')).toBe('来源未提供')
})

test('主题复核状态', () => {
  expect(reviewStateLabel('pending')).toBe('待复核')
  expect(reviewStateLabel('confirmed')).toBe('已确认')
  expect(reviewStateLabel('excluded')).toBe('已排除')
  expect(reviewStateAppearance('pending')).toBe('warning')
})

test('效果状态', () => {
  expect(effectStatusLabel('NOT_EVALUATED')).toBe('尚未复盘')
  expect(effectStatusLabel('INSUFFICIENT_DATA')).toBe('数据不足')
  expect(effectStatusLabel('OBSERVED_CHANGE')).toBe('观察到变化')
})

test('复盘可比性标签:low_sample 不能写成「可比」', () => {
  expect(comparabilityLabel('ok')).toBe('可比')
  expect(comparabilityLabel('insufficient')).toBe('无法比较')
  expect(comparabilityLabel('low_sample')).toBe('样本量不足')
  expect(comparabilityLabel('low_sample')).not.toContain('可比')
})

test('未知值安全回退:返回原值且不抛错', () => {
  expect(taskStatusLabel('UNKNOWN_STATE')).toBe('UNKNOWN_STATE')
  expect(severityLabel('weird')).toBe('weird')
  expect(sourceLabel('weird')).toBe('weird')
  expect(reviewStateLabel('weird')).toBe('weird')
  expect(effectStatusLabel('weird')).toBe('weird')
  expect(comparabilityLabel('weird')).toBe('weird')
})
