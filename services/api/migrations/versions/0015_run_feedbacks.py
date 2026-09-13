"""run_feedbacks: freeze a run's input (5.2)

Revision ID: 0015_run_feedbacks
Revises: 0014_feedback_and_segments
Create Date: 2026-09-13

工程计划 5.2 把「冻结分析输入」列为一张表,5.3 给它的语义是「创建 run 时冻结
`run_feedbacks`…之后新增反馈不影响这个 run」。

0014 先把这份清单冻结在 `analysis_runs.result->run_feedback_ids` 里——那只是把
一条关系放进 JSON:它不参与任何约束,删掉一条 feedback 之后没有任何东西会阻止
清单继续指向一个不存在的 id,而「这个 run 到底覆盖了哪些反馈」也因此不可查询
(5.2 明文禁止的那种做法)。

回填:把存量 run 的 `run_feedback_ids` 读出来建行。只补那些 id 在 feedback 表里
确实存在的条目——0014 之前创建的 run 本来就没有冻结过输入,它们指向的 id 现在
也可能已经被删掉,而复合外键不会接受悬空引用(这一点正是这张表的意义)。
"""
import json

from alembic import op
import sqlalchemy as sa

revision = '0015_run_feedbacks'
down_revision = '0014_feedback_and_segments'
branch_labels = None
depends_on = None


def _run_feedbacks_table(metadata):
    """约束写在表定义里:SQLite 不支持 ALTER TABLE ADD CONSTRAINT,而「全新建库
    能否到 head」这条闸门跑的就是 sqlite。

    `metadata` 必须已经含 `feedback` 表:复合外键的目标是 `feedback.project_id /
    feedback.id`,SQLAlchemy 建约束时要能在同一份 metadata 里解析出这张表,
    否则报 `NoReferencedTableError`——只在 PostgreSQL 上能侥幸通过的那种写法,
    正是 sqlite 闸门要拦的。
    """
    return sa.Table(
        'run_feedbacks', metadata,
        sa.Column('id', sa.String(96), primary_key=True),
        sa.Column('project_id', sa.String(64), nullable=False),
        sa.Column('run_id', sa.String(64), nullable=False),
        sa.Column('feedback_id', sa.String(80), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('run_id', 'feedback_id', name='uq_run_feedbacks_run_feedback'),
        sa.ForeignKeyConstraint(['project_id', 'feedback_id'], ['feedback.project_id', 'feedback.id'],
                                name='fk_run_feedbacks_feedback_same_project'),
        sa.Index('ix_run_feedbacks_project_id', 'project_id'),
        sa.Index('ix_run_feedbacks_run_id', 'run_id'),
        sa.Index('ix_run_feedbacks_feedback_id', 'feedback_id'),
    )


def backfill_run_feedbacks(bind) -> tuple[int, int]:
    """从存量 run 的 JSON 冻结清单回填;返回 (写入行数, 跳过的悬空引用数)。"""
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if 'analysis_runs' not in tables or 'feedback' not in tables:
        return 0, 0
    metadata = sa.MetaData()
    runs = sa.Table('analysis_runs', metadata, autoload_with=bind)
    feedback = sa.Table('feedback', metadata, autoload_with=bind)
    run_feedbacks = sa.Table('run_feedbacks', metadata, autoload_with=bind)

    live = {(row[0], row[1]) for row in
            bind.execute(sa.select(feedback.c.project_id, feedback.c.id)).fetchall()}
    # 已经存在的清单条目不再插入:应用启动时的 create_all 可能已经把表建好并写入,
    # 而 alembic 版本号还停在上一版(与 0014 同一个场景)。迁移必须可重复执行。
    already = {(row[0], row[1]) for row in
               bind.execute(sa.select(run_feedbacks.c.run_id, run_feedbacks.c.feedback_id)).fetchall()}
    present_ids = {row[0] for row in bind.execute(sa.select(run_feedbacks.c.id)).fetchall()}

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    payload: list[dict] = []
    skipped = 0
    for row in bind.execute(sa.select(runs)).mappings().all():
        result = row['result']
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except ValueError:
                continue
        frozen = (result or {}).get('run_feedback_ids')
        if not frozen:
            continue
        project_id, run_id = row['project_id'], row['id']
        for index, feedback_id in enumerate(frozen):
            if (project_id, feedback_id) not in live:
                skipped += 1
                continue
            row_id = f'rf_{run_id}_{index}'
            if (run_id, feedback_id) in already or row_id in present_ids:
                continue
            payload.append({'id': row_id, 'project_id': project_id,
                            'run_id': run_id, 'feedback_id': feedback_id, 'created_at': now})
    if payload:
        bind.execute(run_feedbacks.insert(), payload)
    return len(payload), skipped


def upgrade():
    bind = op.get_bind()
    metadata = sa.MetaData()
    # 反射 feedback 而不是重抄一遍列定义:抄一份就多一处会与 0014 漂移的副本,
    # 而漂移的表现是外键指向一个不存在的列。
    sa.Table('feedback', metadata, autoload_with=bind)
    _run_feedbacks_table(metadata).create(bind, checkfirst=True)
    backfill_run_feedbacks(bind)


def downgrade():
    """删表即回到「清单存在 run JSON 里」的旧状态;服务端读取端仍保留 JSON 回退,
    所以降级不会让已有 run 变成空输入。"""
    op.drop_table('run_feedbacks')
