"""备份/恢复脚本的共用底座:数据库只经 `docker compose exec postgres` 访问。

为什么只走这一条路:compose 里 postgres 不发布端口(§14.2 要求数据库只在内网),
宿主机能用的唯一通道就是 exec。备份与恢复共用同一个传输层,才不会出现
「备份能跑、恢复连不上」这种只在真演练里暴露的差异。

直连形式(生产备份机上 pg_dump 直连 DATABASE_URL)见 docs/runbooks/restore.md;
本文件不实现它,因为两条路径的转义、超时和错误处理必须一起验证,只在一边实现
等于制造一个没演练过的分支。

脚本只用标准库:宿主机与容器里都不一定装得下别的依赖,备份工具链越少越好。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO_ROOT / "services" / "api" / "migrations" / "versions"
DEFAULT_SERVICE = "postgres"
DEFAULT_DATABASE = "voicelens"
DEFAULT_USER = "voicelens"


class OpsError(RuntimeError):
    """外部命令失败或数据不满足前置条件;调用方负责 exit 2。"""


def compose_cmd() -> list:
    """定位 docker compose 可执行形式:优先 `docker compose`,退回 `docker-compose`。"""
    if shutil.which("docker"):
        return ["docker", "compose"]
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    raise OpsError("docker compose not found on PATH")


def run(cmd: list, stdin=None, stdout=None, capture: bool = True,
        cwd: Path | None = None, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    """执行命令;非零退出统一转成 OpsError,并带上真实 stderr。

    无输入时显式关掉 stdin:docker compose exec 在 cron/CI 下继承到 TTY 会挂住,
    这类挂起在人工演练里看不出来。
    """
    result = subprocess.run(
        cmd,
        cwd=str(cwd or REPO_ROOT),
        input=input_bytes,
        stdin=subprocess.DEVNULL if (stdin is None and input_bytes is None) else stdin,
        stdout=stdout if stdout is not None else (subprocess.PIPE if capture else None),
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        stderr = (result.stderr or b"").decode("utf-8", "replace").strip()
        raise OpsError(f"command failed ({result.returncode}): {' '.join(cmd)}\n{stderr}")
    return result


def exec_in(service: str, args: list, stdin=None, stdout=None, capture: bool = True,
            input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    """在 compose 服务里执行命令;-T 关闭 TTY,否则 cron/管道下会挂住。"""
    return run(compose_cmd() + ["exec", "-T", service] + args,
               stdin=stdin, stdout=stdout, capture=capture, input_bytes=input_bytes)


def psql(database: str, sql: str, user: str = DEFAULT_USER,
         service: str = DEFAULT_SERVICE, single_transaction: bool = False,
         variables: dict | None = None) -> str:
    """执行 SQL 并返回 -tA 文本输出;--single-transaction 保证重放不会半途生效。

    SQL 走 stdin 而不是 `-c`:psql 的 `:'变量'` 展开只对 stdin/文件生效,
    用 `-c` 会把占位符原样发给服务器(报 syntax error at or near ":")。
    """
    # -q 抑制 SET 之类的命令标签:否则脚本里的 SET TRANSACTION READ ONLY 会被
    # 当成一行输出,和逐行 JSON 解析撞车
    args = ["psql", "-U", user, "-d", database, "-v", "ON_ERROR_STOP=1", "-tA", "-q"]
    if single_transaction:
        args.append("-1")
    for key, value in (variables or {}).items():
        args += ["-v", f"{key}={value}"]
    result = exec_in(service, args, input_bytes=sql.encode("utf-8"))
    return (result.stdout or b"").decode("utf-8")


def psql_scalar(database: str, sql: str, **kwargs) -> str:
    return psql(database, sql, **kwargs).strip()


def psql_json_rows(database: str, sql: str, **kwargs) -> list:
    """把 `select row_to_json(t) from (...) t` 的逐行 JSON 解析成 dict 列表。"""
    rows = []
    for line in psql(database, sql, **kwargs).splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise OpsError(f"file not found: {path}")
    except json.JSONDecodeError as exc:
        raise OpsError(f"invalid JSON in {path}: {exc}")


def human_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"


def require_artifact(path: Path) -> Path:
    if not path.is_file():
        raise OpsError(f"artifact missing: {path}")
    return path


def main_guard(entry) -> None:
    """统一入口:OpsError 打一行真实原因并 exit 2,不吞堆栈用于排查的其它异常。"""
    try:
        entry()
    except OpsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)


def migration_head() -> str:
    """从迁移文件推导 head,不依赖 alembic 可执行文件。

    恢复机上只需要 psql/docker;把 head 算成「没有任何迁移把它当 down_revision」
    的那个 revision。出现多个 head(分支)时直接报错而不是随便挑一个。
    """
    revision_re = re.compile(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE)
    down_re = re.compile(r"^down_revision\s*=\s*(?:['\"]([^'\"]+)['\"]|None)", re.MULTILINE)
    revisions, referenced = {}, set()
    for path in sorted(MIGRATIONS_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        revision = revision_re.search(text)
        if not revision:
            raise OpsError(f"{path.name}: 找不到 revision 声明")
        revisions[revision.group(1)] = path.name
        down = down_re.search(text)
        if down and down.group(1):
            referenced.add(down.group(1))
    heads = sorted(set(revisions) - referenced)
    if len(heads) != 1:
        raise OpsError(f"迁移目录存在 {len(heads)} 个 head: {heads};恢复前的版本检查需要唯一 head")
    return heads[0]


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        raise OpsError(f"{name} must be an integer, got {raw!r}")
