import AxeBuilder from '@axe-core/playwright'
import { test, expect } from './ui-fixtures'

test('overview has no serious accessibility violations', async ({ page }) => {
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations.filter(v => ['serious', 'critical'].includes(v.impact ?? ''))).toEqual([])
})
