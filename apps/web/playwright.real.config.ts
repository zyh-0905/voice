// playwright.real.config.ts — 真实 API 闭环(工程计划 14.3)。
//
// 与 playwright.config.ts 分开,而不是塞进同一个 projects 数组:那一套跑 mock
// (前端默认客户端),这一套让前端请求真实 FastAPI。两者端口、配置、生命周期都不同,
// 混在一起会让每次 E2E 都多起两个进程。
//
// 存在意义:mock 套件验证的是「前端自洽」,真实套件验证的是「前后端契约一致」——
// 客户端类型、响应信封、CSRF、Cookie、错误体形状这些只有真连一次才会暴露。
import { defineConfig, devices } from '@playwright/test'

const API_PORT = 8010
const WEB_PORT = 4174
const API_URL = `http://127.0.0.1:${API_PORT}`
const WEB_URL = `http://127.0.0.1:${WEB_PORT}`

export default defineConfig({
  testDir: './tests/real-api',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  // 真实后端共享一份内存仓储;串行跑避免用例之间互相干扰
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: WEB_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'real-api', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      // 后端:内存仓储 + 演示种子。这样 CI 不必额外起 PostgreSQL/Redis,
      // 而本套件要验证的是 HTTP 契约,不是持久化(那由 schema_connection 覆盖)。
      command: `python -m uvicorn app.main:app --host 127.0.0.1 --port ${API_PORT}`,
      cwd: '../..',
      env: {
        ...process.env,
        PYTHONPATH: 'services/api',
        AUTH_REQUIRED: 'false',
        AUTH_INSECURE_DEV: 'true',
        USE_DATABASE: '0',
        // 分析在 API 进程内同步跑完,套件无需等待队列(队列接线由后端用例覆盖)
        RUN_WORKER_INLINE: '1',
        // 跨源开发:前端在另一个端口,必须显式白名单 + 允许凭据
        CORS_ORIGINS: `${WEB_URL},http://localhost:${WEB_PORT}`,
      },
      url: `${API_URL}/api/v1/health`,
      // 本地已有服务时复用,CI 上一律新起,避免用到过期进程
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${WEB_PORT}`,
      env: {
        ...process.env,
        // 关键:关掉 mock 并指向真实后端
        VITE_USE_MOCK: 'false',
        VITE_API_BASE_URL: `${API_URL}/api/v1`,
      },
      url: WEB_URL,
      // 本地已有服务时复用,CI 上一律新起,避免用到过期进程
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
})
