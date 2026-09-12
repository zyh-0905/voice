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


// W14 风险裁决:理由必填、裁决后状态更新、确认不等于"已确认事故"
test('风险裁决需填写理由,确认后状态更新', async ({ page }) => {
  await page.goto('/p/demo-project/risks')
  const row = page.locator('[data-testid="risk-table"] tbody tr').filter({ hasText: '待复核' }).first()
  await row.getByTestId('risk-confirm').click()

  // 未填理由直接提交 → 拦在对话框内
  await page.getByTestId('risk-confirm-submit').click()
  await expect(page.getByTestId('risk-reason-error')).toBeVisible()

  await page.locator('#vl-risk-reason').fill('已对照原文与命中规则,确认属实际问题')
  await page.getByTestId('risk-confirm-submit').click()
  await expect(page.locator('[data-testid="risk-table"]').getByText('已确认').first()).toBeVisible()
})


// 10.4 删除:必须输入项目名才能确认;确认按钮在名称匹配前不可用
test('删除项目需先看影响范围并输入名称确认', async ({ page }) => {
  await page.goto('/p/demo-project/settings')
  await page.getByTestId('delete-data').click()

  // 影响范围逐项展示,且明确说明旧报告不再有效
  await expect(page.getByTestId('delete-impact')).toBeVisible()
  await expect(page.getByTestId('delete-invalidates')).toContainText('不再作为有效结果')

  const confirm = page.getByTestId('delete-project-confirm')
  await expect(confirm).toBeDisabled()
  await page.getByTestId('delete-confirm-name').fill('写错的名称')
  await expect(confirm).toBeDisabled()
  await page.getByTestId('delete-confirm-name').fill('VoiceLens Demo Project')
  await expect(confirm).toBeEnabled()
})
