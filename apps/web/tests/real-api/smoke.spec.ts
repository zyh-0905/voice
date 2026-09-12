// 真实 API 闭环(工程计划 14.3)。
//
// 这一套**不用 mock**:前端以 VITE_USE_MOCK=false 直连 uvicorn 上的 FastAPI。
// mock 套件验证前端自洽;这里验证的是**前后端契约一致**与**闭环真的走得通**——
// Cookie 会话、CSRF、multipart 上传、响应信封、错误体形状,只有真连一次才暴露。
//
// 重要前提:内存仓储启动时 demo-project 没有数据集,所以工作台是空态。用例必须
// 自己造数据,不能假设演示种子已有反馈——这正是它比 mock 套件更接近真实的地方。
import { test, expect } from '@playwright/test'

// 6 条近似 + 3 条无关:这个形状经实测能聚成两个簇;其中一条命中风险规则 duplicate_charge
const CSV_ROWS = [
  ...Array.from({ length: 6 }, (_, i) => `物流信息一直没有更新反馈编号${i},2026-08-${String(5 + i).padStart(2, '0')}T10:00:00+08:00`),
  ...Array.from({ length: 2 }, (_, i) => `退款到账时间偏长希望加快编号${i},2026-08-${String(12 + i).padStart(2, '0')}T10:00:00+08:00`),
  '订单被重复扣款了两次请核查,2026-08-15T10:00:00+08:00',
]
const CSV = `text,occurred_at\n${CSV_ROWS.join('\n')}\n`

async function login(page: import('@playwright/test').Page) {
  await page.goto('/login')
  await page.getByLabel('用户名').fill('demo')
  await page.getByLabel('密码').fill('demo')
  await page.getByTestId('login-submit').click()
  await expect(page).toHaveURL(/overview/)
}

/** 走完四步向导:上传 → 映射 → 治理报告 → 选择批次分析 */
async function importAndAnalyze(page: import('@playwright/test').Page) {
  await page.goto('/p/demo-project/imports')
  // 文件名带唯一后缀:同源同名同内容会走「重传去重」直接回显已有数据集,
  // 用例之间就会互相干扰(去重键是 project+namespace+kind+name)
  await page.getByTestId('file-input').setInputFiles({
    name: `real-closed-loop-${Date.now()}.csv`, mimeType: 'text/csv', buffer: Buffer.from(CSV),
  })
  // 授权必须主动勾选(计划 4.3),未勾选时上传被拦
  await page.getByTestId('consent-checkbox').check()
  await page.getByTestId('upload-button').click()

  await expect(page.getByTestId('field-mapping')).toBeVisible()
  await page.getByTestId('mapping-next').click()
  await expect(page.getByTestId('import-health')).toBeVisible()
  await page.getByTestId('report-next').click()

  await expect(page.getByTestId('dataset-list')).toBeVisible()
  await page.getByRole('button', { name: '选择并分析' }).first().click()

  // 向导的「选择并分析」只跳转到分析页,真正的发起动作在那一页上。
  // (这是当前的实现:按钮文案承诺了分析,实际只跳转——见报告中的说明。)
  await expect(page.getByTestId('analysis-page')).toBeVisible()
  await page.getByRole('button', { name: '开始分析' }).click()
  await expect(page.getByTestId('analysis-page')).toContainText('done', { timeout: 30_000 })
}

test('真实后端:四步向导走通,工作台渲染服务端算出的指标与主题', async ({ page }) => {
  await login(page)
  await importAndAnalyze(page)

  await page.goto('/p/demo-project/overview')
  // 指标来自 GET /summary,主题来自 GET /topics——都是刚上传的数据算出来的
  await expect(page.getByTestId('metric-valid-feedback')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId('topic-table')).toBeVisible({ timeout: 30_000 })
  // 上传前这里是空态;有数据后不应再出现
  await expect(page.getByText('还没有导入客户反馈')).toHaveCount(0)
})

test('真实后端:扫描出的风险进入复核队列(而非只留在 run 里)', async ({ page }) => {
  await login(page)
  await importAndAnalyze(page)

  await page.goto('/p/demo-project/risks')
  const table = page.getByTestId('risk-table')
  await expect(table).toBeVisible({ timeout: 30_000 })
  // 这条候选来自真实扫描:upload 的 CSV 里有一条「重复扣款」
  await expect(table).toContainText('duplicate_charge', { timeout: 30_000 })
})

test('真实后端:主题证据引文可在源反馈正文里定位', async ({ page }) => {
  // 证据区在 ≥1440px 才是非模态侧栏,更窄会切换成模态抽屉(规范 9.2 断点表);
  // Playwright 默认视口 1280 会走抽屉分支,所以这里显式设宽。
  await page.setViewportSize({ width: 1440, height: 900 })
  await login(page)
  await importAndAnalyze(page)

  await page.goto('/p/demo-project/overview')
  await expect(page.getByTestId('topic-table')).toBeVisible({ timeout: 30_000 })
  await page.getByRole('button', { name: '查看证据' }).first().click()
  await expect(page.getByTestId('evidence-panel')).toBeVisible()

  // GET /feedback/{id}:返回脱敏正文;切分 offset 可复原
  await page.getByTestId('evidence-open-source').first().click()
  await expect(page.getByTestId('evidence-source')).toBeVisible()
  await expect(page.getByTestId('evidence-source')).toContainText('源行')
})
