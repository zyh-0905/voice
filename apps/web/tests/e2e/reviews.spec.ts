// reviews.spec:复盘向导与详情(工程计划 W18 验收)
// 契约更新(计划 7.5/8.7):向导只选两个时间窗并确认映射,n/N 由服务端从 run 推导;
// 旧用例中「手工填写 n/N」的行为已被移除,相应步骤改为填写窗口起止日期。
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

test('不可比复盘不显示任何变化结论并列出原因', async ({ page }) => {
  await page.goto('/p/demo-project/reviews')
  await page.locator('[data-resource-id="review-003"]').getByTestId('review-open').click()

  await expect(page.getByTestId('review-effect')).toContainText('无法比较')
  await expect(page.getByTestId('review-share-delta')).toHaveText('—')
  await expect(page.getByTestId('review-reasons')).toContainText('分母为 0')
  await expect(page.getByTestId('review-limitations')).toContainText('数据不足')
  // 不可比时不得渲染变化数字
  await expect(page.getByTestId('review-count-change')).toHaveCount(0)
})

test('创建向导:选两个等长窗口并确认映射后由服务端推导 n/N', async ({ page }) => {
  await page.goto('/p/demo-project/reviews')
  await page.getByTestId('review-create').click()

  // 手工 n/N 输入已移除,改为窗口起止日期
  await expect(page.getByTestId('wizard-before-n')).toHaveCount(0)
  await page.getByTestId('wizard-before-start').fill('2026-07-01')
  await page.getByTestId('wizard-before-end').fill('2026-07-11')
  await page.getByTestId('wizard-after-start').fill('2026-08-01')
  await page.getByTestId('wizard-after-end').fill('2026-08-11')
  await page.getByTestId('wizard-alignment').check()
  await page.getByTestId('wizard-next').click()

  // 第二步确认映射与窗口口径
  await expect(page.getByText('请确认以下映射与口径')).toBeVisible()
  await expect(page.getByText('2026-07-01 → 2026-07-11')).toBeVisible()
  await page.getByTestId('wizard-submit').click()
  await expect(page).toHaveURL(/\/reviews\/review-/)

  // 10 天窗口 → N=300(服务端推导),数量下降但占比上升,两者同时呈现
  await expect(page.getByTestId('review-window-compare')).toContainText('50 / 300')
  await expect(page.getByTestId('review-window-compare')).toContainText('31 / 300')
  await expect(page.getByTestId('review-count-change')).toHaveText('-19')
  await expect(page.getByTestId('review-before-pp')).toContainText('16.7%')
  await expect(page.getByTestId('review-after-pp')).toContainText('10.3%')
})

test('窗口时长不等时不输出结论,详情列出不可比原因', async ({ page }) => {
  await page.goto('/p/demo-project/reviews')
  await page.getByTestId('review-create').click()

  await page.getByTestId('wizard-before-start').fill('2026-07-01')
  await page.getByTestId('wizard-before-end').fill('2026-07-31')
  await page.getByTestId('wizard-after-start').fill('2026-08-01')
  await page.getByTestId('wizard-after-end').fill('2026-08-15')
  await page.getByTestId('wizard-alignment').check()
  await page.getByTestId('wizard-next').click()

  await expect(page.getByTestId('wizard-window-warning')).toContainText('前后窗口时长不等')
  await page.getByTestId('wizard-submit').click()
  await expect(page).toHaveURL(/\/reviews\/review-/)

  await expect(page.getByTestId('review-effect')).toContainText('无法比较')
  await expect(page.getByTestId('review-reasons')).toContainText('前后窗口时长不等')
  await expect(page.getByTestId('review-share-delta')).toHaveText('—')
  await expect(page.getByTestId('review-count-change')).toHaveCount(0)
})

test('低样本只展示数量与分母,不渲染变化数字', async ({ page }) => {
  await page.goto('/p/demo-project/reviews')
  await page.getByTestId('review-create').click()

  // 1 天窗口 → N=30 < 50,服务端标记 low_sample
  await page.getByTestId('wizard-before-start').fill('2026-07-01')
  await page.getByTestId('wizard-before-end').fill('2026-07-02')
  await page.getByTestId('wizard-after-start').fill('2026-08-01')
  await page.getByTestId('wizard-after-end').fill('2026-08-02')
  await page.getByTestId('wizard-alignment').check()
  await page.getByTestId('wizard-next').click()
  await page.getByTestId('wizard-submit').click()
  await expect(page).toHaveURL(/\/reviews\/review-/)

  await expect(page.getByTestId('review-window-compare')).toContainText('5 / 30')
  await expect(page.getByTestId('review-window-compare')).toContainText('3 / 30')
  await expect(page.getByTestId('review-low-sample-note')).toContainText('样本量不足')
  await expect(page.getByTestId('review-share-delta')).toHaveText('—')
  await expect(page.getByTestId('review-count-change')).toHaveCount(0)
})
