// window-compare.spec.ts — 工程计划 W18:复盘黄金样例与可比性限制。
import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import WindowCompare from '../../src/components/common/WindowCompare.vue'
import type { ReviewComparability, ReviewWindow } from '../../src/types/domain'

function window(n: number, N: number): ReviewWindow {
  return { start: '2026-08-01T00:00:00+00:00', end: '2026-08-31T00:00:00+00:00', n, N, untimed: 0 }
}

function mountCompare(before: ReviewWindow, after: ReviewWindow, comparability: ReviewComparability) {
  return mount(WindowCompare, { props: { before, after, comparability } })
}

test('168/1000→102/1000 显示 16.8%→10.2%,变化 −6.6 个百分点', () => {
  const wrapper = mountCompare(window(168, 1000), window(102, 1000), 'ok')
  expect(wrapper.get('[data-testid="review-before-share"]').text()).toContain('16.8%')
  expect(wrapper.get('[data-testid="review-after-share"]').text()).toContain('10.2%')
  expect(wrapper.get('[data-testid="review-share-delta"]').text()).toContain('-6.6 个百分点')
  expect(wrapper.text()).toContain('不能据此证明因果关系')
})

test('100/1000→80/500 同时显示数量减少与占比上升,不选择性报喜', () => {
  const wrapper = mountCompare(window(100, 1000), window(80, 500), 'ok')
  expect(wrapper.get('[data-testid="review-before-share"]').text()).toContain('10.0%')
  expect(wrapper.get('[data-testid="review-after-share"]').text()).toContain('16.0%')
  expect(wrapper.get('[data-testid="review-window-compare"]').text()).toContain('100 / 1,000')
  expect(wrapper.get('[data-testid="review-window-compare"]').text()).toContain('80 / 500')
})

test('分母为 0 的 insufficient 不输出变化结论', () => {
  const wrapper = mountCompare(window(0, 0), window(5, 10), 'insufficient')
  expect(wrapper.get('[data-testid="review-share-delta"]').text()).toBe('—')
  expect(wrapper.get('[data-testid="review-before-share"]').text()).toBe('—')
  expect(wrapper.get('[data-testid="review-incomparable"]').text()).toContain('无法比较')
  // 原始数量与分母始终可见
  expect(wrapper.get('[data-testid="review-window-compare"]').text()).toContain('0 / 0')
  expect(wrapper.get('[data-testid="review-window-compare"]').text()).toContain('5 / 10')
})

test('low_sample 保留数量与占比,但变化显示为 — 且不给结论', () => {
  const wrapper = mountCompare(window(12, 40), window(15, 40), 'low_sample')
  expect(wrapper.get('[data-testid="review-share-delta"]').text()).toBe('—')
  expect(wrapper.get('[data-testid="review-window-compare"]').text()).toContain('12 / 40')
  expect(wrapper.get('[data-testid="review-window-compare"]').text()).toContain('15 / 40')
  expect(wrapper.get('[data-testid="review-low-sample"]').text()).toContain('样本量不足')
  expect(wrapper.text()).not.toContain('个百分点')
})
