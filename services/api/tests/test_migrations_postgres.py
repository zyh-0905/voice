"""W02:数据模型与真实 PostgreSQL 测试库。

计划 11.2 要求 `schema_connection` 提供「真实独立 PostgreSQL 测试库,已应用全部当前
迁移」,并明文规定**不用 SQLite 代替**。原因在这里的用例里看得很直接:内存仓储和
SQLite 都不校验列约束,`reviews.finding` 的 NOT NULL、迁移与模型在可空性上的不一致
这类问题在它们面前完全不可见,却会让真实部署返回 500。

计划把这些用例放在 tests/integration/;本仓库自 W01 起测试就是扁平结构
(tests/support/* 与 tests/test_*.py),这里沿用仓库既有布局。
"""
import sqlalchemy as sa
import pytest

from conftest import TEST_DB_PREFIX, assert_test_database_name


# —— 迁移后的 schema ——

def test_migrated_tables_exist(schema_connection):
    """空库执行 alembic upgrade head 后,业务表与记账表都在(计划 W02 示例)。"""
    tables = set(sa.inspect(schema_connection).get_table_names())
    assert {
        'projects', 'memberships', 'datasets', 'analysis_runs', 'reviews',
        'risks', 'tasks', 'idempotency_keys', 'outbox_events', 'export_jobs',
    } <= tables
    assert 'alembic_version' in tables


def test_application_writes_succeed_on_the_migrated_schema(schema_session_factory):
    """应用的写入形状必须能通过迁移产出的真实约束。

    这条是本文件的重点:同一形状在内存仓储上永远通过——它不校验 NOT NULL。
    """
    from app.sql_repository import SQLAlchemyRepository

    repo = SQLAlchemyRepository(session_factory=schema_session_factory)
    repo.create_entity('reviews', {
        'id': 'rv_pg', 'project_id': 'p', 'run_id': 'run_1', 'revision': 1,
        'topic_version_ids': ['t1'], 'task_id': None,
        'before': {'n': 1, 'N': 2}, 'after': {'n': 1, 'N': 2},
        'metrics': None, 'effect_status': 'INSUFFICIENT_DATA', 'limitations': [],
    })
    assert [item['id'] for item in repo.list_entities('reviews', 'p')] == ['rv_pg']


# —— 约束错误可被重现(计划 W02 完成定义) ——

def test_membership_uniqueness_is_enforced_by_the_database(schema_session_factory):
    from app.sql_repository import SQLAlchemyRepository

    repo = SQLAlchemyRepository(session_factory=schema_session_factory)
    repo.create_membership({'project_id': 'p_uniq', 'user_id': 'u1', 'role': 'OWNER'})
    with pytest.raises(ValueError):
        repo.create_membership({'project_id': 'p_uniq', 'user_id': 'u1', 'role': 'VIEWER'})


def test_idempotency_key_uniqueness_is_enforced(schema_session_factory):
    from app.sql_repository import SQLAlchemyRepository

    repo = SQLAlchemyRepository(session_factory=schema_session_factory)
    repo.create_idempotency('key_dup', {'project_id': 'p', 'fingerprint': 'f', 'analysis_id': 'run_1'})
    with pytest.raises(ValueError):
        repo.create_idempotency('key_dup', {'project_id': 'p', 'fingerprint': 'f', 'analysis_id': 'run_2'})


def test_not_null_is_enforced_where_the_model_requires_it(schema_connection):
    """模型声明 NOT NULL 的列,在真库里确实拒绝空值——否则约束只存在于文档里。"""
    with schema_connection.begin() as conn:
        with pytest.raises(sa.exc.IntegrityError):
            conn.exec_driver_sql(
                "INSERT INTO datasets (id, project_id, filename, status) VALUES ('d1', 'p', NULL, 'uploaded')")


# —— 库名守卫 ——

def test_database_name_guard_rejects_foreign_names():
    """守卫必须拒绝非专用前缀的库名——它挡的是误删别人的库,不能只是形式。"""
    assert_test_database_name(f'{TEST_DB_PREFIX}abcd1234')
    for name in ('voicelens', 'postgres', '', 'template1', 'voicelens_test'):
        with pytest.raises(RuntimeError):
            assert_test_database_name(name)
