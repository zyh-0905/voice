"""align tasks/reviews nullability with the models

Revision ID: 0019_align_nullability
Revises: 0018_task_events_and_evidence
Create Date: 2026-09-13

迁移 0003 建表时写的是 `nullable=(c in ('id','project_id','title','finding'))`
——**语义反了**:那个表达式让 id/project_id/title 可空,而其余列 NOT NULL。
于是迁移产出的 schema 与模型在 9 处不一致。

危险的方向是「迁移比模型严」:`tasks.owner` 在迁移里是 NOT NULL,而模型允许为空
——真实 PostgreSQL 上 `create_entity('tasks', ...)` 不带 owner 直接
`NotNullViolation`,而内存仓储完全看不见。这与 `reviews.finding` 是同一类缺陷
(5.2 的迁移与模型双向不一致),只是方向相反。

另一个方向(迁移比模型松)不会当场炸,但它让真实库接受模型说不存在的行。

这里把迁移对齐到**模型**(模型是权威),并把可空性比对并入
`test_migrated_schema_matches_models` —— 那条测试此前只比列名,所以这两类差异
它一个都没拦住。

revision id 刻意压在 32 字符内:alembic 的 `alembic_version.version_num` 是
varchar(32),写超了会在**升级到该版本的最后一刻**炸,而那时前面的 DDL 都已执行。
"""
from alembic import op
import sqlalchemy as sa

revision = '0019_align_nullability'
down_revision = '0018_task_events_and_evidence'
branch_labels = None
depends_on = None

# (表, 列, 目标 nullable, 收紧前用的回填值)
# 收紧为 NOT NULL 之前必须先回填:表里可能已经有 NULL(0006 回填过 state/version,
# 但那是它自己的升级路径;别的路径进来的行不保证)。
ALIGN = [
    ('tasks', 'id', False, None),
    ('tasks', 'project_id', False, None),
    ('tasks', 'title', False, None),
    ('tasks', 'state', False, 'DRAFT'),
    ('tasks', 'version', False, 1),
    ('tasks', 'effect_status', False, 'NOT_EVALUATED'),
    ('tasks', 'owner', True, None),
    ('reviews', 'id', False, None),
    ('reviews', 'project_id', False, None),
]


def _current_nullability(bind) -> dict:
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    return {table: {c['name']: c['nullable'] for c in inspector.get_columns(table)}
            for table in ('tasks', 'reviews') if table in tables}


def upgrade():
    bind = op.get_bind()
    before = _current_nullability(bind)
    metadata = sa.MetaData()
    for table_name, column, nullable, backfill in ALIGN:
        if table_name not in {t for t in sa.inspect(bind).get_table_names()}:
            continue
        if before.get(table_name, {}).get(column) == nullable:
            continue
        if not nullable and backfill is not None:
            table = sa.Table(table_name, metadata, autoload_with=bind)
            bind.execute(table.update().where(table.c[column].is_(None)).values({column: backfill}))
            metadata = sa.MetaData()  # 反射缓存作废
        # sqlite 不支持 ALTER COLUMN,batch 模式会重建表——所以「全新建库能否到 head」
        # 这条 sqlite 闸门也能覆盖到这里
        with op.batch_alter_table(table_name) as batch:
            batch.alter_column(column, existing_type=sa.String(), nullable=nullable,
                               existing_nullable=before.get(table_name, {}).get(column))


def downgrade():
    """回到 0003 那份「反了」的约束。

    刻意恢复成错的:降级的目标是「旧代码能跑」,而旧代码在这些列可空/非空上
    依赖的正是旧行为。改回去不丢数据。
    """
    bind = op.get_bind()
    current = _current_nullability(bind)
    for table_name, column, _nullable, _backfill in ALIGN:
        if table_name not in current:
            continue
        legacy_nullable = column in ('id', 'project_id', 'title')
        if current[table_name].get(column) == legacy_nullable:
            continue
        with op.batch_alter_table(table_name) as batch:
            batch.alter_column(column, existing_type=sa.String(), nullable=legacy_nullable,
                               existing_nullable=current[table_name].get(column))
