# 备份与恢复 Runbook(§10.4 / §14.5 / W21)

> 状态:**备份、隔离恢复、tombstone 重放已在真实 compose 栈上演练通过**(证据见文末「演练记录」)。
> **生产切换、加密、定时任务未演练**,本文用「未验证」明确标出,不得当成已交付能力。

## 0. 目标与非目标

- 建议目标 RPO ≤ 24 小时、RTO ≤ 2 小时(计划 14.5)。**这是目标,不是对本项目已成立的服务承诺**;
  演练记录只有一次本机演练,没有生产数据量、没有异地恢复,不能对外写成 SLA。
- 备份产物**未加密**(见 §3),不得进交付包(§14.6)、不得放公共存储。
- 本流程覆盖「备份 → 恢复 → 重放删除登记 → 校验 → 再开放」;回滚(换回旧版本应用)见
  [rollback.md](rollback.md)。

## 1. 先决条件

| 项 | 要求 |
|---|---|
| 宿主机 | Python 3.9+,能执行 `docker compose`(脚本用 `docker compose exec -T` 访问数据库) |
| 数据库通道 | postgres 容器;compose 不发布 5432,只有 exec 这条通道(§14.2) |
| 磁盘 | 备份目录至少能放 3 份全量(产物大小 ≈ 库大小,压缩后更小) |
| 权限 | 能 `createdb`/`dropdb`(演练建隔离库用) |

## 2. 备份

```bash
python3 scripts/backup.py                       # 产物在 backups/(默认,可用 BACKUP_DIR 覆盖)
python3 scripts/backup.py --prune               # 按保留天数清理旧产物
BACKUP_RETENTION_DAYS=2 python3 scripts/backup.py --out-dir /srv/voicelens-backups
```

一次备份产出三个文件:

| 产物 | 作用 |
|---|---|
| `<db>-<ts>.dump` | `pg_dump --format=custom` 全库;可 `pg_restore -l` 校验、可选择性恢复 |
| `<db>-<ts>.tombstones.json` | **删除登记(§10.4)**:单独成文件,不随下一次恢复被覆盖 |
| `<db>-<ts>.manifest.json` | SHA-256、字节数、迁移版本、PostgreSQL 版本、保留天数、是否加密 |

- 保留策略:计划写「初始保留 7 天」并注明这是**建议工程策略、未经企业认可**。脚本默认只备份、
  **不删任何东西**;`--prune` 才按 `--keep-days`/`BACKUP_RETENTION_DAYS`(默认 7)清理,
  读不懂的 manifest 一律跳过并打印。
- 备份目录内会自动写一个 `.gitignore`(`*`),避免 `git add -A` 把数据库备份带进仓库(§14.6)。
- **未加密**是已知缺口:计划 14.1 要求备份密钥与数据库口令不同值,本脚本没有实现静态加密。
  要补必须同时做密钥管理、恢复时解密和演练,不是加一行 flag 能算交付;补上之前,备份只能落
  在加密介质/受控目录。

### 直连形式(未演练)

生产备份机上也可以不经过 compose,直接:

```bash
PGPASSWORD='***' pg_dump "postgresql://voicelens@db-host:5432/voicelens" \
  --format=custom --no-owner --no-privileges -f voicelens-$(date -u +%Y%m%dT%H%M%SZ).dump
```

本仓库不提供这条路径的脚本实现,也**没有演练过**:口令会出现在进程环境/历史里,且恢复侧
(`pg_restore`、版本检查、tombstone 重放)也要一起改写。要走这条路,先按本文的隔离演练流程
把两条路径都跑一遍再写进生产手册。

## 3. 恢复(隔离库演练 / 新环境)

```bash
python3 scripts/restore.py \
    --manifest backups/voicelens-20260913T063834Z.manifest.json \
    --target-db voicelens_restore_$(date -u +%Y%m%d) \
    --recreate \
    --report /tmp/restore-report.json
```

脚本按 §14.5 的顺序执行,任一门禁失败即以退出码 2 停止,**不会开放访问**:

| 步骤 | 门禁 | 失败时的含义 |
|---|---|---|
| 1 | 逐产物 SHA-256 与 manifest 比对 | 产物损坏/被替换,拒绝恢复 |
| 2 | 读删除登记文件 | 没有登记文件直接拒绝(恢复完不重放=旧正文复活) |
| 3 | `createdb` + `pg_restore --single-transaction` | 归档不可用 |
| 4 | **重放删除登记**(见 §4) | 有任何残留行 → 拒绝继续 |
| 5 | 版本检查:`alembic_version` == 仓库迁移 head | 旧备份落后于当前代码,见下 |
| 6 | 清理过期凭据/导出(§14.5) | — |
| 7 | 项目隔离检查:正文表不得有指向不存在项目的行 | 通常意味着「有删除没进登记」 |
| 8 | 只读事务里读完关键表 | 库不可读/结构不符 |

要点:

- **目标库默认必须是隔离库**。目标库名与备份源库同名时脚本直接拒绝,除非显式 `--force-live`
  (那会覆盖生产库;脚本不会替你判断这个决定)。
- `--recreate` 会丢弃目标库现有数据,脚本只打印、不额外保护:真正的保护是「先备份再恢复」。
- **版本检查失败是正常的**:例如备份取于 `0013`,而当前代码 head 是 `0015`。此时对恢复库执行迁移
  (`docker compose run --rm migrate` 指向恢复库,或手工 `alembic -c services/api/alembic.ini upgrade head`),
  然后**重跑本脚本**(幂等:重新校验、重建、重放)。顺序不能是「先开放再迁移」。
- 隔离检查放行开关 `--allow-orphans` 只用于明确知情的情况,且会写进报告;正常响应是查清
  「哪次删除没有进登记」,而不是放行。
- 最后一步(**把 api/worker 指向恢复库、解除只读、放开写入**)是人工操作,脚本不做。

### 生产恢复的切换顺序(未演练)

1. 停新作业:停止 api 的写入口(维护页/网关 503),`docker compose stop api worker relay watchdog`;
2. 等在途分析:确认没有 `running` 且租约未过期的 run(否则会丢阶段结果);
3. 对现有生产库**先做一次备份**(恢复前的现场);
4. 按 §3 在**隔离库**完成恢复+重放+校验;
5. 用恢复库替换生产库:`ALTER DATABASE voicelens RENAME TO voicelens_old;` +
   `ALTER DATABASE voicelens_restore_x RENAME TO voicelens;`(或改 DATABASE_URL 指向);
6. 只读冒烟:`/health/ready`、一个只读页面、一次导出下载(确认旧 token/导出已失效);
7. 逐步放开写入,观察 watchdog 是否把历史 queued 作业重投;
8. 保留 `voicelens_old` 至少一个保留周期再删。

## 4. tombstone(删除登记)语义

- 登记表是 `deletion_jobs`;应用每次删除**先写登记再清数据**(`app/deletions.py`)。
- 备份把登记导成独立 JSON;恢复时 `scripts/tombstone_register.py` 在恢复库上**重新执行**那次删除,
  顺序在开放访问之前。
- 重放的清理表清单是 `app/deletions.py` 级联在 SQL 侧的投影;`assert_coverage` 会在库里出现
 「带 `project_id` 但既未列入清理、也未列入显式保留」的新表时**拒绝执行**,避免漏删一张表
  还报成功。显式保留:`deletion_jobs`(证据)、`audit_events`、`risk_audits`(脱敏元数据)。
- 重放比应用层删除更彻底:应用删除**没有**清 `idempotency_keys`(§10.4 要求清幂等响应正文),
  重放会清;应用只把 `export_jobs` 置 `invalidated`,重放会删行。应用层这两处缺口见 §6。
- **dataset 级 tombstone 的已知缺口**:SQL 仓储把 `dataset_ids` 只取第一个写进
  `analysis_runs.dataset_id`(`sql_repository._assign`),所以一个引用多数据集的 run,其
  dataset 级删除无法被 SQL 重放完整覆盖。多数据集 run 的删除重放需要先修应用层。

## 5. 演练记录(W21 验收场景:备份 → 删除 → 恢复 → 重放)

2026-09-13 在本机真实 compose 栈执行,全部命令与输出如下(节选真实输出):

1. 备份线上库:`python3 scripts/backup.py`
   → `voicelens-20260913T063834Z.dump`(50.2 KiB,91 个归档条目),
   登记 `1` 条,`sha256=4839c36d…` 与 `shasum -a 256` 独立比对一致。
2. 隔离恢复:`python3 scripts/restore.py --manifest … --target-db voicelens_restore_drill --recreate`
   → 门禁 1–4、6–8 通过;门禁 5 以 `0013 ≠ 0014` 失败(诚实拦截),加
   `--expect-revision 0013_reviews_nullable_columns` 后完成 8/8。
   重放 `del_e995745efd`:删除 1 行(该行正是应用删除漏掉的 `idempotency_keys`),残留 0。
3. **删除-复活-重放**演练(隔离库,不碰线上数据):
   1. 在 `voicelens_drill` 里造一个带正文的项目 `drill_proj`(正文标记 `DRILL_SECRET_PAYLOAD`);
   2. `python3 scripts/backup.py --database voicelens_drill --out-dir /tmp/drill-backups` → 旧备份;
   3. 在 `voicelens_drill` 里执行一次真实删除(清正文 + 写登记 `del_drill0001`);
      `python3 scripts/tombstone_register.py export --database voicelens_drill --output /tmp/drill-register.json`;
   4. 用**旧备份**恢复到 `voicelens_drill_restored`,登记文件给一个空登记 →
      已删项目的正文**全部复活**:`projects=1, datasets=1, runs=1, exports=1,秘密正文行=2`;
   5. 同一个旧备份 + 真实登记重放 → 重放删除 9 行,核对
      `projects/datasets/runs/tasks/reviews/risks/memberships/export_jobs/idempotency_keys = 0`,
      `DRILL_SECRET_PAYLOAD` 行数 `0`,`deletion_jobs` 仍有 2 条登记。
4. 隔离检查在同一批量数据上报出真实孤儿:`project_id='p'` 的 2 个 dataset、2 个 analysis_run
   ——该项目的删除**没有登记**(线上 `deletion_jobs` 只有 1 条)。这是登记不完整的现有事实,
   需要产品或运维决定补录/清理策略,不是脚本缺陷。
5. schema 升到 `0015`(feedback/segments/run_feedbacks)后复跑:
   - 线上库备份(99 个归档条目,3 条登记)→ `voicelens_accept` 恢复,**8/8 门禁通过**,
     默认版本检查直接对上 head;两条 dataset 级登记重放后残留 0;
   - 又造了 `drill2_proj`(feedback+segments+run_feedbacks 复合外键齐全)复跑「备份→删除→旧备份恢复→重放」:
     重放删除 8 行(`datasets/analysis_runs/feedback/segments/run_feedbacks/memberships/idempotency_keys/projects`),
     残留 0、正文标记 0、登记保留;
   - dataset 级登记单独用真实行验证:重放删除 `segments/run_feedbacks/feedback/analysis_runs/datasets` 5 行,
     **项目本身保留**(数据集删除不动项目),残留 0。

**未验证**:生产切换(§3 的 8 步)、异地恢复、真实数据量下的 RTO/RPO、加密、定时备份任务
(cron/systemd timer)、直连 pg_dump 路径。

## 6. 已知缺口(需要应用层或配置变更,不在本 worker 文件范围)

| 缺口 | 影响 | 建议 |
|---|---|---|
| 应用删除不清 `idempotency_keys` | §10.4 要求清「幂等响应正文」;真实部署里删除后仍留一份响应正文(本次演练实测:应用删除后该行仍在,重放才删掉) | 改 `app/deletions.py` 增加一步(未做,属后端范围) |
| dataset 级删除的 SQL 仓储只存首个 dataset_id | 多数据集 run 的 dataset 级重放覆盖不全 | 改 `sql_repository._assign` 或改跑应用层删除(未做) |
| `deletion_jobs` 无 `created_at` | 无法按时间审计/清理登记 | 加列(未做) |
| 备份未加密 | 计划 14.1 的「备份密钥」无从落地 | 加密+密钥管理+演练(未做) |
| compose 用 `build:`、无固定 image tag | §14.5「切回前一镜像」目前只能靠 git checkout + rebuild | 见 [rollback.md](rollback.md) §3 |
| 无 `tests/integration/test_restore.py` | W21 规划里的自动化恢复测试不存在;本文的演练是手工执行、非 CI 门禁 | 需要建 `tests/integration`(未做,超出本次文件范围) |
| `relay_runner` 内联跑 watchdog pass | relay 与 compose 的 `watchdog` 服务会重复恢复同一批过期租约 | 拆开 `relay_runner`,见 [rollback.md](rollback.md) 附录 |
