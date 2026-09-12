// reviews.spec:复盘向导与详情(工程计划 W18 验收)
import { test, expect } from './ui-fixtures'

test('复盘展示百分点而非混用百分比', async ({ page }) => {
  await page.goto('/p/demo-project/reviews')
  await page.locator('[data-resource-id="review-001"]').getByTestId('review-open').click()

  await expect(page.getByTestId('review-before-share')).toContainText('16.8%')
  await expect(page.getByTestId('review-after-share')).toContainText('10.2%')
  await expect(page.getByTestId('review-share-delta')).toContainText('个百分点')
  await expect(page.getByTestId('review-share-delta')).not.toContainText('%')
  // 原始数量与分母始终可见
  await expect(page.getByTestId('review-window-compare')).toContainText('168 / 1,000')
  await expect(page.getByTestId('review-window-compare')).toContainText('102 / 1,000')
  // 相对变化必须标注「相对」
  await expect(page.getByTestId('review-relative')).toContainText('相对')
})

test('数据不足不显示改善结论', async ({ page }) => {
  await page.goto('/p/demo-project/reviews')
  await page.locator('[data-resource-id="review-003"]').getByTestId('review-open').click()

  await expect(page.getByTestId('review-effect')).toContainText('数据不足')
  await expect(page.getByTestId('review-share-delta')).toHaveText('—')
  await expect(page.getByTestId('review-limitations')).toContainText('数据不足')
})

test('创建向导:先确认映射再生成,生成后进入详情', async ({ page }) => {
  await page.goto('/p/demo-project/reviews')
  await page.getByTestId('review-create').click()

  await page.getByTestId('wizard-before-n').fill('100')
  await page.getByTestId('wizard-before-N').fill('1000')
  await page.getByTestId('wizard-after-n').fill('80')
  await page.getByTestId('wizard-after-N').fill('500')
  await page.getByTestId('wizard-next').click()

  // 第二步确认映射,明确提示不会按名称自动对齐
  await expect(page.getByText('请确认以下映射与口径')).toBeVisible()
  await page.getByTestId('wizard-submit').click()
  await expect(page).toHaveURL(/\/reviews\/review-/)

  // 数量下降但占比上升,两者同时呈现
  await expect(page.getByTestId('review-count-change')).toHaveText('-20')
  await expect(page.getByTestId('review-before-pp')).toContainText('10.0%')
  await expect(page.getByTestId('review-after-pp')).toContainText('16.0%')
})

test('分母为 0 时向导提示不输出结论', async ({ page }) => {
  await page.goto('/p/demo-project/reviews')
  await page.getByTestId('review-create').click()
  await page.getByTestId('wizard-before-N').fill('0')
  await page.getByTestId('wizard-next').click()
  await expect(page.getByTestId('wizard-insufficient')).toBeVisible()
})
