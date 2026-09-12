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
  // 不选负责人直接确认 → 内联校验错误,状态保持草稿
  await page.getByTestId('task-owner-input').selectOption('')
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
  await page.getByTestId('task-owner-input').selectOption('owner-1')
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

// W16:负责人选项只来自项目成员接口,不再是自由文本输入
test('派发对话框的负责人选项来自项目成员接口', async ({ page }) => {
  await page.goto('/p/demo-project/tasks')
  await page.getByTestId('create-task-draft').click()
  await page.locator('[data-resource-id^="task-draft-"]').first().getByTestId('task-open').click()
  await page.getByTestId('task-confirm').click()

  const ownerSelect = page.getByTestId('task-owner-input')
  await expect(ownerSelect).toBeVisible()
  // 必须是 select(来自成员接口),而不是自由文本输入
  await expect(page.locator('input[data-testid="task-owner-input"]')).toHaveCount(0)
  await expect(ownerSelect.locator('option[value="owner-1"]')).toHaveText('Demo Analyst')
  await expect(ownerSelect.locator('option[value="viewer-1"]')).toHaveText('Demo Viewer')

  await ownerSelect.selectOption('owner-1')
  await page.getByTestId('task-due-input').fill('2026-09-25')
  await page.getByTestId('task-acceptance-input').fill('按成员列表选择负责人')
  await page.getByTestId('review-dialog-confirm').click()
  await expect(page.getByTestId('task-state')).toContainText('待开始')
  await expect(page.getByTestId('task-owner')).toContainText('owner-1')
})

test('VIEWER 只读:详情页不出现主动作', async ({ page }) => {
  await page.goto('/login')
  await page.getByTestId('login-readonly').click()
  await page.goto('/p/demo-project/tasks/task-003')
  await expect(page.getByTestId('task-state')).toBeVisible()
  await expect(page.getByTestId('task-approve')).toHaveCount(0)
  await expect(page.getByTestId('task-confirm')).toHaveCount(0)
})


// W22:草稿内联编辑——草稿与正式任务的可改字段不同,state 不走这个入口
test('草稿可内联编辑标题与优先级,正式任务字段不出现在草稿表单', async ({ page }) => {
  await page.goto('/p/demo-project/tasks')
  await page.getByTestId('create-task-draft').click()
  const draftRow = page.locator('[data-resource-id^="task-draft-"]').first()
  await draftRow.getByTestId('task-open').click()
  await expect(page.getByTestId('task-state')).toContainText('草稿')

  await page.getByTestId('task-edit').click()
  const form = page.getByTestId('task-edit-form')
  await expect(form).toBeVisible()
  // 草稿阶段的可改控件只有标题/来源/优先级;期限与验收标准要到派发后才可调
  await expect(form.locator('input, select')).toHaveCount(3)
  await expect(form.getByLabel('验收标准')).toHaveCount(0)
  await expect(form.getByLabel('期限')).toHaveCount(0)

  await page.getByTestId('task-edit-title').fill('草稿标题已修订')
  await page.getByTestId('task-edit-priority').selectOption('HIGH')
  await page.getByTestId('task-edit-save').click()

  // 保存后表单收起,详情回写新值
  await expect(form).toBeHidden()
  await expect(page.getByTestId('page-title')).toContainText('草稿标题已修订')
  await expect(page.getByTestId('task-state')).toContainText('草稿')
})

test('派发后的任务不再提供草稿编辑入口', async ({ page }) => {
  await page.goto('/p/demo-project/tasks')
  await page.locator('[data-resource-id="task-003"]').getByTestId('task-open').click()
  await expect(page.getByTestId('task-state')).toContainText('待验收')
  await expect(page.getByTestId('task-edit')).toHaveCount(0)
})
