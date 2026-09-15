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

  // CPI 是真算出来的,不是占位。此前 GET /topics 两项都写死 null,于是这一列恒为
  // 「—」、证据面板恒为「暂无 CPI 数据」——而 compute_cpi 的单元测试一直是绿的。
  const cpi = page.getByTestId('topic-cpi').first()
  await expect(cpi).not.toHaveText('—')
  await expect(cpi).toHaveText(/^\d+$/)
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

// —— 本轮修复的三条真实链路:筛选聚合 / 复盘详情不缺列 / 风险乐观锁 ——
const API_BASE = `http://127.0.0.1:${Number(process.env.REAL_API_PORT ?? 8010)}/api/v1`

/** API 级请求的 CSRF 头:会话存在时写请求必须带,page.request 与页面共享 Cookie。 */
async function csrfHeader(page: import('@playwright/test').Page): Promise<Record<string, string>> {
  const response = await page.request.get(`${API_BASE}/auth/csrf`)
  const token = (await response.json()) as { csrf_token: string }
  return { 'X-CSRF-Token': token.csrf_token }
}

test('真实后端:筛选真的改变 insight 指标(此前前端从不发筛选参数)', async ({ page }) => {
  await login(page)
  await importAndAnalyze(page)

  await page.goto('/p/demo-project/overview')
  await expect(page.getByTestId('metric-valid-feedback')).toBeVisible({ timeout: 30_000 })
  // 值定位按规范走两层:先卡片再 metric-value(卡片根的 textContent 混着标签与单位)
  const raw = await page.getByTestId('metric-valid-feedback')
    .getByTestId('metric-value').textContent()
  // 值节点里带单位(如「9条」),取数字部分
  const unfiltered = Number((raw ?? '').replace(/[^\d]/g, ''))
  expect(unfiltered).toBeGreaterThan(0)

  // CSV 的 9 行里只有 1 行在 2026-08-15:窗口收到那天,有效反馈应收敛到 1。
  // 这条用例证明的是「前端把筛选发给了服务端、聚合真的用了」——
  // 旧实现 summary 客户端没有 filters 参数,四卡从不随筛选变化。
  const response = await page.request.get(
    `${API_BASE}/projects/demo-project/summary?start=2026-08-15&end=2026-08-15`)
  expect(response.status()).toBe(200)
  const summary = await response.json()
  expect(summary.insight_metrics.valid_feedback_count).toBe(1)
  // 7.7:反馈筛选只影响 insight,任务指标恒项目范围
  expect(summary.action_metrics.scope).toBe('project_all_runs')
})

test('真实后端:创建复盘后详情页可打开且结论齐全(reviews 缺列的回归)', async ({ page }) => {
  // reviews 表此前没有 comparability/reasons/filters/alignment_confirmed 四列,
  // 真实 PostgreSQL 上 GET /reviews/{id} 丢字段,详情页读 reasons 直接 TypeError;
  // POST 侥幸正常,因为端点返回的是本地 dict 而不是仓储行。
  await login(page)
  await importAndAnalyze(page)

  await page.goto('/p/demo-project/reviews')
  await page.getByTestId('review-create').click()
  await expect(page.getByTestId('wizard-run')).toBeVisible({ timeout: 10_000 })
  // 向导选项来自服务端:run 与主题不再是写死的演示值。选项是异步回填的
  // (打开向导时列表可能还没到),先等下拉出现 revision 文案再读值
  await expect(page.getByTestId('wizard-run')).toContainText(/revision \d+/, { timeout: 10_000 })
  const runValue = await page.getByTestId('wizard-run').inputValue()
  expect(runValue).toMatch(/run|demo/)
  await expect(page.getByTestId('wizard-topic').locator('option').first()).toBeTruthy()

  // 映射确认勾选在第 1 步(与向导表单同页),下一步才是确认页
  await page.getByTestId('wizard-alignment').check()
  await page.getByTestId('wizard-next').click()
  await page.getByTestId('wizard-submit').click()

  // 详情页能渲染出结论状态,说明 GET /reviews/{id} 把 comparability/reasons
  // 完整带回来了(缺列时这里先 TypeError 崩页)
  await expect(page).toHaveURL(/\/reviews\/review_/, { timeout: 15_000 })
  await expect(page.getByTestId('review-effect')).toBeVisible()
})

test('真实后端:风险裁决缺版本 422、旧版本 409(乐观锁真的咬合)', async ({ page }) => {
  await login(page)
  await importAndAnalyze(page)

  // 界面先裁决一次(它带的总是列表里的当前版本)
  await page.goto('/p/demo-project/risks')
  const row = page.getByTestId('risk-table').locator('tbody tr').first()
  await row.getByTestId('risk-confirm').click()
  await page.getByLabel(/裁决理由/).fill('人工核验:规则命中与原文一致')
  await page.getByTestId('risk-confirm-submit').click()
  // 裁决成功后该行不再是待复核,行内「复核并裁决」按钮消失
  await expect(row.getByTestId('risk-confirm')).toHaveCount(0, { timeout: 10_000 })

  const riskId = await page.evaluate(() => {
    const first = document.querySelector('[data-testid="risk-table"] tbody tr')
    return first?.getAttribute('data-resource-id') ?? ''
  })
  expect(riskId).toBeTruthy()
  const headers = await csrfHeader(page)

  // 拿旧版本(裁决后至少 2)直接打 API:必须 409,而不是静默覆盖
  const stale = await page.request.post(
    `${API_BASE}/projects/demo-project/risks/${riskId}/reviews`,
    { headers, data: { decision: 'excluded', reason: '拿旧版本重试', expected_version: 1 } })
  expect(stale.status()).toBe(409)

  // 缺版本:422,而不是无锁放行
  const missing = await page.request.post(
    `${API_BASE}/projects/demo-project/risks/${riskId}/reviews`,
    { headers, data: { decision: 'excluded', reason: '缺版本' } })
  expect(missing.status()).toBe(422)
})
