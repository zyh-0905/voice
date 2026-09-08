import { test as base, expect } from '@playwright/test'

export const test = base.extend({
  page: async ({ page }, use) => {
    await page.goto('/login')
    await page.getByRole('button').click()
    await expect(page).toHaveURL(/overview/)
    await use(page)
  },
})
export { expect }
