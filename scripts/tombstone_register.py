"""§10.4 删除登记的导出与重放。

计划原文:

    与项目删除相关的 tombstone 在独立的运维删除登记中保留,以便备份恢复后
    先重放删除记录、再开放访问。删除登记不得只存在于将被旧备份覆盖的数据库里。

因此登记必须有一份落在数据库之外(随备份产出的 JSON 文件),恢复流程里
「恢复备份 → 重放登记 → 校验 → 再开放」的顺序不能颠倒:先开放访问再慢慢删,
等于旧备份里的正文在窗口期内重新可见。

本模块的 SQL 是 `app/deletions.py` 级联删除在 SQL 侧的**投影**,不是替代品:
- 权威实现是应用层,新增项目域表时应用层会改,这里不会自动跟上;
- 所以下面用 `assert_coverage` 做动态护栏:只要库里出现一张「带 project_id
  但既不在清理清单、也不在显式保留清单」的表,重放直接拒绝执行,
  而不是悄悄漏删一张表还报告成功。
- dataset 级 tombstone 另有已知缺口:SQL 仓储只把 dataset_ids 的第一个写进
  `analysis_runs.dataset_id`,多数据集 run 的重放覆盖不全,见 runbook。

用法:
    python3 scripts/tombstone_register.py export --database voicelens --output X.json
    python3 scripts/tombstone_register.py replay --database voicelens_restore --register X.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from ops_common import (DEFAULT_DATABASE, DEFAULT_SERVICE, DEFAULT_USER, OpsError,
                        main_guard, psql, psql_json_rows, psql_scalar, read_json,
                        write_json)

REGISTER_VERSION = 1

# 项目级删除要清空的表(子表在前,便于人工核对顺序);
# 与 app/deletions.py 的级联保持一致——那边加了表而这边没加时,assert_coverage 会直接报错
PURGE_TABLES = (
    "segments",
    "run_feedbacks",
    "feedback",
    "analysis_runs",
    "datasets",
    "export_jobs",
    "idempotency_keys",
    "tasks",
    "reviews",
    "risks",
    "memberships",
    "projects",
)

# 带 project_id 但**不**随项目删除的表:留着是刻意的,不是漏了
RETAINED_TABLES = {
    "deletion_jobs": "删除登记与最小回执本身是删除的证据,重放后仍要可查",
    "audit_events": "审计元数据不含正文,与 app.execute_deletion 现状一致",
    "risk_audits": "风险裁决审计元数据不含正文",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def table_columns(database: str, user: str = DEFAULT_USER,
                  service: str = DEFAULT_SERVICE) -> dict:
    """探测 public schema 里每张表的列;重放计划据此生成,而不是靠假设。"""
    rows = psql_json_rows(
        database,
        """
        select row_to_json(t) from (
          select c.table_name as name, json_agg(c.column_name order by c.column_name) as columns
          from information_schema.columns c
          where c.table_schema = 'public'
          group by c.table_name
          order by c.table_name
        ) t
        """,
        user=user, service=service,
    )
    return {row["name"]: list(row["columns"]) for row in rows}


def assert_coverage(tables: dict) -> dict:
    """护栏:库里每张带 project_id 的表都必须被显式处置;否则拒绝重放。"""
    project_scoped = {name for name, columns in tables.items() if "project_id" in columns}
    unknown = sorted(project_scoped - set(PURGE_TABLES) - set(RETAINED_TABLES))
    if unknown:
        raise OpsError(
            "恢复重放拒绝执行:检测到未登记的项目域表 " + ", ".join(unknown) +
            "。它们既不在 PURGE_TABLES(会被清空),也不在 RETAINED_TABLES(显式保留),"
            "重放可能会把已删项目的正文重新暴露。请先更新 scripts/tombstone_register.py 并说明理由。"
        )
    missing = sorted(set(PURGE_TABLES) - set(tables))
    return {"project_scoped_tables": sorted(project_scoped), "missing_tables": missing}


def export_register(database: str, output: Path, user: str = DEFAULT_USER,
                    service: str = DEFAULT_SERVICE, source_backup: str | None = None) -> dict:
    """把删除登记导出成独立文件——这份文件才是「不会被旧备份覆盖」的那一份。"""
    # steps/receipt 显式转 jsonb:json 列里的换行会被 row_to_json 原样吐出,
    # 逐行解析会断;jsonb 输出是单行规范形式,登记文件仍保留嵌套结构
    rows = psql_json_rows(
        database,
        """
        select row_to_json(t) from (
          select id, project_id, target_type, target_id, target_name, state, actor,
                 steps::jsonb as steps, receipt::jsonb as receipt
          from deletion_jobs order by id
        ) t
        """,
        user=user, service=service,
    )
    payload = {
        "register_version": REGISTER_VERSION,
        "exported_at": _now(),
        "database": database,
        "source_backup": source_backup,
        "row_count": len(rows),
        "rows": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, payload)
    return payload


def load_register(path: Path) -> dict:
    payload = read_json(path)
    if payload.get("register_version") != REGISTER_VERSION:
        raise OpsError(f"{path}: unsupported register_version {payload.get('register_version')!r}")
    if not isinstance(payload.get("rows"), list):
        raise OpsError(f"{path}: register has no rows list")
    return payload


def _json_literal(value) -> str:
    """psql 变量是文本;None 传空串,SQL 侧用 NULLIF(...)::json 还原成 NULL。"""
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _insert_job_cte() -> str:
    return (
        "ins AS (INSERT INTO deletion_jobs "
        "(id, project_id, target_type, target_id, target_name, state, actor, steps, receipt) "
        "VALUES (:'job_id', :'project_id', :'target_type', :'target_id', "
        "NULLIF(:'target_name', ''), :'state', NULLIF(:'actor', ''), "
        "NULLIF(:'steps', '')::json, NULLIF(:'receipt', '')::json) "
        "ON CONFLICT (id) DO NOTHING RETURNING 1)"
    )


def _project_replay_sql(tables: dict) -> str:
    ctes = []
    selects = []
    for index, table in enumerate(PURGE_TABLES):
        if table not in tables:
            continue
        if table == "projects":
            # projects 的主键是 id;其余表按 project_id 关联
            condition = "id = :'project_id'"
        else:
            # 一律按 URL 里的 project_id 清,而不是按 tombstone.target_id:
            # 前者才是被删除的项目,后者是历史写入值,不保证一致
            condition = "project_id = :'project_id'"
        ctes.append(f"d{index} AS (DELETE FROM {table} WHERE {condition} RETURNING 1)")
        selects.append(f"SELECT row_to_json(t) FROM (SELECT '{table}' AS table_name, "
                       f"(SELECT count(*) FROM d{index}) AS removed) t")
    ctes.append(_insert_job_cte())
    return "WITH\n  " + ",\n  ".join(ctes) + "\n" + "\nUNION ALL ".join(selects)


def _dataset_replay_sql(tables: dict) -> str:
    if "datasets" not in tables:
        raise OpsError("数据集 tombstone 无法重放:恢复库里没有 datasets 表")
    run_columns = set(tables.get("analysis_runs", ()))
    if "dataset_id" in run_columns:
        run_condition = "project_id = :'project_id' AND dataset_id = :'target_id'"
    elif "dataset_ids" in run_columns:
        run_condition = ("project_id = :'project_id' AND "
                         "dataset_ids::jsonb @> jsonb_build_array(:'target_id')")
    else:
        raise OpsError("数据集 tombstone 无法重放:analysis_runs 既无 dataset_id 也无 dataset_ids 列")
    ctes = []
    selects = []
    if "segments" in tables:
        ctes.append("d0 AS (DELETE FROM segments WHERE project_id = :'project_id' AND feedback_id IN "
                    "(SELECT id FROM feedback WHERE project_id = :'project_id' "
                    "AND dataset_id = :'target_id') RETURNING 1)")
        selects.append("SELECT row_to_json(t) FROM (SELECT 'segments' AS table_name, "
                       "(SELECT count(*) FROM d0) AS removed) t")
    if "run_feedbacks" in tables:
        # 按 feedback_id 删,而不是按 run:SQL 仓储只记录 run 的第一个 dataset_id,
        # 多数据集 run 在本重放里可能幸存;留下指向已删 feedback 的冻结清单会撞复合外键,
        # 结果是整个重放事务回滚(比悄悄漏删好,但这里可以既安全又完整)
        ctes.append("d4 AS (DELETE FROM run_feedbacks WHERE project_id = :'project_id' "
                    "AND feedback_id IN (SELECT id FROM feedback WHERE project_id = :'project_id' "
                    "AND dataset_id = :'target_id') RETURNING 1)")
        selects.append("SELECT row_to_json(t) FROM (SELECT 'run_feedbacks' AS table_name, "
                       "(SELECT count(*) FROM d4) AS removed) t")
    if "feedback" in tables:
        ctes.append("d1 AS (DELETE FROM feedback WHERE project_id = :'project_id' "
                    "AND dataset_id = :'target_id' RETURNING 1)")
        selects.append("SELECT row_to_json(t) FROM (SELECT 'feedback' AS table_name, "
                       "(SELECT count(*) FROM d1) AS removed) t")
    ctes.append(f"d2 AS (DELETE FROM analysis_runs WHERE {run_condition} RETURNING 1)")
    selects.append("SELECT row_to_json(t) FROM (SELECT 'analysis_runs' AS table_name, "
                   "(SELECT count(*) FROM d2) AS removed) t")
    ctes.append("d3 AS (DELETE FROM datasets WHERE project_id = :'project_id' "
                "AND id = :'target_id' RETURNING 1)")
    selects.append("SELECT row_to_json(t) FROM (SELECT 'datasets' AS table_name, "
                   "(SELECT count(*) FROM d3) AS removed) t")
    ctes.append(_insert_job_cte())
    return "WITH\n  " + ",\n  ".join(ctes) + "\n" + "\nUNION ALL ".join(selects)


def _verify_sql(tombstone: dict, tables: dict) -> str:
    """重放后必须为零的清单;projects 用 id,其余用 project_id。"""
    project_id, target_id = tombstone["project_id"], tombstone["target_id"]
    if tombstone["target_type"] == "project":
        raw = [f"SELECT 'projects' AS table_name, count(*) AS remaining FROM projects "
               f"WHERE id = :'project_id'"]
        for table in PURGE_TABLES:
            if table == "projects" or table not in tables:
                continue
            raw.append(f"SELECT '{table}' AS table_name, count(*) AS remaining FROM {table} "
                       f"WHERE project_id = :'project_id'")
    else:
        raw = [f"SELECT 'datasets' AS table_name, count(*) AS remaining FROM datasets "
               f"WHERE project_id = :'project_id' AND id = :'target_id'",
               f"SELECT 'feedback' AS table_name, count(*) AS remaining FROM feedback "
               f"WHERE project_id = :'project_id' AND dataset_id = :'target_id'"]
        run_columns = set(tables.get("analysis_runs", ()))
        if "dataset_id" in run_columns:
            raw.append("SELECT 'analysis_runs' AS table_name, count(*) AS remaining "
                       "FROM analysis_runs WHERE project_id = :'project_id' "
                       "AND dataset_id = :'target_id'")
    # 统一包成 row_to_json,和删除计数共用一套解析(-tA 下 TSV 与 JSON 混用迟早解析错)
    checks = [f"SELECT row_to_json(t) FROM ({check}) t" for check in raw]
    return " UNION ALL ".join(checks)


def _variables(tombstone: dict) -> dict:
    return {
        "job_id": str(tombstone.get("id") or ""),
        "project_id": str(tombstone.get("project_id") or ""),
        "target_type": str(tombstone.get("target_type") or ""),
        "target_id": str(tombstone.get("target_id") or ""),
        "target_name": str(tombstone.get("target_name") or ""),
        "state": str(tombstone.get("state") or "DONE"),
        "actor": str(tombstone.get("actor") or ""),
        "steps": _json_literal(tombstone.get("steps")),
        "receipt": _json_literal(tombstone.get("receipt")),
    }


def plan_replay(database: str, register: dict, user: str = DEFAULT_USER,
                service: str = DEFAULT_SERVICE) -> dict:
    tables = table_columns(database, user=user, service=service)
    coverage = assert_coverage(tables)
    if "deletion_jobs" not in tables:
        raise OpsError("恢复库里没有 deletion_jobs 表:先对恢复库执行 alembic upgrade head,再重放登记")
    plans = []
    for tombstone in register["rows"]:
        target_type = tombstone.get("target_type")
        if target_type == "project":
            sql = _project_replay_sql(tables)
        elif target_type == "dataset":
            sql = _dataset_replay_sql(tables)
        else:
            raise OpsError(f"不支持的 tombstone target_type={target_type!r} (id={tombstone.get('id')!r})")
        warning = None
        if target_type == "project" and tombstone.get("target_id") != tombstone.get("project_id"):
            warning = "tombstone 的 target_id 与 project_id 不一致;重放按 project_id 清理"
        plans.append({"tombstone": tombstone, "sql": sql, "variables": _variables(tombstone),
                      "verify_sql": _verify_sql(tombstone, tables), "warning": warning})
    return {"coverage": coverage, "plans": plans, "register_rows": len(register["rows"])}


def replay(database: str, register: dict, dry_run: bool = False, user: str = DEFAULT_USER,
           service: str = DEFAULT_SERVICE) -> dict:
    """在恢复库上重新执行登记里的每次删除;返回逐条的真实删除计数与校验结果。"""
    plan = plan_replay(database, register, user=user, service=service)
    report = {"database": database, "dry_run": dry_run, "register_rows": plan["register_rows"],
              "coverage": plan["coverage"], "tombstones": [], "ok": True}
    for item in plan["plans"]:
        tombstone = item["tombstone"]
        entry = {"id": tombstone.get("id"), "target_type": tombstone.get("target_type"),
                 "target_id": tombstone.get("target_id"), "removed": {}, "remaining": {}}
        if item["warning"]:
            entry["warning"] = item["warning"]
        if dry_run:
            entry["planned_tables"] = [table for table in PURGE_TABLES
                                       if table in plan["coverage"]["project_scoped_tables"]]
            report["tombstones"].append(entry)
            continue
        removed = psql_json_rows(database, item["sql"], user=user, service=service,
                                 single_transaction=True, variables=item["variables"])
        entry["removed"] = {row["table_name"]: int(row["removed"]) for row in removed}
        remaining = psql_json_rows(database, item["verify_sql"], user=user, service=service,
                                   variables=item["variables"])
        entry["remaining"] = {row["table_name"]: int(row["remaining"]) for row in remaining}
        if any(entry["remaining"].values()):
            entry["ok"] = False
            report["ok"] = False
        report["tombstones"].append(entry)
    return report


def _cmd_export(args: argparse.Namespace) -> None:
    payload = export_register(args.database, Path(args.output), user=args.user,
                              service=args.service, source_backup=args.source_backup)
    print(f"导出删除登记 {payload['row_count']} 条 → {args.output}")


def _cmd_replay(args: argparse.Namespace) -> None:
    register = load_register(Path(args.register))
    report = replay(args.database, register, dry_run=args.dry_run, user=args.user,
                    service=args.service)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["ok"]:
        raise OpsError("重放后仍有残留:恢复库不得开放访问(见上方 remaining)")
    print("删除登记已重放,残留校验通过")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="§10.4 删除登记(tombstone)导出与重放")
    sub = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--database", default=DEFAULT_DATABASE)
    common.add_argument("--user", default=DEFAULT_USER)
    common.add_argument("--service", default=DEFAULT_SERVICE)
    export = sub.add_parser("export", parents=[common], help="把删除登记导出为独立 JSON")
    export.add_argument("--output", required=True)
    export.add_argument("--source-backup", default=None, help="对应备份文件名,写进登记文件便于追溯")
    export.set_defaults(func=_cmd_export)
    replay_parser = sub.add_parser("replay", parents=[common], help="在恢复库上重放删除登记")
    replay_parser.add_argument("--register", required=True)
    replay_parser.add_argument("--dry-run", action="store_true")
    replay_parser.set_defaults(func=_cmd_replay)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main_guard(main)
