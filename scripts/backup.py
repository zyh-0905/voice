"""W21/§10.4 备份:pg_dump 全库 + 独立删除登记 + SHA-256 manifest。

三个产物各自解决一件计划里点名的事:

- `<db>-<ts>.dump`            pg_dump 自定义格式(可选择性恢复,pg_restore 可校验);
- `<db>-<ts>.tombstones.json` 删除登记。§10.4 要求它「不得只存在于将被旧备份
  覆盖的数据库里」——dump 本身会被下一次恢复覆盖,登记文件不会;
- `<db>-<ts>.manifest.json`   SHA-256、字节数、迁移版本、保留天数。

诚实说明:

- **产物未加密。** 计划 14.1 提到「备份密钥与数据库口令不得使用相同值」,本脚本
  没有实现静态加密,所以备份必须落在加密介质/受控目录,且不得进入交付包(§14.6)。
  加解密要真做需要独立密钥管理与演练,不是这里加一行能算交付的。
- **默认只备份、不清理。** 「初始保留7天」在计划里明确是建议工程策略、未经企业
  认可;自动删除不可逆,所以清理必须显式 `--prune`,保留天数仍写进 manifest 备查。
- 只支持 `docker compose exec postgres` 通道(§14.2 数据库不对外发布端口);
  直连形式见 docs/runbooks/restore.md。

用法:
    python3 scripts/backup.py                      # 备份到 backups/
    python3 scripts/backup.py --prune              # 顺带按保留天数清理旧产物
    BACKUP_DIR=/srv/voicelens-backups python3 scripts/backup.py
"""
from __future__ import annotations

import argparse
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ops_common import (DEFAULT_DATABASE, DEFAULT_SERVICE, DEFAULT_USER, REPO_ROOT,
                        OpsError, env_int, exec_in, human_bytes, main_guard, psql_scalar,
                        require_artifact, sha256_file, write_json)

MANIFEST_VERSION = 1
GITIGNORE = "# 备份产物:禁止进仓库(§14.6 不得把生产数据库备份打进交付包)\n*\n!.gitignore\n"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%SZ")


def _prefix(database: str, label: str | None) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", label) if label else None
    return f"{database}-{safe}" if safe else database


def _ensure_out_dir(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    ignore = out_dir / ".gitignore"
    inside_repo = REPO_ROOT in out_dir.resolve().parents
    if inside_repo and not ignore.exists():
        # 仓库里 runbook 明确要求「不要 git add -A」;少了这行,备份会被误提交
        ignore.write_text(GITIGNORE, encoding="utf-8")


def _pg_dump(out_dir: Path, name: str, database: str, user: str, service: str) -> Path:
    path = out_dir / f"{name}.dump"
    with open(path, "wb") as handle:
        exec_in(service, ["pg_dump", "-U", user, "-d", database, "--format=custom",
                          "--compress=6", "--no-owner", "--no-privileges"], stdout=handle)
    return path


def _archive_entries(path: Path, service: str) -> int:
    """用 pg_restore -l 读一遍归档:证明它是可解析的 dump,而不是一段字节。"""
    with open(path, "rb") as handle:
        result = exec_in(service, ["pg_restore", "-l"], stdin=handle)
    lines = (result.stdout or b"").decode("utf-8", "replace").splitlines()
    return sum(1 for line in lines if line.strip() and not line.startswith(";"))


def _database_facts(database: str, user: str, service: str) -> dict:
    return {
        "postgres_version": psql_scalar(database, "select version()", user=user, service=service),
        "alembic_revision": psql_scalar(database, "select version_num from alembic_version",
                                        user=user, service=service),
    }


def create_backup(out_dir: Path, database: str = DEFAULT_DATABASE, user: str = DEFAULT_USER,
                  service: str = DEFAULT_SERVICE, label: str | None = None,
                  keep_days: int = 7) -> dict:
    from tombstone_register import export_register  # 同目录脚本,避免 ops_common 反向依赖

    _ensure_out_dir(out_dir)
    moment = _now()
    name = f"{_prefix(database, label)}-{_stamp(moment)}"
    facts = _database_facts(database, user, service)

    dump_path = _pg_dump(out_dir, name, database, user, service)
    require_artifact(dump_path)
    entries = _archive_entries(dump_path, service)

    register_path = out_dir / f"{name}.tombstones.json"
    register = export_register(database, register_path, user=user, service=service,
                               source_backup=dump_path.name)

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "created_at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool": "scripts/backup.py",
        "database": database,
        "source": {"service": service, "user": user},
        "postgres_version": facts["postgres_version"],
        "alembic_revision": facts["alembic_revision"],
        "retention_days": keep_days,
        "encrypted": False,
        "artifacts": [
            {"role": "database", "name": dump_path.name, "format": "pg_dump/custom",
             "bytes": dump_path.stat().st_size, "sha256": sha256_file(dump_path),
             "pg_restore_entries": entries},
            {"role": "deletion_register", "name": register_path.name, "format": "json",
             "bytes": register_path.stat().st_size, "sha256": sha256_file(register_path),
             "rows": register["row_count"]},
        ],
    }
    manifest_path = out_dir / f"{name}.manifest.json"
    write_json(manifest_path, manifest)
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def prune(out_dir: Path, prefix: str, keep_days: int, now: datetime) -> list:
    """按 manifest 的 created_at 清理过期产物;读不懂的 manifest 一律不动。"""
    from ops_common import read_json

    cutoff = now - timedelta(days=keep_days)
    removed, skipped = [], []
    for manifest_path in sorted(out_dir.glob(f"{prefix}-*.manifest.json")):
        try:
            manifest = read_json(manifest_path)
            created = datetime.strptime(manifest["created_at"], "%Y-%m-%dT%H:%M:%SZ")
            created = created.replace(tzinfo=timezone.utc)
        except (OpsError, KeyError, ValueError) as exc:
            skipped.append(f"{manifest_path.name} ({exc})")
            continue
        if created >= cutoff:
            continue
        for artifact in manifest.get("artifacts", []):
            target = out_dir / artifact["name"]
            if target.exists():
                target.unlink()
                removed.append(target.name)
        manifest_path.unlink()
        removed.append(manifest_path.name)
    return [removed, skipped]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VoiceLens 备份(pg_dump + 删除登记 + manifest)")
    parser.add_argument("--out-dir", default=None, help="产物目录,默认 $BACKUP_DIR 或 backups/")
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--service", default=DEFAULT_SERVICE)
    parser.add_argument("--label", default=None, help="产物名附加标签,如 nightly")
    parser.add_argument("--keep-days", type=int, default=None,
                        help="保留天数,默认 $BACKUP_RETENTION_DAYS 或 7;只写入 manifest")
    parser.add_argument("--prune", action="store_true",
                        help="按保留天数删除旧产物(默认不删;保留周期未经企业确认)")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    import os
    out_dir = Path(args.out_dir or os.getenv("BACKUP_DIR") or (REPO_ROOT / "backups"))
    keep_days = args.keep_days if args.keep_days is not None else env_int("BACKUP_RETENTION_DAYS", 7)
    if keep_days < 1:
        raise OpsError("--keep-days 必须 >= 1")
    if shutil.which("docker") is None and shutil.which("docker-compose") is None:
        raise OpsError("docker compose not found on PATH")
    manifest = create_backup(out_dir, database=args.database, user=args.user,
                             service=args.service, label=args.label, keep_days=keep_days)
    total = sum(item["bytes"] for item in manifest["artifacts"])
    print(f"备份完成: {manifest['manifest_path']}")
    for item in manifest["artifacts"]:
        extra = (f"{item['rows']} 条登记" if item["role"] == "deletion_register"
                 else f"{item['pg_restore_entries']} 个归档条目")
        print(f"  - {item['name']}  {human_bytes(item['bytes'])}  {extra}  sha256={item['sha256']}")
    print(f"  迁移版本 {manifest['alembic_revision']} / PostgreSQL {manifest['postgres_version'].split()[1]}"
          f" / 未加密(见脚本 docstring) / 保留 {manifest['retention_days']} 天{' (本次已清理)' if args.prune else ''}")
    if args.prune:
        removed, skipped = prune(out_dir, _prefix(args.database, args.label), keep_days, _now())
        print(f"清理 {len(removed)} 个过期产物" + (f";跳过 {len(skipped)} 个: {skipped}" if skipped else ""))
    if total <= 0:
        raise OpsError("备份产物为空")


if __name__ == "__main__":
    main_guard(main)
