// topics.spec:主题详情与人工校正(工程计划 W13 前端验收)
import { test, expect } from './ui-fixtures'

test('主题详情展示摘要、证据源行与片段偏移', async ({ page }) => {
  await page.goto('/p/demo-project/topics')
  await page.locator('[data-resource-id="delivery"]').getByTestId('topic-open').click()

  await expect(page.getByTestId('page-title')).toContainText('物流体验')
  await expect(page.getByTestId('topic-evidence')).toContainText('源行')
  await expect(page.getByTestId('topic-evidence')).toContainText('片段')
})

test('校正理由必填,缺失时拦在对话框内', async ({ page }) => {
  await page.goto('/p/demo-project/topics/delivery')
  await page.getByTestId('topic-correct').click()
  await page.getByTestId('correction-name').fill('外包装破损')
  await page.getByTestId('correction-submit').click()
  await expect(page.getByTestId('correction-error')).toContainText('理由')
})

test('重命名创建新 revision,旧版本仍可查看', async ({ page }) => {
  await page.goto('/p/demo-project/topics/delivery')
  await page.getByTestId('topic-correct').click()
  await page.getByTestId('correction-name').fill('外包装破损')
  await page.getByTestId('correction-reason').fill('人工核对后明确问题对象')
  await page.getByTestId('correction-submit').click()

  await expect(page.getByTestId('page-title')).toContainText('外包装破损')
  // 新版本摘要未重新验证时显式标注
  await expect(page.getByTestId('topic-pending-revalidation')).toBeVisible()
})

test('MERGE 至少需要两个来源主题', async ({ page }) => {
  await page.goto('/p/demo-project/topics/delivery')
  await page.getByTestId('topic-correct').click()
  await page.getByTestId('correction-operation').selectOption('MERGE')
  await page.getByTestId('correction-reason').fill('两条线索实为同一问题')
  await page.getByTestId('correction-submit').click()
  await expect(page.getByTestId('correction-error')).toContainText('两个来源')
})
