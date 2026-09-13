"""topics, topic_versions, topic_evidence, analysis_revisions, topic_corrections (5.2)

Revision ID: 0016_topics_and_revisions
Revises: 0015_run_feedbacks
Create Date: 2026-09-13

主题与证据此前整体装在一次发布的 `analysis_runs.result` JSON 里,人工校正再把
旧快照整份复制进 `revision_history`。计划对这种做法有明文禁止:

    「不要为了"减少表数"把整个项目装进一个不可查询的 JSON 字段。」

失去的是三条计划明写的语义:

- `(topic_id, version)` 唯一与「不可原地更新」(5.2):JSON 数组里没有版本行,
  改名就是就地改一个 dict,旧版本靠整份快照副本保存;
- `(run_id, revision)` 唯一与「旧 revision 永远可读」(5.3):副本与「当前」副本
  会分叉,而且不会有任何东西发现;
- `(topic_version_id, feedback_id, segment_id)` 唯一(5.2):证据是 JSON 列表,
  重复关联只在写入时靠 Python 的 set 保证,落库后无人复核。

回填刻意复用 `app.revisions.plan_revision`,与在线发布走同一个展开函数。各写一份
的话,存量行与新行的 topic_version 编号口径会分叉——而「旧版本可复现」正建立在
这些编号上,分叉了也不会有测试发现。

历史 revision 一并回填(`revision_history` 里的快照)。只存在于历史里的主题标
`state='INACTIVE'`:它已经不是当前版本,但删掉就等于销毁了「旧 revision 永远可读」。
"""
import json

from alembic import op
import sqlalchemy as sa

from app.revisions import plan_revision

revision = '0016_topics_and_revisions'
down_revision = '0015_run_feedbacks'
branch_labels = None
depends_on = None


def _tables(metadata):
    """五张表定义在同一份 metadata 里:topic_versions 的复合外键要能解析出 topics,
    topic_evidence 的要能解析出 feedback。分开定义会在 SQLite 上直接报
    NoReferencedTableError——而「全新建库能否到 head」这条闸门跑的就是 sqlite。"""
    topics = sa.Table(
        'topics', metadata,
        sa.Column('id', sa.String(160), primary_key=True),
        sa.Column('topic_id', sa.String(80), nullable=False),
        sa.Column('project_id', sa.String(64), nullable=False),
        sa.Column('run_id', sa.String(64), nullable=False),
        sa.Column('current_version_id', sa.String(200)),
        sa.Column('state', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('project_id', 'id', name='uq_topics_project_id_id'),
        sa.UniqueConstraint('run_id', 'topic_id', name='uq_topics_run_topic'),
        sa.Index('ix_topics_project_id', 'project_id'),
        sa.Index('ix_topics_run_id', 'run_id'),
        sa.Index('ix_topics_project_run', 'project_id', 'run_id'),
    )
    topic_versions = sa.Table(
        'topic_versions', metadata,
        sa.Column('id', sa.String(200), primary_key=True),
        sa.Column('project_id', sa.String(64), nullable=False),
        sa.Column('run_id', sa.String(64), nullable=False),
        sa.Column('topic_id', sa.String(80), nullable=False),
        sa.Column('topic_row_id', sa.String(160), nullable=False),
        sa.Column('version', sa.Integer, nullable=False),
        sa.Column('revision', sa.Integer, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('summary', sa.Text, nullable=False),
        sa.Column('severity', sa.String(32), nullable=False),
        sa.Column('department', sa.String(64)),
        sa.Column('claims_json', sa.JSON),
        sa.Column('suggested_action', sa.Text),
        sa.Column('needs_review', sa.Boolean, nullable=False),
        sa.Column('summary_revalidated', sa.Boolean, nullable=False),
        sa.Column('limitations_json', sa.JSON),
        sa.Column('origin', sa.String(32)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('topic_row_id', 'version', name='uq_topic_versions_topic_version'),
        sa.ForeignKeyConstraint(['project_id', 'topic_row_id'], ['topics.project_id', 'topics.id'],
                                name='fk_topic_versions_topic_same_project'),
        sa.Index('ix_topic_versions_project_id', 'project_id'),
        sa.Index('ix_topic_versions_topic_id', 'topic_id'),
    )
    topic_evidence = sa.Table(
        'topic_evidence', metadata,
        sa.Column('id', sa.String(96), primary_key=True),
        sa.Column('project_id', sa.String(64), nullable=False),
        sa.Column('topic_version_id', sa.String(200), nullable=False),
        sa.Column('feedback_id', sa.String(80), nullable=False),
        sa.Column('segment_id', sa.String(96), nullable=False),
        sa.Column('source_row', sa.Integer, nullable=False),
        sa.Column('quote', sa.Text, nullable=False),
        sa.Column('quote_start', sa.Integer, nullable=False),
        sa.Column('quote_end', sa.Integer, nullable=False),
        sa.Column('similarity', sa.Numeric(6, 5)),
        sa.Column('is_representative', sa.Boolean, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('topic_version_id', 'feedback_id', 'segment_id',
                            name='uq_topic_evidence_version_feedback_segment'),
        sa.ForeignKeyConstraint(['project_id', 'feedback_id'], ['feedback.project_id', 'feedback.id'],
                                name='fk_topic_evidence_feedback_same_project'),
        sa.Index('ix_topic_evidence_project_id', 'project_id'),
        sa.Index('ix_topic_evidence_topic_version_id', 'topic_version_id'),
        sa.Index('ix_topic_evidence_feedback_id', 'feedback_id'),
    )
    analysis_revisions = sa.Table(
        'analysis_revisions', metadata,
        sa.Column('id', sa.String(96), primary_key=True),
        sa.Column('project_id', sa.String(64), nullable=False),
        sa.Column('run_id', sa.String(64), nullable=False),
        sa.Column('revision', sa.Integer, nullable=False),
        sa.Column('topic_manifest_json', sa.JSON),
        sa.Column('unassigned_count', sa.Integer, nullable=False),
        sa.Column('reason', sa.Text),
        sa.Column('actor_id', sa.String(64)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('run_id', 'revision', name='uq_analysis_revisions_run_revision'),
        sa.Index('ix_analysis_revisions_project_id', 'project_id'),
        sa.Index('ix_analysis_revisions_run_id', 'run_id'),
        sa.Index('ix_analysis_revisions_project_run', 'project_id', 'run_id'),
    )
    topic_corrections = sa.Table(
        'topic_corrections', metadata,
        sa.Column('id', sa.String(96), primary_key=True),
        sa.Column('project_id', sa.String(64), nullable=False),
        sa.Column('run_id', sa.String(64), nullable=False),
        sa.Column('from_revision', sa.Integer, nullable=False),
        sa.Column('to_revision', sa.Integer, nullable=False),
        sa.Column('operation', sa.String(32), nullable=False),
        sa.Column('source_topic_ids', sa.JSON),
        sa.Column('target_topic_ids', sa.JSON),
        sa.Column('reason', sa.Text, nullable=False),
        sa.Column('actor_id', sa.String(64)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Index('ix_topic_corrections_project_id', 'project_id'),
        sa.Index('ix_topic_corrections_run_id', 'run_id'),
    )
    return topics, topic_versions, topic_evidence, analysis_revisions, topic_corrections


def _insert(bind, table, rows, now):
    if not rows:
        return
    bind.execute(table.insert(), [{**row, 'created_at': now} for row in rows])


def backfill_revisions(bind) -> tuple[int, int, int]:
    """把存量 run 的主题与证据展开成实体行;返回 (revision 数, topic_version 数, 证据数)。"""
    inspector = sa.inspect(bind)
    names = set(inspector.get_table_names())
    if 'analysis_runs' not in names or 'topics' not in names:
        return 0, 0, 0
    metadata = sa.MetaData()
    runs = sa.Table('analysis_runs', metadata, autoload_with=bind)
    topics, versions, evidence, revisions, _corrections = (
        sa.Table(name, metadata, autoload_with=bind)
        for name in ('topics', 'topic_versions', 'topic_evidence',
                     'analysis_revisions', 'topic_corrections'))

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    # 可重复执行:应用启动时的 create_all 可能已经建好表并写入,而版本号还停在上一版
    existing_revisions = {(row[0], row[1]) for row in
                          bind.execute(sa.select(revisions.c.run_id, revisions.c.revision)).fetchall()}
    existing_topic_ids = {(row[0], row[1]) for row in
                          bind.execute(sa.select(topics.c.project_id, topics.c.id)).fetchall()}
    existing_version_ids = {row[0] for row in
                            bind.execute(sa.select(versions.c.id)).fetchall()}
    # 复核可引用的反馈:topic_evidence 的复合外键指向 feedback(project_id, id)
    feedback = sa.Table('feedback', metadata, autoload_with=bind)
    live_feedback = {(row[0], row[1]) for row in
                     bind.execute(sa.select(feedback.c.project_id, feedback.c.id)).fetchall()}

    counts = [0, 0, 0]
    for row in bind.execute(sa.select(runs)).mappings().all():
        stored = row['result']
        if isinstance(stored, str):
            try:
                stored = json.loads(stored)
            except ValueError:
                continue
        stored = stored or {}
        current = stored.get('result') or {}
        history = stored.get('revision_history') or {}
        run_id, project_id = row['id'], row['project_id']

        # 按 revision 升序处理:版本号是「第几次出现」,顺序错了编号就错,
        # 而「旧 revision 永远可读」正建立在这些编号上
        snapshots = sorted(
            [snap for snap in [*history.values(), current] if snap],
            key=lambda snap: int(snap.get('revision') or 0),
        )
        snapshots = [snap for snap in snapshots if int(snap.get('revision') or 0)]

        # plan_revision 对**每个** snapshot 都算一次(即使该 revision 已存在),
        # 否则跳过中间的 revision 会让后续的版本号从头开始,与已写入的行撞键
        next_versions: dict[str, int] = {}
        for snapshot in snapshots:
            plan = plan_revision(project_id, run_id, snapshot, next_versions=next_versions)
            for version in plan['versions']:
                next_versions[version['topic_id']] = version['version'] + 1

            rev = plan['revision']['revision']
            if (run_id, rev) in existing_revisions:
                continue

            fresh_topics = [t for t in plan['topics']
                            if (project_id, t['id']) not in existing_topic_ids]
            existing_topic_ids.update((project_id, t['id']) for t in fresh_topics)
            fresh_versions = [v for v in plan['versions'] if v['id'] not in existing_version_ids]
            existing_version_ids.update(v['id'] for v in fresh_versions)
            keep = {v['id'] for v in fresh_versions}
            # 悬空证据只跳过,不让整次升级失败。存量 run 里确实存在这种行:发布时
            # 引用的反馈此后被重新治理/清理掉了(demo 库上就有一条 published run
            # 的证据指向已不存在的 feedback)。它们本来就渲染不出来,而复合外键
            # 的意义正是拒绝这种引用——所以跳过并**报出数量**,而不是静默或中断。
            fresh_evidence = [e for e in plan['evidence']
                              if e['topic_version_id'] in keep
                              and (project_id, e['feedback_id']) in live_feedback]
            dropped = sum(1 for e in plan['evidence']
                          if e['topic_version_id'] in keep
                          and (project_id, e['feedback_id']) not in live_feedback)
            if dropped:
                print(f'0016: run {run_id} rev {rev}: 跳过 {dropped} 条悬空证据引用')

            _insert(bind, topics, fresh_topics, now)
            _insert(bind, versions, fresh_versions, now)
            _insert(bind, evidence, fresh_evidence, now)
            _insert(bind, revisions, [plan['revision']], now)
            existing_revisions.add((run_id, rev))
            counts[0] += 1
            counts[1] += len(fresh_versions)
            counts[2] += len(fresh_evidence)

        # 只在历史里出现过的主题标 INACTIVE:它不再是当前版本,但删掉就等于
        # 销毁了「旧 revision 永远可读」
        live_topic_ids = [str(t['topic_id']) for t in (current.get('topics') or [])]
        bind.execute(topics.update()
                     .where(topics.c.run_id == run_id, topics.c.state == 'ACTIVE')
                     .where(topics.c.topic_id.notin_(live_topic_ids or ['']))
                     .values(state='INACTIVE'))

    return counts[0], counts[1], counts[2]


def upgrade():
    bind = op.get_bind()
    metadata = sa.MetaData()
    # feedback 也要在同一份 metadata 里:topic_evidence 的复合外键指向它
    sa.Table('feedback', metadata, autoload_with=bind)
    created = _tables(metadata)
    for table in created:
        table.create(bind, checkfirst=True)
    backfill_revisions(bind)


def downgrade():
    """删表即丢主题版本史。主题与证据可以从 feedback 重新分析生成,但**人工校正
    的结果不会回来**——那是人的输入,不是算法产物。真要保留就先备份。"""
    for name in ('topic_corrections', 'analysis_revisions', 'topic_evidence',
                 'topic_versions', 'topics'):
        op.drop_table(name)
