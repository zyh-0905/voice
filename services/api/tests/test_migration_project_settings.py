"""迁移 0012:项目设置列与成员表(工程计划 5.2 / W03)。

应用启动的 create_all 与 alembic 并存:先 create_all 再 upgrade 必须无操作;
旧 schema(只有 0011 之前的表)升级后新列/新表可用,downgrade 清理干净。
"""
import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import Base

_MIGRATION_PATH = (Path(__file__).resolve().parents[1]
                   / 'migrations' / 'versions' / '0012_settings_memberships.py')


def _load_migration():
    spec = importlib.util.spec_from_file_location('migration_0012', _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_is_noop_after_create_all(tmp_path):
    engine = sa.create_engine(f'sqlite:///{tmp_path}/mig12a.db')
    Base.metadata.create_all(engine)
    module = _load_migration()
    with engine.begin() as conn:
        module.op = Operations(MigrationContext.configure(conn))
        module.upgrade()
        module.upgrade()  # 与 create_all 并存时第二次必须是空操作
    with engine.begin() as conn:
        inspector = sa.inspect(conn)
        assert {'timezone', 'settings_json'} <= {c['name'] for c in inspector.get_columns('projects')}
        assert 'memberships' in inspector.get_table_names()
        assert {'ix_memberships_project_id', 'ix_memberships_user_id'} <= {
            index['name'] for index in inspector.get_indexes('memberships')}


def test_upgrade_and_downgrade_old_schema(tmp_path):
    engine = sa.create_engine(f'sqlite:///{tmp_path}/mig12b.db')
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE projects (id VARCHAR(64) PRIMARY KEY, name VARCHAR(255) NOT NULL)')
        conn.exec_driver_sql("INSERT INTO projects (id, name) VALUES ('p1', '旧项目')")
    module = _load_migration()

    with engine.begin() as conn:
        module.op = Operations(MigrationContext.configure(conn))
        module.upgrade()
    with engine.begin() as conn:
        inspector = sa.inspect(conn)
        assert {'timezone', 'settings_json'} <= {c['name'] for c in inspector.get_columns('projects')}
        assert 'memberships' in inspector.get_table_names()
        # 旧行保留,新列可空
        assert conn.exec_driver_sql('SELECT timezone, settings_json FROM projects WHERE id = \'p1\'').fetchone() == (None, None)

    with engine.begin() as conn:
        module.op = Operations(MigrationContext.configure(conn))
        module.downgrade()
    with engine.begin() as conn:
        inspector = sa.inspect(conn)
        assert 'memberships' not in inspector.get_table_names()
        assert not {'timezone', 'settings_json'} & {c['name'] for c in inspector.get_columns('projects')}
