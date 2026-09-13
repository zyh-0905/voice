"""为 real-api E2E 准备专用 PostgreSQL 库,并在其之上启动 API。

**为什么要这一步。** 真实套件此前跑在 `USE_DATABASE=0`(内存仓储)上,于是它验证
的是「HTTP 契约一致」,而不是「真实持久化下走得通」。这一轮已经三次出现
「内存模式全绿、SQL 模式炸」:

- `AnalysisStage.config_hash == x or ''` 的优先级 → 整条流水线 status='error'
- `tasks.owner` 迁移里 NOT NULL 而模型可空 → 真实库直接 NotNullViolation
- 删除顺序未先删候选 → 复合外键拒绝删除

内存仓储不校验列约束、不校验外键,这三类它一个都看不见——而它们恰恰只在真实部署
上炸。所以套件必须连真库跑。

**库名带 `voicelens_test_` 前缀**,与后端套件(conftest 的 schema_connection)
同一约定:即使有人把连接串指到别的实例,前缀守卫也会拦住误删既有数据库。

用法(由 playwright.real.config.ts 调用):
    python scripts/e2e_server.py --port 8010
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / 'services' / 'api'
TEST_DATABASE_PREFIX = 'voicelens_test_'
DEFAULT_TEST_DATABASE = 'voicelens_test_e2e'
DEFAULT_ADMIN_URL = 'postgresql+psycopg://voicelens:voicelens@127.0.0.1:5433/voicelens'


def assert_test_database_name(name: str) -> None:
    """守卫:只允许对带专用前缀的库执行建库/删库(计划 11.2)。"""
    if not name or not name.startswith(TEST_DATABASE_PREFIX):
        raise RuntimeError(f'refusing to touch database {name!r}: name must start with {TEST_DATABASE_PREFIX!r}')


def _split(url: str):
    from sqlalchemy.engine import make_url
    return make_url(url)


def prepare_database(admin_url: str, test_name: str) -> str:
    """重建测试库并升到 head,返回指向它的连接串。"""
    import sqlalchemy as sa

    assert_test_database_name(test_name)
    parsed = _split(admin_url)
    target = parsed.database or ''
    maintenance = 'postgres' if target != 'postgres' else 'template1'
    admin = sa.create_engine(parsed.set(database=maintenance), isolation_level='AUTOCOMMIT')

    with admin.connect() as conn:
        # 先断开旧连接,否则 DROP 会挂在「有会话在用」上;上一轮失败留下的连接
        # 会让这一次也起不来,表现成「套件偶发跑不起来」
        conn.exec_driver_sql(
            'SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s', (test_name,))
        conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{test_name}"')
        conn.exec_driver_sql(f'CREATE DATABASE "{test_name}"')

    test_url = parsed.set(database=test_name)
    dsn = test_url.render_as_string(hide_password=False)
    result = subprocess.run(
        [sys.executable, '-m', 'alembic', '-c', 'alembic.ini', 'upgrade', 'head'],
        cwd=str(API_ROOT), env={**os.environ, 'DATABASE_URL': dsn, 'PYTHONPATH': str(API_ROOT)},
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f'alembic upgrade head failed on {test_name}:\n{result.stderr}')
    return dsn


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=int(os.getenv('REAL_API_PORT', '8010')))
    # 绑到 127.0.0.1 时容器外的端口映射到不了它——在容器里跑必须绑 0.0.0.0,
    # 而表现是「服务起来了但探针连不上」,看起来像启动太慢
    parser.add_argument('--host', default=os.getenv('REAL_API_HOST', '127.0.0.1'))
    args = parser.parse_args()

    admin_url = os.getenv('REAL_API_DATABASE_URL', DEFAULT_ADMIN_URL)
    test_name = os.getenv('REAL_API_TEST_DATABASE', DEFAULT_TEST_DATABASE)
    try:
        dsn = prepare_database(admin_url, test_name)
    except Exception as exc:  # 连不上库时给一句能照着做的提示,而不是一堆栈
        print(f'real-api E2E 需要可达的 PostgreSQL: {exc}', file=sys.stderr)
        print(f'管理员连接串来自 REAL_API_DATABASE_URL(当前 {admin_url!r})。', file=sys.stderr)
        print('本地可用 `docker compose -f compose.yaml -f compose.e2e.yaml up -d postgres`。', file=sys.stderr)
        return 2

    print(f'real-api E2E 使用测试库 {test_name}(已升到 head)', file=sys.stderr)
    os.environ.update({
        'DATABASE_URL': dsn,
        'USE_DATABASE': '1',
        'PYTHONPATH': str(API_ROOT),
    })
    # exec:让 uvicorn 接管这个进程,Playwright 关掉它时不需要再转发信号
    os.execv(sys.executable, [
        sys.executable, '-m', 'uvicorn', 'app.main:app',
        '--host', args.host, '--port', str(args.port),
    ])


if __name__ == '__main__':
    raise SystemExit(main())
