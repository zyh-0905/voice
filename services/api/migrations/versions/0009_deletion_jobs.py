"""deletion jobs (10.4)

Revision ID: 0009_deletion_jobs
Revises: 0008_risk_reviews_and_audits
Create Date: 2026-09-12

删除登记独立于项目数据:项目被清理后仍可查最小回执;回执不含正文。
表已存在时跳过,保证与 create_all 并存时幂等。
"""
from alembic import op
import sqlalchemy as sa

revision = '0009_deletion_jobs'
down_revision = '0008_risk_reviews_and_audits'
branch_labels = None
depends_on = None


def upgrade():
    if 'deletion_jobs' in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        'deletion_jobs',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('project_id', sa.String(64), nullable=False),
        sa.Column('target_type', sa.String(32), nullable=False),
        sa.Column('target_id', sa.String(64), nullable=False),
        sa.Column('target_name', sa.String(255)),
        sa.Column('state', sa.String(32), nullable=False, server_default='RUNNING'),
        sa.Column('actor', sa.String(64)),
        sa.Column('steps', sa.JSON()),
        sa.Column('receipt', sa.JSON()),
    )
    op.create_index('ix_deletion_jobs_project_id', 'deletion_jobs', ['project_id'])


def downgrade():
    op.drop_index('ix_deletion_jobs_project_id', table_name='deletion_jobs')
    op.drop_table('deletion_jobs')
