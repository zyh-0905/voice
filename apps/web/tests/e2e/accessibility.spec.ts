import AxeBuilder from '@axe-core/playwright'
import { test, expect } from './ui-fixtures'

test('overview has no serious accessibility violations', async ({ page }) => {
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations.filter(v => ['serious', 'critical'].includes(v.impact ?? ''))).toEqual([])
})

test('opened evidence drawer has no serious accessibility violations', async ({ page }) => {
  await page.locator('[data-resource-id="delivery"]').getByRole('button', { name: '查看证据' }).click()
  await expect(page.getByTestId('evidence-drawer')).toBeVisible()
  // 等待 180ms 显隐过渡完成,避免 opacity 中间态造成对比度误报
  await expect(page.locator('.vl-overlay')).toHaveCSS('opacity', '1')
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations.filter(v => ['serious', 'critical'].includes(v.impact ?? ''))).toEqual([])
})
