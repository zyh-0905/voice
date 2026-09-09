// evidence-quote.spec.ts — 纯文本渲染、Unicode offset 与引文重构(风格规范 6.4/12.1)。
import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import EvidenceQuote from '../../src/components/common/EvidenceQuote.vue'
import type { EvidenceQuoteItem } from '../../src/types/domain'

function mountQuote(quote: EvidenceQuoteItem) {
  return mount(EvidenceQuote, { props: { quote } })
}

test('Unicode 字符 offset:emoji 前后的高亮切片拼回完整原文', () => {
  const text = '反馈:😀包裹延迟,物流信息未更新。'
  const highlight = '包裹延迟'
  const chars = Array.from(text)
  const start = chars.indexOf('包')
  const end = start + Array.from(highlight).length
  const wrapper = mountQuote({
    feedbackId: 'fb-1', text, start, end, channel: 'chat', occurredAt: null, rowIndex: 3,
  })
  expect(wrapper.get('mark').text()).toBe(highlight)
  expect(wrapper.get('blockquote').text()).toBe(text)
})

test('纯文本渲染:HTML 字符串按字面量显示,不产生元素', () => {
  const text = '<img src=x onerror=alert(1)>安全文本'
  const wrapper = mountQuote({
    feedbackId: 'fb-2', text, start: 0, end: Array.from(text).length, channel: null, occurredAt: null, rowIndex: null,
  })
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.get('blockquote').text()).toBe(text)
})

test('越界 offset 被安全钳制,不抛错', () => {
  const text = '短文本'
  const wrapper = mountQuote({
    feedbackId: 'fb-3', text, start: 10, end: 99, channel: null, occurredAt: null, rowIndex: null,
  })
  expect(wrapper.get('blockquote').text()).toBe(text)
})
