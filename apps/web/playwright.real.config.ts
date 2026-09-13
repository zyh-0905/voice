// playwright.real.config.ts — 真实 API 闭环(工程计划 14.3)。
//
// 与 playwright.config.ts 分开,而不是塞进同一个 projects 数组:那一套跑 mock
// (前端默认客户端),这一套让前端请求真实 FastAPI。两者端口、配置、生命周期都不同,
// 混在一起会让每次 E2E 都多起两个进程。
//
// 存在意义:mock 套件验证的是「前端自洽」,真实套件验证的是「前后端契约一致」——
// 客户端类型、响应信封、CSRF、Cookie、错误体形状这些只有真连一次才会暴露。
//
// **后端连真实 PostgreSQL。** 此前这一套跑在 USE_DATABASE=0(内存仓储)上,于是
// 「真实」只到 HTTP 层为止:内存仓储不校验列约束也不校验外键,而这一轮三次缺陷
// (save_stages 的运算符优先级、tasks.owner 的可空性、删除顺序)全都是只在真实库上
// 才炸的那一类。套件跑在内存上,恰好把要防的东西绕过去了。
//
// 需要可达的 PostgreSQL,见 scripts/e2e_server.py;本地起库:
//   docker compose -f compose.yaml -f compose.e2e.yaml up -d postgres
import { defineConfig, devices } from '@playwright/test'

// 端口可配:CI 里后端容器用 host 网络(那时 -p 被忽略),容器必须直接绑这个端口
const API_PORT = Number(process.env.REAL_API_PORT ?? 8010)
const WEB_PORT = 4174
const API_URL = `http://127.0.0.1:${API_PORT}`
const WEB_URL = `http://127.0.0.1:${WEB_PORT}`

// 测试库的管理员连接串:库名由 scripts/e2e_server.py 固定为带前缀的
// `voicelens_test_e2e`,每次运行重建。
// 本地走 compose 网络(数据库端口不发布到宿主机);CI 里 postgres 在 runner 的
// localhost 上,用 host 网络。
const ADMIN_URL = process.env.REAL_API_DATABASE_URL
  ?? 'postgresql+psycopg://voicelens:voicelens@postgres:5432/voicelens'
const DOCKER_NETWORK = process.env.REAL_API_DOCKER_NETWORK ?? 'voice_default'

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
  // 后端容器被 SIGKILL 时不会自己消失,收尾统一删一次(见 global-teardown.ts)
  globalTeardown: './tests/real-api/global-teardown.ts',
  projects: [{ name: 'real-api', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      // 后端:**在容器里**用专用 PostgreSQL 测试库起(每次重建库 + 全量迁移)。
      //
      // 为什么必须进容器:宿主机上通常没有 API 依赖(本机是 python3.9 且没装
      // uvicorn),而数据库端口按设计不发布到宿主机。此前这条命令跑的是
      // `python -m uvicorn`,本地从未真正执行过——只是 reusable 的旧进程让它看起来
      // 在跑,而那可能是内存模式的。
      // 整条命令交给一个 sh -c:上一次超时被杀时 `docker run` 客户端收不到 SIGKILL,
      // 容器会变成孤儿占住名字,所以先清一次
      command:
        `sh -c "docker rm -f vl_e2e_api >/dev/null 2>&1; ` +
        `exec docker run --rm --name vl_e2e_api --network ${DOCKER_NETWORK} ` +
        `-p ${API_PORT}:${API_PORT} -e AUTH_REQUIRED=false -e AUTH_INSECURE_DEV=true ` +
        `-e RUN_WORKER_INLINE=1 -e REAL_API_DATABASE_URL='${ADMIN_URL}' ` +
        `-e CORS_ORIGINS='${WEB_URL},http://localhost:${WEB_PORT}' ` +
        // 容器内必须绑 0.0.0.0:绑 127.0.0.1 时 -p 的端口映射到不了它
        `voice-api:latest python scripts/e2e_server.py --port ${API_PORT} --host 0.0.0.0"`,
      cwd: '../..',
      url: `${API_URL}/api/v1/health`,
      // **不复用**:复用意味着可能连上一个内存模式的后端,而配置说它连的是 PostgreSQL
      // ——那正是「看起来配好了,实际没生效」。每次都由脚本重建库再起。
      reuseExistingServer: false,
      timeout: 120_000,  // 建库 + 全量迁移比单起 uvicorn 慢
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
