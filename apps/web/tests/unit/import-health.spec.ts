// import-health.spec.ts — 工程计划 W05:脱敏/缺时间行是交叉属性,不改变有效行总数。
import { mount } from '@vue/test-utils'
import { expect, test } from 'vitest'
import ImportHealth from '../../src/components/common/ImportHealth.vue'

test('脱敏行是交叉属性,不改变有效行总数', () => {
  const wrapper = mount(ImportHealth, {
    props: {
      health: { inputRows: 10, validRows: 7, invalidRows: 1, duplicateRows: 2, redactedRows: 3, undatedRows: 0 },
    },
  })
  expect(wrapper.get('[data-testid="valid-rows"]').text()).toBe('7')
  expect(wrapper.get('[data-testid="redacted-rows"]').text()).toBe('3')
  expect(wrapper.get('[data-testid="invalid-rows"]').text()).toBe('1')
  expect(wrapper.get('[data-testid="duplicate-rows"]').text()).toBe('2')
})
