# VoiceLens Web

当前仓库包含 VoiceLens Web 的首个可运行前端垂直切片：登录演示、项目选择、概览工作台、数据导入向导、字段映射、治理报告和分析进度。

## 启动

要求 Node.js 22.x 与 npm。安装依赖并启动：

```bash
npm --prefix apps/web install
npm --prefix apps/web run dev
```

验证命令：

```bash
npm --prefix apps/web run typecheck
npm --prefix apps/web run test:unit -- --run
npm --prefix apps/web run build
```

当前 API 位于 `src/api`，使用 mock client；后续 FastAPI `/api/v1` 接入时保持 `ApiClient` 契约即可替换。演示数据均有 demo/mock 标识，不代表真实人工复核结果。
## API 启动

```bash
python -m pip install -r services/api/requirements.txt
uvicorn services.api.app.main:app --reload
```

API 测试：

```bash
$env:PYTHONPATH='services/api'; python -m pytest services/api/tests -q
```
## Docker Compose

开发环境可使用 `docker compose up --build` 同时启动 API、PostgreSQL 和 Redis。当前 API repository 默认仍为内存实现，数据库与队列服务已预留健康检查和连接配置，后续可替换为生产 repository/worker。

### API 环境变量

复制 `.env.example` 后按部署环境调整：`DATABASE_URL` 默认指向本机 PostgreSQL，`REDIS_URL` 指向 Redis；`AUTH_REQUIRED=true` 是生产默认值。仅在本地演示时可显式设置 `AUTH_REQUIRED=false`，关闭匿名请求的认证要求。

Frontend validation now passes with Node.js 24/npm 11: typecheck, unit tests, and production build.
