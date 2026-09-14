import { test, expect } from './ui-fixtures'

// 分析进度页(工程计划 7.3 / QA-12):状态以服务端为准,终态停止轮询。
//
// 这里跑的是 mock,而 mock 的 run **会真的推进**(排队 → 分析中 → 已完成,见
// api/mock.ts 的 MockRunStore)。这一点是刻意的:早先 mock 的 runAnalysis 直接返回
// done,于是「观察到状态变化」「终态停止轮询」这两条——也就是这个页面唯一要做的事
// ——在 mock 套件里永远不会被执行到,而 E2E 默认跑的就是 mock。
test('分析页从服务端观察状态推进,并在终态停下', async ({ page }) => {
  await page.goto('/p/demo-project/analysis?dataset=demo-1')

  // 尚未开始:没有 run 时状态是空态,不是编出来的「排队中」
  await expect(page.getByTestId('analysis-status')).toHaveText('尚未开始')
  await page.getByRole('button', { name: '开始分析' }).click()

  // POST 返回的是排队态。这一刻页面还不该显示已完成——
  // 若显示,说明它用的是别处的状态而不是刚建出来的这个作业。
  await expect(page.getByTestId('analysis-status')).toHaveText('排队中')

  // run id 进 URL:刷新与分享回到同一个作业
  await expect(page).toHaveURL(/run=/)

  // 轮询把它推到终态。这条断言只有真的在查服务端才会成立。
  await expect(page.getByTestId('analysis-status')).toHaveText('已完成', { timeout: 20_000 })
  await expect(page.getByTestId('analysis-percent')).toContainText('100%')
})

test('刷新后不读浏览器里的残留状态', async ({ page }) => {
  await page.goto('/p/demo-project/analysis?dataset=demo-2')
  await page.getByRole('button', { name: '开始分析' }).click()
  await expect(page.getByTestId('analysis-status')).toHaveText('已完成', { timeout: 20_000 })

  await page.reload()

  // 断言的是「空态」,而这不是随便挑的期望值:sessionStorage 在同标签页内刷新后
  // **仍然存在**,旧实现会把刚才存进去的「已完成」原样读回来并显示出来。
  // 显示空态,说明这一屏没有去读浏览器里的残留。
  //
  // 至于为什么这里应该退回空态:mock 的所有仓储都在模块作用域里,刷新等于
  // 「重启服务端」,它记不住刚才那个 run。真实后端会记住——那一半由 real-api
  // 套件(换一个干净浏览器上下文打开同一个 URL,应显示终态)证明,不在 mock 里假装。
  //
  // (mock 模式不发网络请求,所以也没法用「数请求」来旁证。)
  await expect(page.getByTestId('analysis-status')).toHaveText('尚未开始')
})

// 「终态后停止轮询」不在这里测:mock 模式**不发网络请求**(mock client 就是内存里的
// 一个对象),所以数请求永远数到 0——写成用例会是一条恒真的假闸门。
// 那一条需要真实 HTTP,放在 tests/real-api 里。
