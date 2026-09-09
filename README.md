# VoiceLens

VoiceLens 是一个面向授权反馈数据的分析与治理 Web MVP。系统围绕“导入数据 → 脱敏治理 → 主题分析 → 证据追溯 → 风险与任务 → 人工复核 → 脱敏导出”建立闭环。

## 当前能力

- Vue 3 + TypeScript + Vite 前端工作台
- FastAPI `/api/v1` 后端 API
- CSV、XLSX、TXT 导入与严格格式校验
- 邮箱、手机号、订单号脱敏
- HMAC 来源去重、幂等键、分页和写接口限流
- 确定性 CPU 主题分析、摘要和证据 offset
- 可替换的结构化 LLM provider 与离线质量评估
- 项目、风险、任务、复核、复盘、导出和删除流程
- SQLAlchemy + Alembic + PostgreSQL Repository
- Celery/Redis、outbox relay 和 Nginx 同源部署
- GitHub Actions、Vitest、Playwright、axe 和样式 token 门禁

## 目录

```text
apps/web/                 Vue 前端
services/api/app/        FastAPI、分析、认证和持久化代码
services/api/migrations/  Alembic 迁移
services/api/tests/      后端测试
apps/web/tests/           前端单元和 E2E 测试
compose.yaml              API、Web、PostgreSQL、Redis、worker、relay
```

## 本地启动

### 前端

要求 Node.js 22+：

```bash
npm --prefix apps/web ci
npm --prefix apps/web run dev
```

前端默认使用 mock client。需要请求真实 API 时设置 `apps/web/.env`：

```dotenv
VITE_USE_MOCK=false
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

### 后端

要求 Python 3.12+：

```bash
python -m pip install -r services/api/requirements.txt
```

PowerShell：

```powershell
$env:PYTHONPATH = "services/api"
uvicorn app.main:app --reload --port 8000
```

Linux/macOS：

```bash
PYTHONPATH=services/api uvicorn app.main:app --reload --port 8000
```

API 文档：`http://localhost:8000/docs`；OpenAPI：`http://localhost:8000/openapi.json`。

## Docker Compose

复制 `.env.example` 为 `.env` 后启动：

```bash
docker compose up --build
```

Web 入口为 `http://localhost:8080`。Compose 包含 API、Nginx Web、PostgreSQL、Redis、Celery worker 和 outbox relay。当前环境如果没有 Docker daemon，可运行静态 Compose 校验：

```bash
python scripts/validate-compose.py
```

## 测试与质量门禁

后端：

```powershell
$env:PYTHONPATH = "services/api"
python -m pytest services/api/tests -q
python -m compileall services/api/app -q
```

前端：

```bash
npm --prefix apps/web run lint:style
npm --prefix apps/web run typecheck
npm --prefix apps/web run test:unit -- --run
npm --prefix apps/web run build
npm --prefix apps/web run test:e2e -- --project=chromium --workers=1
```

离线分析质量评估：

```powershell
$env:PYTHONPATH = "services/api"
python services/api/evaluation/evaluate_analysis.py
```

## 认证与生产配置

演示账号由 API auth 模块提供。生产环境必须满足：

- `AUTH_REQUIRED=true`
- `DEDUPE_HMAC_SECRET` 使用独立随机密钥
- `DATABASE_URL` 使用 PostgreSQL
- 使用真实身份提供商替换内存 token store

数据集、分析和领域实体都通过项目范围隔离；未授权项目返回 `404`，viewer 不能执行写操作。演示数据是合成数据，不能作为真实业务结论或人工复核结果。

## 重要 API

所有路径以 `/api/v1` 开头：

- `POST /auth/login`、`GET /auth/me`、`POST /auth/logout`
- `GET /projects`、`GET /projects/{project_id}`
- `POST /projects/{project_id}/datasets`
- `POST /projects/{project_id}/datasets/{dataset_id}/validate`
- `DELETE /projects/{project_id}/datasets/{dataset_id}`
- `POST /projects/{project_id}/analyses`
- `GET /projects/{project_id}/analyses/{analysis_id}`
- `GET /projects/{project_id}/risks`
- `GET /projects/{project_id}/tasks`
- `GET /projects/{project_id}/reviews`
- `POST /projects/{project_id}/reviews/{review_id}/confirm`
- `GET /projects/{project_id}/exports/redacted.csv`
- `GET /health`、`GET /health/ready`

完整契约以 FastAPI OpenAPI 文档为准。

## 开发说明

详细工程约束和前端风格要求见：

- `VoiceLens_Web_工程开发计划_v1.1.md`
- `VoiceLens_Web_前端风格规范_v1.0.md`

本仓库的 mock、demo 和离线评估路径用于开发与演示；生产部署仍需接入真实身份、密钥、PostgreSQL/Redis/Celery 运行环境，并基于获授权数据完成模型评估。
