import { test, expect } from './ui-fixtures'

test('demo user can complete import mapping and see governance report', async ({ page }) => {
  await page.goto('/p/demo-project/imports')
  await expect(page.getByTestId('import-page')).toBeVisible()
  const input = page.getByTestId('file-input')
  await input.setInputFiles({ name: 'notes.pdf', mimeType: 'application/pdf', buffer: Buffer.from('bad') })
  await expect(page.getByTestId('import-error')).toContainText('仅支持')
  await input.setInputFiles({ name: 'calls.csv', mimeType: 'text/csv', buffer: Buffer.from('call_id,transcript\n1,hello') })
  await page.getByTestId('upload-button').click()
  await expect(page.getByTestId('field-mapping')).toBeVisible()
  await page.getByTestId('mapping-next').click()
  await expect(page.getByTestId('import-health')).toBeVisible()
})

test('viewer sees demo risks and tasks without mutation actions', async ({ page }) => {
  await page.goto('/p/demo-project/risks')
  await expect(page.getByText('演示数据')).toBeVisible()
  await expect(page.getByRole('button', { name: '创建风险' })).toHaveCount(0)
  await page.goto('/p/demo-project/tasks')
  await expect(page.getByText('演示数据')).toBeVisible()
  await expect(page.getByRole('button', { name: '创建任务' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: '执行' })).toHaveCount(0)
})
