// tasks.spec:任务详情状态机(工程计划 W16 验收)
import { test, expect } from './ui-fixtures'

test('未填写负责人不能派发草稿', async ({ page }) => {
  // 造一个草稿:从任务列表进入详情
  await page.goto('/p/demo-project/tasks')
  await page.getByTestId('create-task-draft').click()
  const draftRow = page.locator('[data-resource-id^="task-draft-"]').first()
  await expect(draftRow).toBeVisible()
  await draftRow.getByTestId('task-open').click()

  await expect(page.getByTestId('task-state')).toContainText('草稿')
  await page.getByTestId('task-confirm').click()
  // 清空负责人后直接确认 → 内联校验错误,状态保持草稿
  await page.getByTestId('task-owner-input').fill('')
  await page.getByTestId('review-dialog-confirm').click()
  await expect(page.getByTestId('owner-validation-error')).toBeVisible()
  await expect(page.getByTestId('task-state')).toContainText('草稿')
})

test('草稿派发→开始→提交→验收是全流程,且记录流转', async ({ page }) => {
  await page.goto('/p/demo-project/tasks')
  await page.getByTestId('create-task-draft').click()
  const draftRow = page.locator('[data-resource-id^="task-draft-"]').first()
  await draftRow.getByTestId('task-open').click()

  // 派发
  await page.getByTestId('task-confirm').click()
  await page.getByTestId('task-owner-input').fill('owner-1')
  await page.getByTestId('task-due-input').fill('2026-09-20')
  await page.getByTestId('task-acceptance-input').fill('退款率下降并复核')
  await page.getByTestId('review-dialog-confirm').click()
  await expect(page.getByTestId('task-state')).toContainText('待开始')

  // 开始执行
  await page.getByTestId('task-start').click()
  await page.getByTestId('review-dialog-confirm').click()
  await expect(page.getByTestId('task-state')).toContainText('进行中')

  // 提交执行材料:说明必填,未填写时拦在对话框内
  await page.getByTestId('task-submit-review').click()
  await page.getByTestId('review-dialog-confirm').click()
  await expect(page.getByTestId('review-dialog-error')).toBeVisible()
  await page.getByTestId('review-dialog-comment').fill('已按验收标准完成整改,附材料链接')
  await page.getByTestId('review-dialog-confirm').click()
  await expect(page.getByTestId('task-state')).toContainText('待验收')

  // 流转记录不伪造过去事件
  await expect(page.getByTestId('task-timeline')).toContainText('确认派发')
  await expect(page.getByTestId('task-timeline')).toContainText('提交执行材料')
})

test('验收后效果状态不自动宣称改善', async ({ page }) => {
  await page.goto('/p/demo-project/tasks')
  // 使用演示种子中处于待验收状态的任务
  const row = page.locator('[data-resource-id="task-003"]')
  await row.getByTestId('task-open').click()
  await expect(page.getByTestId('task-state')).toContainText('待验收')
  await expect(page.getByTestId('task-effect')).toContainText('尚未复盘')

  await page.getByTestId('task-approve').click()
  await page.getByTestId('review-dialog-comment').fill('材料齐备,验收通过')
  await page.getByTestId('review-dialog-confirm').click()
  await expect(page.getByTestId('task-state')).toContainText('执行已验收')
  await expect(page.getByTestId('task-effect')).toContainText('尚未复盘')
})

test('VIEWER 只读:详情页不出现主动作', async ({ page }) => {
  await page.goto('/login')
  await page.getByTestId('login-readonly').click()
  await page.goto('/p/demo-project/tasks/task-003')
  await expect(page.getByTestId('task-state')).toBeVisible()
  await expect(page.getByTestId('task-approve')).toHaveCount(0)
  await expect(page.getByTestId('task-confirm')).toHaveCount(0)
})
