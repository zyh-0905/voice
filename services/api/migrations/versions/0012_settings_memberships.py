"""project settings and memberships (7.2 / W03)

Revision ID: 0012_settings_memberships
Revises: 0011_redact_stored_rows
Create Date: 2026-09-12

W03:项目需要 timezone 与 settings_json,成员关系落 memberships 表。
应用启动的 create_all 与 alembic 并存,迁移必须幂等(0008/0010 同款守卫):
create_all 只会建缺失的表、不会补列,先起过服务的库也要能升级。

revision id 必须短于 alembic 版本列的 VARCHAR(32)——超长会让 Postgres 写版本号时
报 StringDataRightTruncation 并回滚整个迁移。保持与既有 0001-0011 一致的短命名,
不要去改 alembic 自己的记账表。
"""
from alembic import op
import sqlalchemy as sa

revision = '0012_settings_memberships'
down_revision = '0011_redact_stored_rows'
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {column['name'] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    if 'projects' in _tables():
        existing = _columns('projects')
        for name, type_ in (('timezone', sa.String(64)), ('settings_json', sa.JSON())):
            if name not in existing:
                op.add_column('projects', sa.Column(name, type_, nullable=True))

    if 'memberships' not in _tables():
        op.create_table(
            'memberships',
            sa.Column('project_id', sa.String(64), nullable=False),
            sa.Column('user_id', sa.String(64), nullable=False),
            sa.Column('role', sa.String(16), nullable=False),
            sa.Column('display_name', sa.String(255)),
            sa.UniqueConstraint('project_id', 'user_id', name='uq_memberships_project_user'),
        )
        op.create_index('ix_memberships_project_id', 'memberships', ['project_id'])
        op.create_index('ix_memberships_user_id', 'memberships', ['user_id'])


def downgrade():
    if 'memberships' in _tables():
        op.drop_index('ix_memberships_user_id', table_name='memberships')
        op.drop_index('ix_memberships_project_id', table_name='memberships')
        op.drop_table('memberships')
    if 'projects' in _tables():
        existing = _columns('projects')
        for name in ('settings_json', 'timezone'):
            if name in existing:
                op.drop_column('projects', name)
