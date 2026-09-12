"""session idle expiry

Revision ID: 0007_session_idle_exp
Revises: 0006_domain_state_columns
Create Date: 2026-09-10

会话空闲过期:每次访问滑动续期,超过 AUTH_IDLE_SECONDS 未使用即失效。
"""
from alembic import op
import sqlalchemy as sa

revision = '0007_session_idle_exp'
down_revision = '0006_domain_state_columns'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('session_tokens', sa.Column('idle_exp', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('session_tokens', 'idle_exp')
