# 发布冻结清单(§14.3 / §14.6 / W22)

> 用法:冻结候选 commit 后逐项执行,把**真实输出**填进「证据」列。计划 W22 的完成定义写明:
> 「不能将未执行写通过」。没有证据路径的勾 = 不算通过;本文件当前**不含**已签核结果。

## 1. 冻结前

- [ ] 发布分支从 `master` 切出,且**没有未提交改动**(`git status --porcelain` 为空);
- [ ] `HANDOFF.md` 等交接件不在发布 commit 里(§14.6:交付源码仓库/tag,不含临时交接文档);
- [ ] 已知问题列表写全(模板见 §6),未完成项按「已完成/未完成/阻塞」分开写;
- [ ] 产品目标与试点结果分开陈述;没有真实用户试用就写「未试用」,不写虚构反馈(§W22)。

## 2. 门禁与证据

| # | 门禁 | 命令 | 期望证据 |
|---|---|---|---|
| 2.1 | Compose 契约 | `python3 scripts/validate-compose.py && docker compose config --quiet` | 「validation passed」+ 无输出 |
| 2.2 | 后端全量 | `docker compose build api && docker compose run --rm -e AUTH_REQUIRED=false -e USE_DATABASE=0 api sh -c 'PYTHONPATH=/app/services/api python -m pytest services/api/tests -q'` | 用例数 + 通过数,0 failed/0 error |
| 2.3 | 前端静态 | `npm --prefix apps/web run lint:style && npm --prefix apps/web run typecheck` | 无错误 |
| 2.4 | 前端单测 | `npm --prefix apps/web run test:unit -- --run` | 用例数与通过数 |
| 2.5 | 前端构建 | `npm --prefix apps/web run build` | 构建成功 |
| 2.6 | UI/E2E(mock) | `npm --prefix apps/web run test:e2e -- --project=chromium --workers=1` | 通过/跳过数(视觉基线人工核准,不得 `--update-snapshots`) |
| 2.7 | 真实 API 闭环 | 先起 API(8010)+ `npm --prefix apps/web run test:e2e:real` | 全部通过;不得用预制 JSON 替换后端(§11.1) |
| 2.8 | schema 闸门 | CI 的「全新建库 → alembic upgrade head」项 | 绿;新增迁移必须能被全新库跑到 head |
| 2.9 | 备份恢复演练 | [runbooks/restore.md](runbooks/restore.md) §3–§4 全流程 + 删除-复活-重放 | 报告 JSON + 重放残留=0 |
| 2.10 | 回滚演练 | [runbooks/rollback.md](runbooks/rollback.md) §3 在隔离库 `downgrade` 再 `upgrade head` | 迁移版本回到 head;破坏性影响已记录 |
| 2.11 | 模型/规则版本 | `python3 scripts/release_manifest.py` 的 `migrations.head`、`prompts`、`rules_version` | 非空;为 `null` 的项必须出现在已知问题里 |
| 2.12 | 依赖与镜像 | 同一 manifest 的 `dependencies`/`images` | 锁文件哈希;镜像 push 后的 digest |

## 3. 发布 manifest

```bash
python3 scripts/release_manifest.py --output releases/manifest-$(git rev-parse --short HEAD).json
```

字段(缺什么就写 `null` + 进 `known_gaps`,不编造):

| 字段 | 内容 | 现状 |
|---|---|---|
| `git` | commit/branch/tag/dirty | 可用;`dirty=true` 的 manifest 不得作为发布件 |
| `images.<service>` | compose 服务 → 镜像 Id + RepoDigests | 可用;**push 后必须重跑**,本地构建的 digest 不能当跨环境标识 |
| `migrations` | head、迁移文件数、文件哈希聚合 | 可用(head 由 `revision/down_revision` 推导) |
| `dependencies` | requirements.txt / package.json / package-lock.json 的 sha256 与是否锁文件 | 可用;**Python 侧无锁文件**,见 §7 |
| `specs` | 规格文档版本与 sha256 | 可用(`工程开发计划 v1.1`、`前端风格规范 v1.0`) |
| `prompts` / `rules_version` / `test_data_hash` | 提示词、规则、固定合成测试数据 | **仓库里不存在,恒为 null** |

## 4. 版本标签

```bash
git tag -a v0.1.0 -m "VoiceLens MVP 冻结" <commit>
git push origin v0.1.0
python3 scripts/release_manifest.py --output releases/manifest-v0.1.0.json   # 基于 tag 重跑
```

- 当前仓库 **0 个 tag**(W22 未完成项),首个 tag 由本清单第一次执行时创建;
- tag 必须指向**已通过全部门禁**的那个 commit,不能事后补打;
- `git add` 只按路径加自己的文件,禁止 `git add -A`(后台 agent 的中间产物会被一起提交)。

## 5. 交付包(§14.6)

必须包含:源码仓库/tag、锁文件(或注明缺锁)、迁移、Compose、配置说明、模型 revision、
数据许可/合成标识、测试报告、性能原始记录、故障恢复记录、部署/回滚手册、已知问题、演示录屏、
UI 验收记录与已核准截图基线。

**禁止打进交付包**:`.env`、真实客诉原始文件、消费者身份、生产数据库备份、Cookie、
API 密钥(§14.6)。本仓库的 `backups/` 内有 `.gitignore`,但仍须在打包前人工确认
`git ls-files backups/` 为空。

## 6. 签核表(由执行者填写)

| 门禁 | 执行人 | 日期 | 证据路径/命令输出 | 结果 |
|---|---|---|---|---|
| 2.1–2.6 | | | | |
| 2.7 真实 API | | | | |
| 2.8 全新库迁移 | | | | |
| 2.9 备份恢复 | | | | |
| 2.10 回滚 | | | | |
| 2.11–2.12 manifest | | | | |
| UI 基线人工核准 | | | | |

## 7. 已知问题(发布时必须列出,当前实际状态)

| 项 | 状态 |
|---|---|
| 提示词/规则版本、固定合成测试数据集 | 不存在,manifest 相应字段为 `null` |
| Python 依赖锁文件 | 不存在(`requirements.txt` 是范围声明);前端有 `package-lock.json` |
| 性能/基准数据(§13.3/13.4) | 未产出;`scripts/benchmark.py` 不在本次交付内 |
| 模型接线 | 向量仍是哈希替身(`hashing-ngram-v1`),真实 LLM provider 无调用方(HANDOFF 未完成项) |
| §5.2 表结构 | 反馈/分块实体化进行中(0014/0015);`feedback`/`segments` 之外的 JSON 承载仍在 |
| 备份加密 | 未实现(见 runbooks/restore.md §2/§6) |
| 镜像 tag / digest | compose 全用 `build:`;「只换镜像回滚」目前不可用(见 runbooks/rollback.md §2) |
| 恢复自动化测试 | 无 `tests/integration/test_restore.py`;恢复演练为手工执行 |
| 验收剩余项 | 以 HANDOFF「未完成」清单为准,发布前逐条确认状态 |

## 8. 本清单自身未验证的部分

本文件是**模板 + 现状说明**,不是已签核的发布记录:2.2–2.8 的测试门禁本次没有在发布候选上执行,
2.9/2.10 只在隔离库演练过(记录见两份 runbook),2.12 的镜像 digest 未 push。首次真正使用时,
按表逐项执行并填证据。
