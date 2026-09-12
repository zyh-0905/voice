# 真实模式运行验收记录

> 执行时间:2026-09-12。环境:本机 Docker Compose(`api` + `migrate` + `web`(nginx) +
> `postgres` + `redis` + `worker` + `relay`),`USE_DATABASE=1`、`SESSION_STORE=db`、
> `AUTH_REQUIRED=true`、`AUTH_INSECURE_DEV=true`(本地 http 场景显式开发开关)。
> 全部为**合成演示数据**,不代表业务结论。

## 1. 服务与迁移

| 检查 | 结果 |
|---|---|
| `docker compose up -d --build` 后 `web: HTTP 200` | 通过 |
| `GET /api/v1/health/ready` | `{"status":"ready","database":{"status":"reachable"}}` |
| `alembic current` | `0007_session_idle_exp (head)` |
| PostgreSQL `session_tokens` 列 | token / user_id / role / projects / issued_at / exp / **idle_exp** |
| PostgreSQL `tasks` 列 | 15 列(含 state / version / events / idempotency_keys) |

## 2. 认证与会话

| 检查 | 结果 |
|---|---|
| `POST /auth/login` 响应头 | `set-cookie: vl_session=…; HttpOnly; Max-Age=28800; Path=/; SameSite=lax` |
| 仅凭 Cookie 访问 `/auth/me`(无 Authorization 头) | 200 |
| `GET /auth/config` | `{"mode":"local"}` |
| 带会话 Cookie 的写请求缺少 `X-CSRF-Token` | 403 `csrf_failed` |
| 携带匹配令牌的写请求 | 成功 |
| `POST /auth/logout` | 204,`vl_session` 被清除 |

## 3. 聚合与业务端点(经 nginx,真实仓储)

| 端点 | 实测值 |
|---|---|
| `GET /summary` | run `run_fbdbde9bf9` · revision 1 · denominator 15 · valid_feedback 15 · topic_count 5 · pending_risk_feedback 3 · active_task 3 · overdue 1 |
| `GET /summary?revision=1`(缺 run_id) | 422 |
| `GET /summary?run_id=run_ghost` | 404 |
| `GET /topics` | 已发布 revision 的 5 个主题(退款进度 / 设备突然 / 包裹破损 / 物流信息 / 客服响应) |
| `GET /topics/{t}/evidence` | 返回 source_row 与 quote 偏移 |
| `GET /tasks` | 3 条,`task-001` 逾期为 `true`(due_at 早于 task_as_of) |
| `GET /risks` | 3 条,severity 与 reviewState 分离,CRITICAL 可得 |
| `GET /reviews` | `review-001` `OBSERVED_CHANGE` / `share_delta_pp = -6.6`;`review-002` `INSUFFICIENT_DATA` |
| `GET /exports/redacted.csv` | `text/csv`,仅本项目行、PII 已脱敏 |

## 4. 异步流水线(上传 → 发布)

实测:上传 15 行 CSV → validate 202 → 创建分析(带 `Idempotency-Key`)
→ relay 发布(`published: 1`,PG 状态 `published`)
→ celery worker 消费(`Task voicelens.run_analysis … succeeded`,0.26s)
→ 分析终态 `status: done / stage: completed / revision: 1`
→ 主题 5 个(差异化命名)、待归类 0、风险候选 3 条(critical,全 `PENDING`)。

幂等:同 key 同体重复请求返回同一 run;异体 409;api 重启后同 key 仍返回同一 run。

## 5. 浏览器端(Cookie + CSRF 冒烟,4/4)

| 检查 | 结果 |
|---|---|
| 登录写入 HttpOnly 会话 Cookie,前端 `sessionStorage` 无令牌 | 通过 |
| 概览读取真实聚合数据(仅凭 Cookie 认证) | 通过 |
| 创建任务草稿:CSRF 引导 200 → 创建 201 → 列表刷新 | 通过 |
| 登出撤销会话并清除 Cookie | 通过 |

## 6. 自动化门禁

| 套件 | 结果 |
|---|---|
| 后端 `pytest services/api/tests -q` | **201 passed** |
| 前端 `lint:style` / `typecheck` / `test:unit` / `build` | 通过 / 通过 / **37 passed** / 通过 |
| 前端 `test:e2e`(含 visual 3 基线、a11y、任务/复盘/主题详情) | **23 passed** |

## 7. 已知限制(未验收项)

- 截图为 darwin 平台基线,尚未在 CI 环境重生成;`visual.spec` 不参与 CI(文件名平台相关)。
- `LOCAL_ACCOUNTS` 未经真实企业目录验证;OIDC 路径仅有本地生成密钥的单元验证,
  未与真实 IdP 联调(需要企业提供 issuer/JWKS/audience)。
- 反馈行仅含 `text` 列,`channel`/`product`/时间筛选在演示数据上是空操作
  (代码路径有单元测试覆盖)。
- 1920px 布局、完整 Tab 顺序、真实 reduced-motion 三项仍需人工走查(见 `ui-checklist.md`)。
