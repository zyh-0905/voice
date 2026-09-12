// visual.spec.ts — W20 截图基线(风格规范 12.3)。
// 固定视口 + 合成 mock 数据;基线首次生成后需人工核准(UI-24),
// 后续失败不得用 --update-snapshots 自动覆盖。
import { test, expect } from './ui-fixtures'

// 基线是平台相关的:Playwright 在快照文件名后追加平台名,已提交的是 -darwin。
// 在别的平台(CI 是 Ubuntu)上跑只会得到「快照不存在」而失败,并把同一个 E2E 任务里
// 其余用例的信号一起淹掉。所以显式声明基线覆盖哪些平台——新增平台时,在该平台执行
// `npx playwright test visual --update-snapshots`,人工核准后把平台加进这一行。
// 不要为了让它变绿就放宽断言,也不要用 --update-snapshots 自动覆盖。
const BASELINE_PLATFORMS = ['darwin']
test.skip(!BASELINE_PLATFORMS.includes(process.platform),
  `视觉基线仅覆盖 ${BASELINE_PLATFORMS.join('/')};当前平台为 ${process.platform}`)

test.describe('工作台 1440×900(桌面四卡+证据侧栏档)', () => {
  test.use({ viewport: { width: 1440, height: 900 } })
  test('overview desktop', async ({ page }) => {
    await page.waitForSelector('[data-testid="topic-table"]')
    await page.waitForSelector('.vl-trend-chart__canvas canvas')
    await expect(page).toHaveScreenshot('overview-1440.png', { fullPage: true })
  })
})

test.describe('工作台 375×812(单列+全宽抽屉档)', () => {
  test.use({ viewport: { width: 375, height: 812 } })
  test('overview mobile', async ({ page }) => {
    await page.waitForSelector('[data-testid="topic-table"]')
    await expect(page).toHaveScreenshot('overview-375.png', { fullPage: true })
  })
})

test.describe('证据抽屉 1280×720(模态抽屉档)', () => {
  test.use({ viewport: { width: 1280, height: 720 } })
  test('evidence drawer open', async ({ page }) => {
    await page.locator('[data-resource-id="delivery"]').getByRole('button', { name: '查看证据' }).click()
    await expect(page.getByTestId('evidence-drawer')).toBeVisible()
    // 等待 180ms 显隐过渡完成,避免 opacity 中间态进入基线
    await expect(page.locator('.vl-overlay')).toHaveCSS('opacity', '1')
    await expect(page).toHaveScreenshot('evidence-drawer-1280.png')
  })
})
