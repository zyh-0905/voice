import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  use: { baseURL: 'http://127.0.0.1:4173', trace: 'on-first-retry', screenshot: 'only-on-failure' },
  webServer: { command: 'npm run dev -- --host 127.0.0.1 --port 4173', url: 'http://127.0.0.1:4173', reuseExistingServer: false },
  // 功能 E2E 使用单一默认视口;断点矩阵(1440 侧栏 / 1280 抽屉 / 768 / 375)
  // 由 evidence-ui 用例内 setViewportSize 覆盖,截图基线(视觉回归)留待 visual.spec 的 project 视口。
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
