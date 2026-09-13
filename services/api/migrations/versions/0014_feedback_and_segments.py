"""feedback and segments entities (5.2)

Revision ID: 0014_feedback_and_segments
Revises: 0013_reviews_nullable_columns
Create Date: 2026-09-13

工程计划 5.2 要求 `feedback` 与 `segments` 是实体表。此前两者都不存在——反馈以
JSON 副本躺在 `datasets.governance->preview->rows` 里,再整份复制进
`analysis_runs.result`。计划对这件事有明文禁止:

    「不要为了"减少表数"把整个项目装进一个不可查询的 JSON 字段。」

代价不只是「不可查询」,而是三件事同时失去约束载体:

- 4.4 的 `(project_id, event_key)` 事件幂等:JSON 列表上无法建立唯一约束;
- 10.4 的按行删除清单:删不掉「某一条反馈」及其派生物;
- 5.1 的 `(project_id, id)` 复合外键:被引用方不存在,跨项目引用无从校验。

回填刻意复用 `app.ingestion.build_feedback_rows`,而不是在这里内联一份派生逻辑。
0011 已经吃过一次这个教训:迁移里写一份「当时的规则」副本,就会留下一个永远
不更新的影子实现,与活代码慢慢分叉而没有任何报错。event_key 尤其如此——它是
幂等、去重与按行删除的共同基础,分叉了也不会有测试发现。
"""
import json

from alembic import op
import sqlalchemy as sa

from app.config import dedupe_hmac_secret
from app.ingestion import build_feedback_rows

revision = '0014_feedback_and_segments'
down_revision = '0013_reviews_nullable_columns'
branch_labels = None
depends_on = None


def _feedback_table(metadata):
    """约束与索引都写在表定义里,而不是建表后再 ALTER。

    SQLite 不支持 `ALTER TABLE ADD CONSTRAINT`,而测试用 sqlite、生产用
    PostgreSQL——分成两步的话,「全新建库能否到 head」这条闸门只在
    PostgreSQL 上成立,而它恰恰是要证明全新部署起得来。
    """
    return sa.Table(
        'feedback', metadata,
        sa.Column('id', sa.String(80), primary_key=True),
        sa.Column('project_id', sa.String(64), nullable=False),
        sa.Column('dataset_id', sa.String(64), nullable=False),
        sa.Column('external_id', sa.String(255)),
        sa.Column('event_key', sa.String(64), nullable=False),
        sa.Column('content_redacted', sa.Text, nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True)),
        sa.Column('time_quality', sa.String(16), nullable=False),
        sa.Column('channel', sa.String(64), nullable=False),
        sa.Column('product', sa.String(64), nullable=False),
        sa.Column('rating', sa.Numeric(3, 2)),
        sa.Column('source_status', sa.String(64)),
        sa.Column('order_ref_redacted', sa.Text),
        sa.Column('source_row', sa.Integer, nullable=False),
        sa.Column('source_kind', sa.String(64)),
        sa.Column('identity_quality', sa.String(16), nullable=False),
        sa.Column('redaction_version', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('project_id', 'event_key', name='uq_feedback_project_event_key'),
        # 5.1 复合外键的被引用侧:segments 用它表达「不得跨项目引用」
        sa.UniqueConstraint('project_id', 'id', name='uq_feedback_project_id_id'),
        sa.Index('ix_feedback_project_id', 'project_id'),
        sa.Index('ix_feedback_dataset_id', 'dataset_id'),
        sa.Index('ix_feedback_project_occurred', 'project_id', 'occurred_at'),
        sa.Index('ix_feedback_project_channel', 'project_id', 'channel'),
        sa.Index('ix_feedback_project_product', 'project_id', 'product'),
    )


def _segments_table(metadata):
    return sa.Table(
        'segments', metadata,
        sa.Column('id', sa.String(96), primary_key=True),
        sa.Column('project_id', sa.String(64), nullable=False),
        sa.Column('feedback_id', sa.String(80), nullable=False),
        sa.Column('start_offset', sa.Integer, nullable=False),
        sa.Column('end_offset', sa.Integer, nullable=False),
        sa.Column('segment_index', sa.Integer, nullable=False),
        sa.Column('redaction_version', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id', 'feedback_id'], ['feedback.project_id', 'feedback.id'],
                                name='fk_segments_feedback_same_project'),
        sa.UniqueConstraint('feedback_id', 'segment_index', 'redaction_version',
                            name='uq_segments_feedback_index_version'),
        sa.Index('ix_segments_project_id', 'project_id'),
        sa.Index('ix_segments_feedback_id', 'feedback_id'),
    )


def backfill_feedback(bind) -> int:
    """把存量数据集的脱敏行写进 feedback 表,返回写入行数。

    4.4「首版反馈归属于首次有效导入的 dataset」:同一 event_key 在回填中只认第一次
    出现的那条,后面的算重复。

    必须**可重复执行**:`SQLAlchemyRepository` 启动时会 `create_all`,而它按当前
    模型建表——所以真实部署里这张表很可能先被应用建出来并写入数据,alembic 的
    版本号却还停在 0013。此时回填再插一遍同名主键就会撞唯一约束,而报错发生在
    迁移里,表现成「起不来」而不是「已存在」。
    """
    inspector = sa.inspect(bind)
    if 'datasets' not in set(inspector.get_table_names()):
        return 0
    metadata = sa.MetaData()
    datasets = sa.Table('datasets', metadata, autoload_with=bind)
    feedback = sa.Table('feedback', metadata, autoload_with=bind)

    secret, _demo = dedupe_hmac_secret()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    # 已经在库里的行不再插入(见上面 docstring 里的 create_all 场景)。
    # 主键与 (project_id, event_key) 两条唯一约束都要避开,只挡一条仍会撞另一条。
    present_ids = {row[0] for row in bind.execute(sa.select(feedback.c.id)).fetchall()}
    seen: set[tuple[str, str]] = {
        (row[0], row[1]) for row in
        bind.execute(sa.select(feedback.c.project_id, feedback.c.event_key)).fetchall()
    }
    payload: list[dict] = []
    for row in bind.execute(sa.select(datasets)).mappings().all():
        governance = row['governance']
        if isinstance(governance, str):
            try:
                governance = json.loads(governance)
            except ValueError:
                continue
        dataset = dict(governance or {})
        dataset.setdefault('id', row['id'])
        dataset.setdefault('project_id', row['project_id'])
        project_id = row['project_id']
        for built in build_feedback_rows(dataset, secret=secret):
            key = (project_id, built['event_key'])
            if key in seen or built['id'] in present_ids:
                continue
            seen.add(key)
            payload.append({
                'project_id': project_id, 'dataset_id': row['id'],
                'occurred_at': built['occurred_at'], 'created_at': now,
                **{name: built[name] for name in (
                    'id', 'external_id', 'event_key', 'content_redacted', 'content_hash',
                    'time_quality', 'channel', 'product', 'rating', 'source_status',
                    'order_ref_redacted', 'source_row', 'source_kind', 'identity_quality',
                    'redaction_version')},
            })
    if payload:
        bind.execute(feedback.insert(), payload)
    return len(payload)


def upgrade():
    bind = op.get_bind()
    metadata = sa.MetaData()
    feedback = _feedback_table(metadata)
    segments = _segments_table(metadata)

    feedback.create(bind, checkfirst=True)
    segments.create(bind, checkfirst=True)
    backfill_feedback(bind)


def downgrade():
    """删表即丢派生数据。

    feedback 的正文与 datasets.governance 中的行同源,重跑 upgrade 可以重建——
    但重建出来的 event_key 依赖当时的 DEDUPE_HMAC_SECRET,换过密钥就回不到
    同一个键。分块同理,可以重算。真要有保留价值的部署,先做备份而不是降级。
    """
    # 索引与约束都是随表内联创建的,删表即删干净;单独 drop_index 反而会在
    # PostgreSQL 上撞到唯一约束的隐式索引。
    op.drop_table('segments')
    op.drop_table('feedback')
