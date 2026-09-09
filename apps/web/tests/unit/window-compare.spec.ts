// window-compare.spec.ts — 工程计划 W18:复盘黄金样例与不可比性限制。
import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import WindowCompare from '../../src/components/common/WindowCompare.vue'

test('168/1000→102/1000 显示 16.8%→10.2%,变化 −6.6 个百分点', () => {
  const wrapper = mount(WindowCompare, {
    props: { before: { n: 168, N: 1000 }, after: { n: 102, N: 1000 } },
  })
  expect(wrapper.get('[data-testid="review-before-share"]').text()).toContain('16.8%')
  expect(wrapper.get('[data-testid="review-after-share"]').text()).toContain('10.2%')
  expect(wrapper.get('[data-testid="review-share-delta"]').text()).toContain('-6.6 个百分点')
  expect(wrapper.text()).toContain('不能据此证明因果关系')
})

test('100/1000→80/500 同时显示数量减少与占比上升,不选择性报喜', () => {
  const wrapper = mount(WindowCompare, {
    props: { before: { n: 100, N: 1000 }, after: { n: 80, N: 500 } },
  })
  expect(wrapper.get('[data-testid="review-before-share"]').text()).toContain('10.0%')
  expect(wrapper.get('[data-testid="review-after-share"]').text()).toContain('16.0%')
  expect(wrapper.get('[data-testid="review-window-compare"]').text()).toContain('100 / 1,000')
  expect(wrapper.get('[data-testid="review-window-compare"]').text()).toContain('80 / 500')
})

test('分母为 0 时显示数据不足,不输出变化结论', () => {
  const wrapper = mount(WindowCompare, {
    props: { before: { n: 0, N: 0 }, after: { n: 5, N: 10 } },
  })
  expect(wrapper.get('[data-testid="review-share-delta"]').text()).toBe('—')
  expect(wrapper.text()).toContain('数据不足,暂不输出变化结论')
})
