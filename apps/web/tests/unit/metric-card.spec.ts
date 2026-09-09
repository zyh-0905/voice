// metric-card.spec.ts — 0/null/error 三分与范围说明(风格规范 UI-10/12.1)。
import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import MetricCard from '../../src/components/common/MetricCard.vue'

test('真实零显示 0,不显示为「—」', () => {
  const wrapper = mount(MetricCard, { props: { title: '真实零', value: 0, scopeLabel: '本项目·所有分析' } })
  expect(wrapper.get('[data-testid="metric-value"]').text()).toBe('0')
})

test('null 显示「—」', () => {
  const wrapper = mount(MetricCard, { props: { title: '无数据', value: null, scopeLabel: '所选分析与筛选' } })
  expect(wrapper.get('[data-testid="metric-value"]').text()).toBe('—')
})

test('error 不显示数字,显示失败标记', () => {
  const wrapper = mount(MetricCard, { props: { title: '失败', value: 5, state: 'error', scopeLabel: '所选分析与筛选' } })
  expect(wrapper.get('[data-testid="metric-value"]').text()).toBe('获取失败')
})

test('scopeLabel 常显且有 metric-scope 定位符', () => {
  const wrapper = mount(MetricCard, { props: { title: 't', value: 1, scopeLabel: '本项目·所有分析' } })
  expect(wrapper.get('[data-testid="metric-scope"]').text()).toBe('本项目·所有分析')
})

test('带单位的数值与格式', () => {
  const wrapper = mount(MetricCard, { props: { title: '有效反馈', value: 1000, unit: '条', scopeLabel: '所选分析与筛选' } })
  expect(wrapper.get('[data-testid="metric-value"]').text()).toContain('1,000')
  expect(wrapper.get('[data-testid="metric-value"]').text()).toContain('条')
})
