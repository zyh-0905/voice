"""risk review fields and audit trail

Revision ID: 0008_risk_reviews_and_audits
Revises: 0007_session_idle_exp
Create Date: 2026-09-12

W14:风险裁决需要版本与裁决记录;审计为脱敏元数据,单独建表以便 OWNER 查询。
"""
from alembic import op
import sqlalchemy as sa

revision = '0008_risk_reviews_and_audits'
down_revision = '0007_session_idle_exp'
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column['name'] for column in inspector.get_columns(table)}


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade():
    # 应用启动时的 create_all 会建缺失的表,但不会补列;
    # 两者并存时必须幂等,否则先起过服务的库会在这里失败。
    existing_columns = _columns('risks')
    for name, type_ in (
        ('version', sa.Integer()),
        ('reviewed_by', sa.String(64)),
        ('review_reason', sa.Text()),
        ('reviewed_at', sa.String(64)),
    ):
        if name not in existing_columns:
            op.add_column('risks', sa.Column(name, type_, nullable=True))

    if 'risk_audits' not in _tables():
        op.create_table(
            'risk_audits',
            sa.Column('id', sa.String(64), primary_key=True),
            sa.Column('project_id', sa.String(64), nullable=False),
            sa.Column('action', sa.String(64), nullable=False),
            sa.Column('actor', sa.String(64)),
            sa.Column('detail', sa.JSON()),
            sa.Column('created_at', sa.String(64)),
        )
        op.create_index('ix_risk_audits_project_id', 'risk_audits', ['project_id'])


def downgrade():
    op.drop_index('ix_risk_audits_project_id', table_name='risk_audits')
    op.drop_table('risk_audits')
    for name in ('reviewed_at', 'review_reason', 'reviewed_by', 'version'):
        op.drop_column('risks', name)
