import { test, expect } from './ui-fixtures'

test('demo user can inspect overview evidence', async ({ page }) => {
  await expect(page.getByTestId('demo-notice')).toContainText('演示')
  await expect(page.getByTestId('metric-pending-risks')).toHaveText('3')
  await page.getByRole('button', { name: /风险规则命中/ }).click()
  await expect(page.getByTestId('evidence-drawer')).toBeVisible()
  await page.getByTestId('evidence-close').press('Escape')
  await expect(page.getByTestId('evidence-drawer')).toBeHidden()
})
