"""Test defaults keep the local API fixtures in demo mode."""
import os

os.environ.setdefault("AUTH_REQUIRED", "false")
# 显式开发开关:允许 http 场景下的非 Secure Cookie,并跳过无会话请求的 CSRF 校验。
# 带会话 Cookie 的写请求仍然校验 CSRF(见 test_auth_csrf.py)。
os.environ.setdefault("AUTH_INSECURE_DEV", "true")

# —— 守卫:测试套件不得连到真实数据库 ——
#
# `app.main` 在导入时按 USE_DATABASE 选仓储;为真值时它就是 SQLAlchemyRepository,
# 绑在 DATABASE_URL 指向的库上(开发库)。于是整个套件会在真实数据上建项目、写
# 数据集、跑分析——而那些夹具用的 id(`p`、`exp_demo`、`del_case_*`)从名字上
# 完全看不出是测试数据。事后清理时在 live 库里数出 51 个这样的项目、402 条反馈。
#
# 漏掉环境变量正是 `.env.example` 的默认值(docker compose run 会读它),所以这不是
# 假想的误用,是默认就踩。需要真实 PostgreSQL 的用例走 `schema_connection` /
# `schema_session_factory`:它们自建一个带 `voicelens_test_` 前缀的一次性库,
# 不依赖这个变量。因此把 USE_DATABASE 置真没有任何正当用途。
if os.getenv("USE_DATABASE", "").strip().lower() in ("1", "true", "yes"):
    raise RuntimeError(
        "USE_DATABASE 为真:测试套件会把夹具写进 DATABASE_URL 指向的真实数据库。\n"
        "请按 runbook 的方式运行:\n"
        "  docker compose run --rm -e AUTH_REQUIRED=false -e USE_DATABASE=0 api \\\n"
        "    sh -c 'PYTHONPATH=/app/services/api python -m pytest services/api/tests -q'\n"
        "需要真实 PostgreSQL 的用例(schema_connection / schema_session_factory)\n"
        "会自建一次性测试库,与本变量无关。"
    )

import pytest

# W11:topic_case 等 support fixture 需显式注册(support/ 不在 pytest 自动发现路径)
from support.client import reset_all  # noqa: E402
from support.topics import topic_case  # noqa: E402,F401


@pytest.fixture(autouse=True)
def _isolate_client_state():
    """会话 Cookie 会在用例间残留,每个用例结束后清空。"""
    yield
    reset_all()


# —— W02:真实 PostgreSQL 测试库(工程计划 11.2 schema_connection)——

import os as _os
import subprocess as _subprocess
import sys as _sys
from pathlib import Path as _Path
from uuid import uuid4 as _uuid4

import sqlalchemy as _sa
from sqlalchemy.engine import make_url as _make_url
from sqlalchemy.orm import sessionmaker as _sessionmaker

# 测试库名必须带这个前缀,否则拒绝建库/删库(计划 11.2)
TEST_DB_PREFIX = 'voicelens_test_'


def assert_test_database_name(name: str) -> None:
    """守卫:只允许对带专用前缀的库执行建库/删库。

    CI 与本地都指向一次性实例,但这条守卫保证即使有人把 DATABASE_URL 指向别的实例,
    也不会误删既有数据库——名字对不上就直接拒绝。
    """
    if not name or not name.startswith(TEST_DB_PREFIX):
        raise RuntimeError(f'refusing to touch database {name!r}: name must start with {TEST_DB_PREFIX!r}')


def _admin_url_from(database_url: str):
    """返回 (管理连接串, 目标库名)。管理连接落在一个必然存在的库上。"""
    parsed = _make_url(database_url)
    target = parsed.database or ''
    maintenance = 'postgres' if target != 'postgres' else 'template1'
    return parsed.set(database=maintenance), target


_SKIP_REASON = (
    'schema_connection 需要真实 PostgreSQL(计划 W02:不用 SQLite 代替)。'
    '设置 DATABASE_URL=postgresql+psycopg://... 后再跑。'
)


@pytest.fixture(scope='session')
def schema_connection():
    """真实且独立的 PostgreSQL 测试库,已应用全部迁移;整个会话结束后销毁。

    为什么非要用真库:内存仓储与 SQLite **都不校验列约束**,也不体现 PG 专有行为。
    `reviews.finding` 的 NOT NULL、迁移与模型在可空性上的双向不一致,在它们面前完全
    不可见——只有真实 PostgreSQL 能重现,而这正是计划 W02 要求「不用 SQLite 代替」
    的原因。

    跳过而不是失败:没有 PG 时其余用例仍应可跑;CI 里 PostgreSQL 是必备服务,
    所以这道检查在 CI 上一定执行。
    """
    database_url = _os.getenv('DATABASE_URL', '')
    if not database_url.startswith('postgresql'):
        pytest.skip(_SKIP_REASON)

    admin_url, _ = _admin_url_from(database_url)
    try:
        admin = _sa.create_engine(admin_url, isolation_level='AUTOCOMMIT')
        with admin.connect():
            pass
    except Exception as exc:  # 服务未起:跳过而不是让整套用例失败
        pytest.skip(f'{_SKIP_REASON}(连接失败: {type(exc).__name__})')

    name = f'{TEST_DB_PREFIX}{_uuid4().hex[:8]}'
    assert_test_database_name(name)
    test_url = _make_url(database_url).set(database=name)

    with admin.connect() as conn:
        conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    try:
        _apply_migrations(test_url)
        engine = _sa.create_engine(test_url)
        try:
            yield engine
        finally:
            engine.dispose()
    finally:
        _drop_database(admin, name)


@pytest.fixture(scope='session')
def schema_session_factory(schema_connection):
    """基于测试库的 sessionmaker;SQLAlchemyRepository 直接用它。"""
    return _sessionmaker(bind=schema_connection)


def _api_root() -> _Path:
    return _Path(__file__).resolve().parents[1]


def _alembic(args: list[str], database_url) -> _subprocess.CompletedProcess:
    """在子进程里跑 alembic:app.db 在导入时就固化了 DATABASE_URL,同进程换库不干净。"""
    # str(URL) 会把密码渲染成 '***'(SQLAlchemy 的防泄漏行为),子进程会因此认证失败
    dsn = database_url.render_as_string(hide_password=False) if hasattr(database_url, 'render_as_string') else str(database_url)
    env = {**_os.environ, 'DATABASE_URL': dsn, 'PYTHONPATH': str(_api_root())}
    return _subprocess.run(
        [_sys.executable, '-m', 'alembic', '-c', str(_api_root() / 'alembic.ini'), *args],
        cwd=str(_api_root()), env=env, capture_output=True, text=True,
    )


def _apply_migrations(database_url) -> None:
    result = _alembic(['upgrade', 'head'], database_url)
    if result.returncode != 0:
        raise RuntimeError(f'alembic upgrade head failed on the test database:\n{result.stderr}')


def _drop_database(admin, name: str) -> None:
    assert_test_database_name(name)
    with admin.connect() as conn:
        try:
            conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        except Exception:
            # PG < 13 不支持 WITH (FORCE):先断开连接再删
            conn.exec_driver_sql(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s", (name,))
            conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}"')
