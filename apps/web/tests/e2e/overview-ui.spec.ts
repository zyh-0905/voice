import { test, expect } from './ui-fixtures'

test('demo user can inspect overview evidence', async ({ page }) => {
  await expect(page.getByTestId('demo-notice')).toBeVisible()
  await expect(page.getByTestId('metric-pending-risks')).toHaveText('3')
  await page.getByTestId('evidence-panel').locator('button').first().click()
  await expect(page.getByTestId('evidence-drawer')).toBeVisible()
  await page.getByTestId('evidence-close').press('Escape')
  await expect(page.getByTestId('evidence-drawer')).toBeHidden()
})
