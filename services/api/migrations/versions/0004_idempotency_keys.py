"""idempotency keys

Revision ID: 0004_idempotency_keys
Revises: 0003_domain_entities
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa

revision = '0004_idempotency_keys'
down_revision = '0003_domain_entities'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'idempotency_keys',
        sa.Column('key', sa.String(128), primary_key=True),
        sa.Column('project_id', sa.String(64), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('analysis_id', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_idempotency_keys_project_id', 'idempotency_keys', ['project_id'])


def downgrade():
    op.drop_index('ix_idempotency_keys_project_id', table_name='idempotency_keys')
    op.drop_table('idempotency_keys')
