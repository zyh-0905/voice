import { test as base, expect } from '@playwright/test'

// 纯合成 UI 测试共享 fixture:以 ANALYST 演示身份登录并进入工作台。
// viewer 场景在用例内自行通过 login-readonly 登录,不与本 fixture 混用。
export const test = base.extend({
  page: async ({ page }, use) => {
    await page.goto('/login')
    await page.getByLabel('用户名').fill('demo')
    await page.getByLabel('密码').fill('demo')
    await page.getByTestId('login-submit').click()
    await expect(page).toHaveURL(/overview/)
    await use(page)
  },
})
export { expect }
