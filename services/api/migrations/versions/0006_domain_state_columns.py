"""domain state machine columns

Revision ID: 0006_domain_state_columns
Revises: 0005_session_tokens
Create Date: 2026-09-10

Task/Risk/Review 补全 W14/W15/W17 所需列,使 SQL 模式与 InMemory 行为一致。
"""
from alembic import op
import sqlalchemy as sa

revision = '0006_domain_state_columns'
down_revision = '0005_session_tokens'
branch_labels = None
depends_on = None

TASK_COLUMNS = [
    ('state', sa.String(32), 'DRAFT'),
    ('version', sa.Integer(), 1),
    ('owner_id', sa.String(64), None),
    ('due_at', sa.String(64), None),
    ('acceptance', sa.Text(), None),
    ('source', sa.String(255), None),
    ('effect_status', sa.String(32), 'NOT_EVALUATED'),
    ('events', sa.JSON(), None),
    ('idempotency_keys', sa.JSON(), None),
]

RISK_COLUMNS = [
    ('rule', sa.String(128), None),
    ('review_state', sa.String(32), 'pending'),
]

REVIEW_COLUMNS = [
    ('revision', sa.Integer(), None),
    ('topic_version_ids', sa.JSON(), None),
    ('task_id', sa.String(64), None),
    ('before', sa.JSON(), None),
    ('after', sa.JSON(), None),
    ('metrics', sa.JSON(), None),
    ('effect_status', sa.String(32), None),
    ('limitations', sa.JSON(), None),
]


def _add(table: str, columns: list) -> None:
    for name, type_, default in columns:
        op.add_column(table, sa.Column(name, type_, nullable=True, server_default=None if default is None else str(default)))


def _drop(table: str, columns: list) -> None:
    for name, _type, _default in reversed(columns):
        op.drop_column(table, name)


def upgrade():
    _add('tasks', TASK_COLUMNS)
    _add('risks', RISK_COLUMNS)
    _add('reviews', REVIEW_COLUMNS)
    # 回填既有行:state 由 status 推导,并补齐状态机默认字段;
    # 新建库此时无数据,回填是空操作。
    op.execute("""
        UPDATE tasks
           SET state = CASE UPPER(COALESCE(status, 'DRAFT'))
                         WHEN 'DRAFT' THEN 'DRAFT'
                         WHEN 'OPEN' THEN 'OPEN'
                         WHEN 'IN_PROGRESS' THEN 'IN_PROGRESS'
                         WHEN 'PENDING_REVIEW' THEN 'PENDING_REVIEW'
                         WHEN 'CLOSED' THEN 'CLOSED'
                         WHEN 'CANCELLED' THEN 'CANCELLED'
                         ELSE 'DRAFT'
                       END,
               version = COALESCE(version, 1),
               effect_status = COALESCE(effect_status, 'NOT_EVALUATED'),
               events = COALESCE(events, '[]'),
               idempotency_keys = COALESCE(idempotency_keys, '[]')
    """)
    op.execute("UPDATE risks SET review_state = COALESCE(review_state, 'pending')")


def downgrade():
    _drop('reviews', REVIEW_COLUMNS)
    _drop('risks', RISK_COLUMNS)
    _drop('tasks', TASK_COLUMNS)
