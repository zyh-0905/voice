"""session tokens

Revision ID: 0005_session_tokens
Revises: 0004_idempotency_keys
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa

revision = '0005_session_tokens'
down_revision = '0004_idempotency_keys'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'session_tokens',
        sa.Column('token', sa.String(128), primary_key=True),
        sa.Column('user_id', sa.String(64), nullable=False),
        sa.Column('role', sa.String(32), nullable=False),
        sa.Column('projects', sa.JSON(), nullable=False),
        sa.Column('issued_at', sa.Float(), nullable=False),
        sa.Column('exp', sa.Float(), nullable=False),
    )
    op.create_index('ix_session_tokens_user_id', 'session_tokens', ['user_id'])


def downgrade():
    op.drop_index('ix_session_tokens_user_id', table_name='session_tokens')
    op.drop_table('session_tokens')
