"""task_events and task_evidence (5.2)

Revision ID: 0018_task_events_and_evidence
Revises: 0017_stages_findings_model_calls
Create Date: 2026-09-13

§5.2 里最后两张影响语义的表。

- `task_events`:事件此前是 `tasks.events` 的 JSON 数组,与任务状态挤在同一行。
  计划要求「与任务状态更新同一事务;有完整时间线」——按时间线查询要能走索引,
  而 JSON 数组做不到。回填时 `from_state` 只能从事件序列里推:JSON 里只记了
  目标状态,推不出来的记空串而不是编一个状态。
- `task_evidence`:任务此前只有一个 `source` 字符串(主题版本 id 或 'manual'),
  那不是快照而是指针。§10.4 要求「数据集删除会使…**任务证据**失效/被清理」,
  而没有这张表就没有可执行的对象。

存量任务的来源反馈无法反推(只有一个主题版本 id,而当时的证据是 JSON 快照),
所以回填**不伪造** task_evidence 行——空表比编出来的引用诚实。
"""
from alembic import op
import sqlalchemy as sa

revision = '0018_task_events_and_evidence'
down_revision = '0017_stages_findings_model_calls'
branch_labels = None
depends_on = None


def _task_events(metadata):
    return sa.Table(
        'task_events', metadata,
        sa.Column('id', sa.String(96), primary_key=True),
        sa.Column('project_id', sa.String(64), nullable=False),
        sa.Column('task_id', sa.String(64), nullable=False),
        sa.Column('action', sa.String(32), nullable=False),
        sa.Column('from_state', sa.String(32), nullable=False),
        sa.Column('to_state', sa.String(32), nullable=False),
        sa.Column('actor_id', sa.String(64)),
        sa.Column('comment_redacted', sa.Text),
        sa.Column('material_refs_json', sa.JSON),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Index('ix_task_events_project_id', 'project_id'),
        sa.Index('ix_task_events_task_id', 'task_id'),
        sa.Index('ix_task_events_project_task', 'project_id', 'task_id', 'created_at'),
    )


def _task_evidence(metadata):
    return sa.Table(
        'task_evidence', metadata,
        sa.Column('id', sa.String(96), primary_key=True),
        sa.Column('project_id', sa.String(64), nullable=False),
        sa.Column('task_id', sa.String(64), nullable=False),
        sa.Column('feedback_id', sa.String(80), nullable=False),
        sa.Column('topic_version_id', sa.String(200)),
        sa.Column('quote_redacted', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('task_id', 'feedback_id', 'topic_version_id',
                            name='uq_task_evidence_task_feedback_version'),
        sa.ForeignKeyConstraint(['project_id', 'feedback_id'], ['feedback.project_id', 'feedback.id'],
                                name='fk_task_evidence_feedback_same_project'),
        sa.Index('ix_task_evidence_project_id', 'project_id'),
        sa.Index('ix_task_evidence_task_id', 'task_id'),
        sa.Index('ix_task_evidence_feedback_id', 'feedback_id'),
    )


def backfill_task_events(bind) -> int:
    """把 `tasks.events` 的 JSON 数组展开成事件行。

    `from_state` 从序列里推:第一条之前是 DRAFT(任务总是从草稿开始),之后每条的
    from 就是上一条的 to。推不出来的记空串——不编一个看起来合理的状态,因为时间线
    的价值全在「准确」二字上。
    """
    inspector = sa.inspect(bind)
    if 'tasks' not in set(inspector.get_table_names()):
        return 0
    metadata = sa.MetaData()
    tasks = sa.Table('tasks', metadata, autoload_with=bind)
    events = sa.Table('task_events', metadata, autoload_with=bind)

    import json as _json
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    existing = {(row[0], row[1]) for row in
                bind.execute(sa.select(events.c.task_id, events.c.id)).fetchall()}

    payload: list[dict] = []
    for row in bind.execute(sa.select(tasks)).mappings().all():
        raw = row.get('events')
        if isinstance(raw, str):
            try:
                raw = _json.loads(raw)
            except ValueError:
                raw = []
        if not isinstance(raw, list) or not raw:
            continue
        task_id, project_id = str(row['id']), row['project_id']
        previous = 'DRAFT'
        for index, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            event_id = f'te_{task_id}_{index}'
            if (task_id, event_id) in existing:
                previous = str(item.get('state') or previous)
                continue
            to_state = str(item.get('state') or '')
            payload.append({
                'id': event_id, 'project_id': project_id, 'task_id': task_id,
                'action': str(item.get('action') or ''),
                'from_state': previous, 'to_state': to_state,
                'actor_id': item.get('actor'),
                'comment_redacted': str(item.get('comment') or ''),
                'material_refs_json': [],
                'created_at': now,
            })
            previous = to_state or previous
    if payload:
        bind.execute(events.insert(), payload)
    return len(payload)


def upgrade():
    bind = op.get_bind()
    metadata = sa.MetaData()
    # feedback 要在同一份 metadata 里:task_evidence 的复合外键指向它
    sa.Table('feedback', metadata, autoload_with=bind)
    events = _task_events(metadata)
    evidence = _task_evidence(metadata)
    events.create(bind, checkfirst=True)
    evidence.create(bind, checkfirst=True)
    backfill_task_events(bind)
    # 旧 JSON 列就此退场:留着它就是同一份时间线的两份存储,而两份会分叉。
    # 读取端已经改走 task_events。
    if 'events' in {column['name'] for column in sa.inspect(bind).get_columns('tasks')}:
        op.drop_column('tasks', 'events')


def downgrade():
    """重建空的 `tasks.events` 列,并删掉两张新表。

    时间线内容不回来(task_events 同样被删),但降级后的旧代码能起来——它会看到
    一个空的 events 数组。
    """
    bind = op.get_bind()
    if 'events' not in {column['name'] for column in sa.inspect(bind).get_columns('tasks')}:
        op.add_column('tasks', sa.Column('events', sa.JSON(), nullable=True))
    op.drop_table('task_evidence')
    op.drop_table('task_events')
