import { test, expect } from './ui-fixtures'

test('工作台按行动顺序展示四卡、范围说明与主题表', async ({ page }) => {
  await expect(page.getByTestId('app-shell')).toBeVisible()
  await expect(page.getByTestId('page-title')).toHaveText('工作台')
  await expect(page.getByTestId('demo-notice').first()).toBeVisible()

  // 四卡顺序与 7.7 合成契约样例值
  const cards = page.locator('.vl-metrics > *')
  await expect(cards).toHaveCount(4)
  await expect(cards.nth(0)).toHaveAttribute('data-testid', 'metric-pending-risks')
  await expect(cards.nth(1)).toHaveAttribute('data-testid', 'metric-overdue-tasks')
  await expect(cards.nth(2)).toHaveAttribute('data-testid', 'metric-active-tasks')
  await expect(cards.nth(3)).toHaveAttribute('data-testid', 'metric-valid-feedback')

  await expect(page.getByTestId('metric-pending-risks').getByTestId('metric-value')).toHaveText('12')
  await expect(page.getByTestId('metric-overdue-tasks').getByTestId('metric-value')).toHaveText('4')
  await expect(page.getByTestId('metric-active-tasks').getByTestId('metric-value')).toHaveText('18')
  await expect(page.getByTestId('metric-valid-feedback').getByTestId('metric-value')).toContainText('1,000')

  // 范围说明常显,两组指标不同 scope(UI-03)
  await expect(page.getByTestId('metric-pending-risks').getByTestId('metric-scope')).toHaveText('所选分析与筛选')
  await expect(page.getByTestId('metric-overdue-tasks').getByTestId('metric-scope')).toHaveText('本项目·所有分析')
  await expect(page.getByTestId('metric-valid-feedback').getByTestId('metric-scope')).toHaveText('所选分析与筛选')

  // 优先主题是表格而非卡片,行带 data-resource-id
  await expect(page.getByTestId('topic-table')).toBeVisible()
  await expect(page.locator('[data-resource-id="delivery"]')).toBeVisible()
})

test('趋势图提供可见摘要、数据表入口与断点', async ({ page }) => {
  await page.getByTestId('chart-data-toggle').click()
  await expect(page.getByTestId('chart-data-table')).toBeVisible()
  // 缺失日期显示「—」,不跨空值连线(UI-17/18 的数据表侧)
  await expect(page.getByTestId('chart-data-table').getByText('—')).toBeVisible()
})

test('窄屏下证据走模态抽屉,Esc 关闭并返回焦点', async ({ page }) => {
  // 默认视口 1280×720 处于 1024-1439:证据为模态抽屉
  const trigger = page.locator('[data-resource-id="delivery"]').getByRole('button', { name: '查看证据' })
  await trigger.click()
  const drawer = page.getByTestId('evidence-drawer')
  await expect(drawer).toBeVisible()
  await expect(drawer).toHaveAttribute('aria-modal', 'true')
  await page.getByTestId('evidence-close').press('Escape')
  await expect(drawer).toBeHidden()
  await expect(trigger).toBeFocused()
})
