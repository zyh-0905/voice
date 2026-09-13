"""W21/§14.5 恢复:校验 → 建库 → pg_restore → 重放登记 → 版本检查 → 清过期 → 隔离 → 只读。

顺序是计划 14.5 的顺序,不能调换:

    恢复备份 → 重放独立删除登记 → 执行版本检查 → 清理过期会话和导出
    → 校验项目隔离 → 只读检查 → 再开放写入

本脚本做到「只读检查」为止,**不**切换流量、不开放访问:最后一步(把 api/worker
指向恢复库、解除只读)是人工操作,写进 docs/runbooks/restore.md。先开放再清理
等于旧备份里的正文在窗口期重新可见。

诚实说明(没有做的事):

- 目标库默认必须是**隔离库**(演练/新建环境)。要覆盖生产库必须显式
  `--force-live` 并自己承担后果——脚本不会假装这是安全操作。
- **重放的是 app/deletions.py 级联的 SQL 投影**,不是调用应用层实现。新增项目域
  表时 tombstone_register.assert_coverage 会让重放直接失败,而不是漏删。
- 覆盖前不会自动备份目标库:目标库若已有数据,`--recreate` 会丢弃它,脚本只打印
  警告;真正的保护是「先备份再恢复」这条人工规程。
- 只支持 `docker compose exec postgres` 通道;直连形式见 runbook(含未演练声明)。

用法:
    python3 scripts/restore.py --manifest backups/voicelens-20260913T000000Z.manifest.json \\
        --target-db voicelens_restore_20260913 --recreate
"""
from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

from ops_common import (DEFAULT_SERVICE, DEFAULT_USER, OpsError, exec_in, human_bytes,
                        main_guard, migration_head, psql, psql_json_rows, psql_scalar,
                        read_json, require_artifact, sha256_file, write_json)

DB_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_]{0,62}$")
FORBIDDEN_DB_NAMES = {"postgres", "template0", "template1"}
RESERVED_PAYLOAD_TABLES = ("datasets", "analysis_runs", "feedback", "segments", "tasks",
                           "reviews", "risks", "export_jobs", "idempotency_keys")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_sources(manifest_path: Path | None, dump_path: Path | None,
                    register_path: Path | None) -> dict:
    """定位三个产物:显式 --dump 也要能配上同名 manifest/登记,否则无法校验。"""
    if manifest_path is None and dump_path is None:
        raise OpsError("必须给出 --manifest 或 --dump")
    if manifest_path is None:
        manifest_path = dump_path.with_name(dump_path.name.replace(".dump", ".manifest.json"))
        if not manifest_path.exists():
            raise OpsError(f"找不到与 {dump_path.name} 同名的 manifest;--manifest 显式指定")
    manifest = read_json(manifest_path)
    out_dir = manifest_path.parent
    artifacts = {item["role"]: item for item in manifest.get("artifacts", [])}
    if "database" not in artifacts:
        raise OpsError(f"{manifest_path}: manifest 缺少 database 产物")
    dump_path = out_dir / artifacts["database"]["name"]
    register_item = artifacts.get("deletion_register")
    register_path = register_path or (out_dir / register_item["name"] if register_item else None)
    if register_path is None:
        raise OpsError("备份没有删除登记文件:恢复无法重放删除,按 §10.4 拒绝继续")
    return {"manifest": manifest, "manifest_path": manifest_path, "dump": dump_path,
            "register": register_path, "out_dir": out_dir}


def verify_checksums(sources: dict) -> list:
    checks = []
    for item in sources["manifest"].get("artifacts", []):
        path = sources["out_dir"] / item["name"]
        require_artifact(path)
        actual = sha256_file(path)
        checks.append({"name": item["name"], "expected": item["sha256"], "actual": actual,
                       "bytes": path.stat().st_size, "ok": actual == item["sha256"]})
    if not all(check["ok"] for check in checks):
        bad = [check["name"] for check in checks if not check["ok"]]
        raise OpsError(f"SHA-256 校验失败: {bad};产物已损坏或被替换,拒绝恢复")
    return checks


def restore_database(dump_path: Path, target_db: str, user: str, service: str,
                     recreate: bool) -> None:
    exists = psql_scalar("postgres", "select 1 from pg_database where datname = :'name'",
                         user=user, service=service, variables={"name": target_db}) == "1"
    if exists and not recreate:
        raise OpsError(f"目标库 {target_db} 已存在;要么换库名,要么显式 --recreate(会丢弃该库现有数据)")
    if exists:
        exec_in(service, ["dropdb", "-U", user, "--if-exists", target_db])
    exec_in(service, ["createdb", "-U", user, "-O", user, target_db])
    with open(dump_path, "rb") as handle:
        exec_in(service, ["pg_restore", "--no-owner", "--no-privileges", "--exit-on-error",
                          "--single-transaction", "-U", user, "-d", target_db], stdin=handle)


def version_check(target_db: str, expect_revision: str | None, user: str, service: str) -> dict:
    restored = psql_scalar(target_db, "select version_num from alembic_version",
                           user=user, service=service)
    head = expect_revision or migration_head()
    return {"restored_revision": restored, "expected_revision": head, "ok": restored == head}


def cleanup_expired(target_db: str, tables: dict, user: str, service: str) -> dict:
    """§14.5「清理过期会话和导出」:恢复回来的旧凭据与下载内容不得继续可用。"""
    removed = {}
    if "session_tokens" in tables:
        sql = "DELETE FROM session_tokens WHERE exp < extract(epoch from now())"
        if "idle_exp" in tables["session_tokens"]:
            sql += " OR idle_exp < extract(epoch from now())"
        removed["session_tokens"] = int(psql_scalar(target_db, f"WITH d AS ({sql} RETURNING 1) "
                                                    "SELECT count(*) FROM d", user=user, service=service))
    if "export_jobs" in tables and "expires_at" in tables["export_jobs"]:
        # expires_at 是 ISO 字符串;先正则挡掉脏值,避免一行坏数据让整个恢复中断
        condition = ("invalidated = true OR (expires_at ~ '^\\d{4}-\\d{2}-\\d{2}T' "
                     "AND expires_at::timestamptz < now())")
        if "invalidated" not in tables["export_jobs"]:
            condition = "expires_at ~ '^\\d{4}-\\d{2}-\\d{2}T' AND expires_at::timestamptz < now()"
        removed["export_jobs"] = int(psql_scalar(target_db, f"WITH d AS (DELETE FROM export_jobs "
                                                   f"WHERE {condition} RETURNING 1) "
                                                   "SELECT count(*) FROM d", user=user, service=service))
    return removed


def isolation_check(target_db: str, tables: dict, user: str, service: str) -> dict:
    """§14.5「校验项目隔离」:正文表不得留下指向已不存在项目的行。"""
    checks = []
    for table in RESERVED_PAYLOAD_TABLES:
        if table not in tables or "project_id" not in tables[table]:
            continue
        checks.append(f"SELECT row_to_json(q) FROM (SELECT '{table}' AS table_name, "
                      f"count(*) AS orphans FROM {table} src WHERE NOT EXISTS "
                      f"(SELECT 1 FROM projects p WHERE p.id = src.project_id)) q")
    if not checks:
        return {"orphans": {}, "ok": True}
    rows = psql_json_rows(target_db, " UNION ALL ".join(checks), user=user, service=service)
    orphans = {row["table_name"]: int(row["orphans"]) for row in rows}
    return {"orphans": orphans, "ok": not any(orphans.values())}


def read_only_check(target_db: str, tables: dict, user: str, service: str) -> dict:
    """§14.5「只读检查」:在只读事务里跑一遍恢复后的关键查询,确认库可读且一致。"""
    checks = ["SELECT row_to_json(q) FROM (SELECT 'projects' AS name, count(*) AS value "
              "FROM projects) q"]
    for table in ("datasets", "analysis_runs", "deletion_jobs", "memberships"):
        if table in tables:
            checks.append(f"SELECT row_to_json(q) FROM (SELECT '{table}' AS name, "
                          f"count(*) AS value FROM {table}) q")
    sql = "SET TRANSACTION READ ONLY;\n" + " UNION ALL ".join(checks)
    rows = psql_json_rows(target_db, sql, user=user, service=service, single_transaction=True)
    return {"counts": {row["name"]: int(row["value"]) for row in rows}, "ok": True}


def run(args: argparse.Namespace) -> dict:
    from tombstone_register import load_register, plan_replay, replay, table_columns

    sources = resolve_sources(Path(args.manifest) if args.manifest else None,
                              Path(args.dump) if args.dump else None,
                              Path(args.register) if args.register else None)
    manifest = sources["manifest"]
    report = {"started_at": _now(), "manifest": str(sources["manifest_path"]),
              "target_db": args.target_db, "gates": {}}

    report["gates"]["checksums"] = verify_checksums(sources)
    print(f"[1/8] 校验通过: {len(report['gates']['checksums'])} 个产物 SHA-256 一致"
          f" ({human_bytes(sum(c['bytes'] for c in report['gates']['checksums']))})")

    if args.dry_run:
        print("[dry-run] 只校验了产物;未建库、未恢复、未重放")
        return report

    source_db = manifest.get("database")
    if args.target_db == source_db and not args.force_live:
        raise OpsError(f"目标库与备份源库同名({source_db});恢复会覆盖生产库,"
                       "确需如此请显式 --force-live")
    register = load_register(sources["register"])
    print(f"[2/8] 删除登记 {register['row_count']} 条 来自 {sources['register'].name}")

    restore_database(sources["dump"], args.target_db, args.user, args.service, args.recreate)
    print(f"[3/8] pg_restore 完成 → {args.target_db}")

    tables = table_columns(args.target_db, user=args.user, service=args.service)

    # §14.5 的顺序:先重放删除登记,再做版本检查。重放用的是恢复库自身的
    # schema 探测结果,不依赖应用版本;而版本不符时绝不能先去开放访问。
    plan = plan_replay(args.target_db, register, user=args.user, service=args.service)
    report["gates"]["tombstones"] = replay(args.target_db, register, user=args.user, service=args.service)
    print(f"[4/8] 重放删除登记 {plan['register_rows']} 条;"
          f"覆盖表 {len(plan['coverage']['project_scoped_tables'])} 张"
          f"{'; 缺表(旧备份跳过) ' + ','.join(plan['coverage']['missing_tables']) if plan['coverage']['missing_tables'] else ''}")
    for entry in report["gates"]["tombstones"]["tombstones"]:
        removed = sum(entry["removed"].values())
        print(f"      - {entry['id']} ({entry['target_type']} {entry['target_id']}): 删除 {removed} 行;"
              f"残留 {sum(entry['remaining'].values())}")
    if not report["gates"]["tombstones"]["ok"]:
        raise OpsError("重放后仍有残留:恢复库不得开放访问")

    report["gates"]["version"] = version_check(args.target_db, args.expect_revision,
                                              args.user, args.service)
    if not report["gates"]["version"]["ok"]:
        raise OpsError(
            f"版本检查失败: 恢复库 {report['gates']['version']['restored_revision']} "
            f"≠ 期望 {report['gates']['version']['expected_revision']};"
            "对恢复库执行 alembic upgrade head 后重跑本脚本(幂等),再谈开放访问")
    print(f"[5/8] 版本检查通过: {report['gates']['version']['restored_revision']}")

    if args.skip_cleanup:
        report["gates"]["cleanup"] = {"skipped": True}
        print("[6/8] 跳过过期会话/导出清理(--skip-cleanup)")
    else:
        report["gates"]["cleanup"] = cleanup_expired(args.target_db, tables, args.user, args.service)
        print(f"[6/8] 清理过期凭据/导出: {report['gates']['cleanup']}")

    report["gates"]["isolation"] = isolation_check(args.target_db, tables, args.user, args.service)
    if not report["gates"]["isolation"]["ok"]:
        if not args.allow_orphans:
            raise OpsError(
                f"项目隔离检查失败,存在孤儿正文行: {report['gates']['isolation']['orphans']};"
                "这通常说明有删除没有进登记(登记不完整),不得直接开放访问。"
                "确认要带病开放才加 --allow-orphans(会写进报告)")
        report["gates"]["isolation"]["override"] = "--allow-orphans"
        print(f"[7/8] 隔离检查未通过,被 --allow-orphans 放行(已写进报告): "
              f"{report['gates']['isolation']['orphans']}")
    else:
        print(f"[7/8] 项目隔离检查通过: {report['gates']['isolation']['orphans']}")

    report["gates"]["read_only"] = read_only_check(args.target_db, tables, args.user, args.service)
    print(f"[8/8] 只读检查通过: {report['gates']['read_only']['counts']}")

    report["finished_at"] = _now()
    report["next_step"] = ("脚本到此为止:尚未放开写入。切换 api/worker 指向恢复库并解除只读"
                           "由人工按 docs/runbooks/restore.md 执行。")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VoiceLens 恢复(含删除登记重放)")
    parser.add_argument("--manifest", default=None, help="backup.py 产出的 manifest")
    parser.add_argument("--dump", default=None, help="直接给 dump;同目录需有同名 manifest")
    parser.add_argument("--register", default=None, help="覆盖 manifest 指向的删除登记文件")
    parser.add_argument("--target-db", required=True, help="恢复目标库(默认要求是隔离库)")
    parser.add_argument("--recreate", action="store_true", help="目标库已存在时先 drop 再建")
    parser.add_argument("--force-live", action="store_true",
                        help="允许目标库名与源库相同(会覆盖生产库,慎用)")
    parser.add_argument("--expect-revision", default=None,
                        help="期望的 alembic 版本,默认取仓库迁移 head")
    parser.add_argument("--skip-cleanup", action="store_true", help="跳过过期会话/导出清理")
    parser.add_argument("--allow-orphans", action="store_true",
                        help="隔离检查发现孤儿正文行时仍然继续(默认阻断;覆盖会写进报告)")
    parser.add_argument("--dry-run", action="store_true", help="只校验产物,不碰数据库")
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--service", default=DEFAULT_SERVICE)
    parser.add_argument("--report", default=None, help="把 JSON 报告写到指定路径(证据留存)")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not DB_NAME_RE.match(args.target_db) or args.target_db in FORBIDDEN_DB_NAMES:
        raise OpsError(f"非法的目标库名: {args.target_db!r}")
    report = run(args)
    if args.report:
        write_json(Path(args.report), report)
        print(f"报告已写入 {args.report}")


if __name__ == "__main__":
    main_guard(main)
