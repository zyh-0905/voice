"""全新建库必须能一口气升到 head,且结果与模型定义一致。

`0001_initial` 并不是冻结快照——它 `from app.models import ...` 后按**当时的**
模型建表。因此每次给模型加列,都会让「后续某个迁移再添加同一列」在全新库上撞
DuplicateColumn,而开发库因为先 create_all 再打标完全无感。

读 README 的运维(以及 compose 的 migrate 服务)走的正是全新库这条路,所以这一类
回归必须有闸。两份断言:
  1. 全新库能 upgrade 到 head;
  2. upgrade 出来的 schema 与 create_all 出来的 schema 一致(防双向漂移)。
"""
import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

_API_ROOT = Path(__file__).resolve().parents[1]


def _fresh_url(tmp_path: Path, name: str) -> str:
    return f'sqlite:///{tmp_path / name}'


def _upgrade_to_head(url: str) -> subprocess.CompletedProcess:
    """在子进程里跑 alembic:app.db 在导入时就固化了 DATABASE_URL,同进程换库不干净。"""
    env = {**os.environ, 'DATABASE_URL': url, 'PYTHONPATH': str(_API_ROOT)}
    return subprocess.run(
        [sys.executable, '-m', 'alembic', '-c', str(_API_ROOT / 'alembic.ini'), 'upgrade', 'head'],
        cwd=str(_API_ROOT), env=env, capture_output=True, text=True,
    )


def _schema(engine) -> dict[str, set[str]]:
    inspector = sa.inspect(engine)
    return {table: {column['name'] for column in inspector.get_columns(table)}
            for table in inspector.get_table_names() if table != 'alembic_version'}


def test_fresh_database_upgrades_to_head(tmp_path):
    url = _fresh_url(tmp_path, 'fresh.db')
    result = _upgrade_to_head(url)
    assert result.returncode == 0, (
        '全新建库无法 upgrade 到 head——全新部署会起不来\n'
        f'stdout:\n{result.stdout}\nstderr:\n{result.stderr}'
    )

    engine = sa.create_engine(url)
    tables = set(sa.inspect(engine).get_table_names())
    assert {'projects', 'datasets', 'memberships', 'idempotency_keys'} <= tables


def test_migrated_schema_matches_models(tmp_path):
    """迁移路径与 create_all 路径必须收敛到同一份 schema。

    只修「升得上去」不够:0001 从模型建表、后续迁移再补,两条路径很容易各自漂移。
    """
    from app.db import Base
    from app import models  # noqa: F401  —— 触发表注册

    url = _fresh_url(tmp_path, 'migrated.db')
    result = _upgrade_to_head(url)
    assert result.returncode == 0, result.stderr

    model_url = _fresh_url(tmp_path, 'models.db')
    model_engine = sa.create_engine(model_url)
    Base.metadata.create_all(model_engine)

    migrated = _schema(sa.create_engine(url))
    modelled = _schema(model_engine)

    assert set(migrated) == set(modelled), (
        f'表集合不一致\n迁移多出: {sorted(set(migrated) - set(modelled))}\n'
        f'模型多出: {sorted(set(modelled) - set(migrated))}'
    )
    for table in sorted(migrated):
        assert migrated[table] == modelled[table], (
            f'{table} 列不一致\n迁移多出: {sorted(migrated[table] - modelled[table])}\n'
            f'模型多出: {sorted(modelled[table] - migrated[table])}'
        )
