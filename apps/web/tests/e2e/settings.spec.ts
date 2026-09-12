// settings.spec:项目设置 W03/7.2 —— 加载、保存、乐观锁冲突与只读角色
import { test, expect } from './ui-fixtures'

test('设置从服务端加载,保存时区后写入新版本', async ({ page }) => {
  await page.goto('/p/demo-project/settings')
  const timezone = page.locator('#vl-settings-timezone')
  // 页面初始默认是 Asia/Shanghai;加载成功后必须被服务端值(UTC)覆盖
  await expect(timezone).toHaveValue('UTC')
  await expect(page.getByTestId('settings-meta')).toContainText('v1')

  await timezone.selectOption('Asia/Shanghai')
  await page.getByTestId('save-settings').click()
  await expect(page.getByTestId('settings-saved')).toBeVisible()

  // 保存确实写入了服务端状态(mock 客户端),而不是仅翻转本地提示
  const stored = await page.evaluate(async () => {
    const mod = await import('/src/api/mock.ts')
    return mod.mockApi.getSettings('demo-project')
  })
  expect(stored.timezone).toBe('Asia/Shanghai')
  expect(stored.version).toBe(2)
})

test('版本冲突保留本地选择,重新加载后可再次保存', async ({ page }) => {
  await page.goto('/p/demo-project/settings')
  const timezone = page.locator('#vl-settings-timezone')
  await expect(timezone).toHaveValue('UTC')

  // 模拟其他会话先保存:版本 1 → 2,页面持有的 expected_version 变为陈旧值
  await page.evaluate(async () => {
    const mod = await import('/src/api/mock.ts')
    await mod.mockApi.patchSettings('demo-project', { expected_version: 1, timezone: 'Asia/Shanghai' })
  })

  await timezone.selectOption('UTC')
  await page.getByTestId('save-settings').click()

  const conflict = page.getByTestId('settings-conflict')
  await expect(conflict).toBeVisible()
  await expect(conflict).toContainText('重新加载')
  // 冲突不清空用户当前选择
  await expect(timezone).toHaveValue('UTC')
  await expect(page.getByTestId('settings-saved')).toHaveCount(0)

  // 重新加载后拿到最新版本,再次保存成功
  await page.getByTestId('settings-reload').click()
  await expect(conflict).toHaveCount(0)
  await expect(timezone).toHaveValue('Asia/Shanghai')
  await timezone.selectOption('UTC')
  await page.getByTestId('save-settings').click()
  await expect(page.getByTestId('settings-saved')).toBeVisible()
})

test('VIEWER 只读:不能保存设置且原因可见', async ({ page }) => {
  await page.goto('/login')
  await page.getByTestId('login-readonly').click()
  await page.goto('/p/demo-project/settings')

  await expect(page.locator('#vl-settings-timezone')).toHaveValue('UTC')
  await expect(page.getByTestId('save-settings')).toBeDisabled()
  await expect(page.getByTestId('save-settings')).toContainText('只读成员不可修改')
  await expect(page.getByTestId('settings-readonly-hint')).toBeVisible()
})
