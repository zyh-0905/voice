// visual.spec.ts — W20 截图基线(风格规范 12.3)。
// 固定视口 + 合成 mock 数据;基线首次生成后需人工核准(UI-24),
// 后续失败不得用 --update-snapshots 自动覆盖。
import { test, expect } from './ui-fixtures'

// 基线是平台相关的:Playwright 在快照文件名后追加平台名。darwin 与 linux 各有一套
// (同一页面在两个平台上高度差 1px,是字体渲染差异,不是缺陷)。
//
// 此前只声明了 darwin,于是**CI(Ubuntu)上这三条是 skip**——闸门「绿」是因为它关着,
// 而不是因为画面没变。现在两个平台都有基线,闸门在 CI 上真的会跑。
//
// 灵敏度(实测,别假设它更强):它抓得住布局位移与明显的视觉变化(整页换色 →
// 88% 像素判为差异),但**默认阈值放过细微的颜色漂移**——把页面底色从 #FBFBFD 改成
// #f2f2f2(单通道约 3.5%)不会让它失败。逐像素颜色由 design-tokens.spec.ts 锁死、
// 硬编码颜色由 lint:style 拦截,这里不重复;但它**不能**被当作颜色回归的保障。
//
// 换平台/换渲染环境时必须重新生成,且人工核准后提交:
//   docker run --rm -v "$PWD:/work" -w /work/apps/web \
//     mcr.microsoft.com/playwright:v<与 @playwright/test 同版本>-jammy \
//     sh -c "npm ci && npx playwright test visual --update-snapshots"
// 不要为了让它变绿就放宽断言,也不要用 --update-snapshots 自动覆盖既有基线。
const BASELINE_PLATFORMS = ['darwin', 'linux']
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
