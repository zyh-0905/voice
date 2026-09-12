"""export jobs (10.3)

Revision ID: 0010_export_jobs
Revises: 0009_deletion_jobs
Create Date: 2026-09-12

24 小时失效、下载重新鉴权、删除后失效;表存在时跳过(与 create_all 并存)。
"""
from alembic import op
import sqlalchemy as sa

revision = '0010_export_jobs'
down_revision = '0009_deletion_jobs'
branch_labels = None
depends_on = None


def upgrade():
    if 'export_jobs' in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        'export_jobs',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('project_id', sa.String(64), nullable=False),
        sa.Column('scope', sa.String(64), nullable=False),
        sa.Column('state', sa.String(32), nullable=False, server_default='DONE'),
        sa.Column('columns', sa.JSON()),
        sa.Column('row_count', sa.Integer()),
        sa.Column('content', sa.Text()),
        sa.Column('actor', sa.String(64)),
        sa.Column('created_at', sa.String(64)),
        sa.Column('expires_at', sa.String(64)),
        sa.Column('invalidated', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index('ix_export_jobs_project_id', 'export_jobs', ['project_id'])


def downgrade():
    op.drop_index('ix_export_jobs_project_id', table_name='export_jobs')
    op.drop_table('export_jobs')
