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
//
// `批次` 列每次都取唯一值,这一点是必需的,不是装饰:这批 CSV 没有来源编号,
// 计划 4.4 对无来源编号的反馈按 `file_sha256 + sheet_name + source_row` 认事件身份,
// 所以**内容完全相同的重传会被判为同一条事件**(计入 duplicate,不新增反馈)。
// 用例之间若共用同一份字节,后两个用例的批次会贡献 0 条反馈,分析自然没有主题。
// 文件名不同不足以区分——sha256 算的是内容,不是文件名。
const CSV_ROWS = [
  ...Array.from({ length: 6 }, (_, i) => `物流信息一直没有更新反馈编号${i},2026-08-${String(5 + i).padStart(2, '0')}T10:00:00+08:00`),
  ...Array.from({ length: 2 }, (_, i) => `退款到账时间偏长希望加快编号${i},2026-08-${String(12 + i).padStart(2, '0')}T10:00:00+08:00`),
  '订单被重复扣款了两次请核查,2026-08-15T10:00:00+08:00',
]
/** 每次调用都取唯一值:同一个 worker 里三个用例共享模块作用域,常量会让后两个批次全部撞成重复。 */
function buildCsv(): string {
  const tag = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  return `text,occurred_at,批次\n${CSV_ROWS.map(row => `${row},${tag}`).join('\n')}\n`
}

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
    name: `real-closed-loop-${Date.now()}.csv`, mimeType: 'text/csv', buffer: Buffer.from(buildCsv()),
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
  // 断言的是界面文案,不是原始 status 值:此前页面直接把 POST 返回的 status
  // 印出来,而 POST 返回的是那一刻的排队态——所以「页面显示 done」这件事只说明
  // POST 回来了,不说明页面看得到作业结束。
  await expect(page.getByTestId('analysis-status')).toHaveText('已完成', { timeout: 30_000 })
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

test('真实后端:分析进度以服务端为准,换一个干净的浏览器也能还原', async ({ page, browser }) => {
  await login(page)
  await importAndAnalyze(page)
  await expect(page.getByTestId('analysis-status')).toHaveText('已完成', { timeout: 30_000 })

  // run id 必须在 URL 里:刷新与分享回到的是同一个作业,而不是浏览器的残留
  const url = page.url()
  expect(url).toContain('run=')

  // **关键的一步:换一个全新的浏览器上下文。** 那里没有 sessionStorage。
  // 旧实现把 run 存进 sessionStorage 且只读它,新上下文会让这一屏退回「尚未开始」;
  // 状态若来自 GET /analyses/{id},同一个 URL 应当照样还原成终态。
  // 也就是说:这条用例区分的是「服务端状态」与「浏览器里存的字符串」,
  // 而不是「页面能显示 done」——后者在旧实现下也是绿的。
  const fresh = await browser.newContext()
  const freshPage = await fresh.newPage()
  await login(freshPage)
  await freshPage.goto(url)
  await expect(freshPage.getByTestId('analysis-status')).toHaveText('已完成', { timeout: 30_000 })
  await fresh.close()
})

// 「终态后停止轮询」不在这里测,原因是实测出来的:本套件带 RUN_WORKER_INLINE=1,
// POST 返回时作业已经是终态,页面根本不会排期第一次轮询——在这里数请求数恒为 0,
// 是一条永远通过的假闸门(我照这个思路写过一条,它确实「通过」了,而通过的
// 原因是轮询压根没发生)。那一条改由 tests/unit/analysis-progress.spec.ts 用
// 假定时器直接驱动页面来证明,并且验证过:去掉收敛条件它会失败。
