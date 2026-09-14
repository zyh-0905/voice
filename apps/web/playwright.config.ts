import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    // ECharts 有约 1s 的入场动画,而 useChart 只在 reduced-motion 下关掉它。
    // 不设这一项时,`waitForSelector('canvas')` 在 canvas 出现的瞬间就返回,而动画
    // 刚开始——截图可能落在中间帧上,视觉用例于是偶发失败(实测:同一次运行里
    // 34 条过、overview desktop 挂掉,单独重跑又过)。
    //
    // 用产品自己已有的 reduced-motion 分支来消除它,而不是在用例里塞 sleep,
    // 也不是关掉动画污染产品代码:这条分支本来就该被跑到的。
    reducedMotion: 'reduce',
  },
  webServer: { command: 'npm run dev -- --host 127.0.0.1 --port 4173', url: 'http://127.0.0.1:4173', reuseExistingServer: false },
  // 功能 E2E 使用单一默认视口;断点矩阵(1440 侧栏 / 1280 抽屉 / 768 / 375)
  // 由 evidence-ui 用例内 setViewportSize 覆盖,截图基线(视觉回归)留待 visual.spec 的 project 视口。
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
