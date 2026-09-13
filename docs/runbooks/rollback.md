# 回滚 Runbook(§14.5 / W21)

> 回滚**应用版本**与回滚**数据库**是两件事。计划 14.5 的原话是:
> 「回滚应用先停止新作业、等正在提交的阶段结束或可安全恢复,再切回前一镜像。
> 新迁移必须兼容上一版本应用;不兼容迁移需要预先备份和维护窗口,**不能声称只换镜像
> 就能安全回滚**。」本文按这句拆成可执行步骤。

## 0. 先判断:回滚还是向前修?

| 情形 | 建议 |
|---|---|
| 新版本代码缺陷、schema 未变或仅新增可选列 | 回滚应用镜像即可(§2) |
| 新版本带了不兼容迁移(改列类型、删列、加 NOT NULL) | 维护窗口 + 备份 + 降级(§3),或向前修 |
| 数据被错误删除/污染 | 不要回滚应用,走 [restore.md](restore.md) 的恢复 |
| 只是模型/规则版本变化 | 回滚镜像 + 保留新 schema(向后兼容设计应允许) |

## 1. 回滚前(两条都必须做)

1. **停新作业**:`docker compose stop api worker relay watchdog`(或网关先 503)。
   仍在跑的 worker 会在回滚后写入上一版本不认识的状态,先让它停。
2. **等在途阶段结束**:确认没有租约未过期的 `running` 分析;watchdog 会把过期租约重排,
   所以等待期间别把 worker 停太久又放开写。
3. **备份当前库**:`python3 scripts/backup.py --label pre-rollback`。
   回滚是不可逆动作的前提,没有这份备份就不算准备完。

## 2. 应用回滚(镜像)

```bash
git checkout <上一个发布 tag 或 commit>          # 只影响工作区,不碰数据
docker compose build api worker relay watchdog web
docker compose up -d api worker relay watchdog web   # migrate 会先跑(见下)
```

**当前仓库的硬限制(未解决,写清楚而不是假装能切)**:`compose.yaml` 里的
`api/worker/relay/watchdog/web` 都用 `build:`,**没有固定 `image:` tag**,所以
「切回前一镜像」目前只能靠 `git checkout` 旧 commit 重新构建。要真正做到计划 14.5
的镜像级回滚,需要:

1. 给每个服务加 `image: registry/voicelens-api:<version>`(build + image 并存);
2. 构建后 push,并把 digest 记进 `scripts/release_manifest.py` 的产物(见 release-checklist);
3. 回滚时只改 tag/digest 并 `docker compose up -d`,不重新构建。

在那之前,回滚耗时 = 一次完整构建,且构建产物只能靠 commit 追溯。

## 3. 数据库回滚(alembic downgrade)

```bash
# 只回滚一个 revision(-1),或指定目标 revision
docker compose run --rm migrate sh -c "cd services/api && alembic -c alembic.ini downgrade -1"
docker compose run --rm migrate sh -c "cd services/api && alembic -c alembic.ini downgrade 0012"
```

先看清楚会经过哪些 revision:`alembic history -r current:0012`。

### 破坏性清单(截至 0015;新增迁移后必须刷新本表)

| revision | downgrade 的行为 | 影响 |
|---|---|---|
| 0001_initial | drop `projects/datasets/analysis_runs/audit_events/outbox_events` | **全部业务数据丢失** |
| 0002_dataset_event_key | drop `datasets.event_key` 与唯一索引 | 事件幂等键丢失,重新升级无法恢复原判定 |
| 0003_domain_entities | drop `reviews/tasks/risks` | 任务/复盘/风险全丢 |
| 0004_idempotency_keys | drop `idempotency_keys` | 幂等响应正文丢失,重复请求会重新执行 |
| 0005_session_tokens | drop `session_tokens` | **所有会话失效,全员重新登录** |
| 0006_domain_state_columns | drop 三表的 state 列 | 状态机历史丢失 |
| 0007_session_idle_exp | drop `session_tokens.idle_exp` | 空闲策略回退,代码需能接受 NULL |
| 0008_risk_reviews_and_audits | drop `risk_audits` + risks 复核列 | 风险裁决审计丢失 |
| 0009_deletion_jobs | drop `deletion_jobs` | **删除登记丢失**,此后无法证明哪些删除发生过;恢复旧备份将重新暴露已删正文(§10.4 的核心约束) |
| 0010_export_jobs | drop `export_jobs` | 导出记录丢失(文件本身按 TTL 处理) |
| 0011_redact_stored_rows | **空操作** | 脱敏不可逆,原值已不存在,没有回滚路径 |
| 0012_settings_memberships | drop `memberships` + `projects.settings_json/timezone` | **成员与角色全部丢失**,恢复后需重新授权 |
| 0013_reviews_nullable_columns | 空操作(刻意不恢复 NOT NULL) | 无数据损失 |
| 0014_feedback_and_segments | drop `feedback/segments` | 脱敏后的正文与分块丢失;可由 `datasets.governance` 重建,但 `event_key` 依赖当时的 `DEDUPE_HMAC_SECRET` |
| 0015_run_feedbacks | drop `run_feedbacks` | 冻结输入清单丢失;服务端保留 JSON 回退,不丢数据 |

**规则**:需要 `downgrade` 穿过 0009(登记)或 0012(成员)之前,**先备份,并在维护窗口内做**;
穿过 0011 没有任何意义(空操作)。跨过 0005 会让所有人重新登录,属于可接受但需公告的影响。

### 演练记录

2026-09-13 在隔离库 `voicelens_drill`(线上备份的副本,非生产)实测:

1. `alembic downgrade 0011`(从 0013 起)→ 通过;随后核对
   `information_schema`:`memberships` 表 = 0 行、`projects.settings_json/timezone` = 0 列,
   与上表 0012 的描述一致(破坏性属实)。
2. `alembic upgrade head` → 回到 `0015_run_feedbacks (head)`;`feedback/segments/run_feedbacks/memberships`
   全部存在。**降级后再升级在隔离库可行**。
3. 注意:第一次升级失败,原因是用的是**旧的 migrate 镜像**(源码是烘焙的,镜像构建于 0015 改动之前),
   重建后通过。任何迁移/应用改动后必须 `docker compose build <service>` 再验证(见 HANDOFF 约定)。

## 4. 回滚后验证

```bash
docker compose ps                                  # 全部 healthy/up
curl --fail http://localhost/health/live
curl --fail http://localhost/health/ready          # 只读,含数据库/迁移检查
docker compose logs --tail=100 api worker relay watchdog
python3 scripts/release_manifest.py --output /tmp/manifest-after-rollback.json
```

- `/health/ready` 会暴露数据库/迁移不一致,这是回滚后第一个该看的信号。
- 若同时降级了 schema,确认 api 启动的 `create_all` 不会把新表按当前模型又建回来
  (模型版本与镜像版本一致时不会;混用会建出「迁移未知的表」,与 0014 场景相同)。
- 恢复写入前,先做一轮只读冒烟:登录、项目列表、主题证据、导出下载(导出应已失效)。

## 5. 已知缺口

| 缺口 | 说明 |
|---|---|
| compose 无固定 image tag | §2 的镜像级回滚目前不可用,只能靠 git checkout + rebuild |
| 无 `downgrade` 的自动化测试 | 本文的破坏性清单来自代码阅读 + 一次隔离库演练,没有 CI 门禁 |
| `run_feedbacks`/`feedback` 的跨项目约束依赖 0014/0015 | 只降级 0015 保留 0014 是安全的;再往前要让应用一起回滚 |
| create_all 与迁移并存 | 任何服务用新镜像先于迁移启动,都会用模型建表(本次 watchdog 首次启动即建出 `feedback/segments`);顺序必须 migrate → 应用 |
| relay 与 watchdog 重复恢复 | §14.2 要求独立 `watchdog` 服务,而 `relay_runner.run()` 内联跑同一个 pass,两个容器会并发恢复同一批过期租约(重排是幂等的,但会重复派发)。拆开需要改 `relay_runner`(后端范围,本次未改) |
