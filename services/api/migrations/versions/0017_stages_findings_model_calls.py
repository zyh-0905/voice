"""analysis_stages, risk_findings, model_calls (5.2)

Revision ID: 0017_stages_findings_model_calls
Revises: 0016_topics_and_revisions
Create Date: 2026-09-13

§5.2 表清单里最后三张缺失的表。

`risk_findings` 落地时同时**取代** `risks`:那张表不在 5.2 的清单里,而且是同一
概念的另一份存储。更要紧的是它少了四列(`feedback_id` / `rule_id` /
`policy_version` / `evidence_offsets`),而 `findings_to_entities` 一直在设这几个
字段——SQL 仓储按列过滤时把它们静默丢掉,内存仓储照收。于是「这条候选命中在正文
的哪一段」在真实部署里根本没落库,两个模式还各说各话。

回填把 `risks` 的每一行搬进 `risk_findings`;`rule` 字段此前是 `{rule_id} · {policy}`
的拼接串,拆回两列,拆不出来的按原样存进 rule_id 并把 policy_version 标成 unknown
(不编一个看起来像真的版本号)。
"""
from alembic import op
import sqlalchemy as sa

revision = '0017_stages_findings_model_calls'
down_revision = '0016_topics_and_revisions'
branch_labels = None
depends_on = None


def _analysis_stages(metadata):
    return sa.Table(
        'analysis_stages', metadata,
        sa.Column('id', sa.String(160), primary_key=True),
        sa.Column('project_id', sa.String(64), nullable=False),
        sa.Column('run_id', sa.String(64), nullable=False),
        sa.Column('stage', sa.String(32), nullable=False),
        sa.Column('config_hash', sa.String(64), nullable=False),
        sa.Column('attempt', sa.Integer, nullable=False),
        sa.Column('state', sa.String(16), nullable=False),
        sa.Column('output_file_id', sa.String(96)),
        sa.Column('output_hash', sa.String(64)),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('finished_at', sa.DateTime(timezone=True)),
        sa.Column('lease_epoch', sa.Integer, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('run_id', 'stage', 'config_hash', name='uq_analysis_stages_run_stage_config'),
        sa.Index('ix_analysis_stages_project_id', 'project_id'),
        sa.Index('ix_analysis_stages_run_id', 'run_id'),
        sa.Index('ix_analysis_stages_project_run', 'project_id', 'run_id'),
    )


def _risk_findings(metadata):
    return sa.Table(
        'risk_findings', metadata,
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('project_id', sa.String(64), nullable=False),
        sa.Column('run_id', sa.String(64)),
        sa.Column('feedback_id', sa.String(80)),
        sa.Column('source_row', sa.Integer),
        sa.Column('rule_id', sa.String(128), nullable=False),
        sa.Column('policy_version', sa.String(64), nullable=False),
        sa.Column('severity', sa.String(32), nullable=False),
        sa.Column('reason', sa.Text, nullable=False),
        sa.Column('evidence_offsets', sa.JSON),
        sa.Column('review_state', sa.String(32), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('version', sa.Integer, nullable=False),
        sa.Column('reviewer_id', sa.String(64)),
        sa.Column('review_reason', sa.Text),
        sa.Column('reviewed_at', sa.String(64)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('feedback_id', 'rule_id', 'policy_version',
                            name='uq_risk_findings_feedback_rule_policy'),
        sa.ForeignKeyConstraint(['project_id', 'feedback_id'], ['feedback.project_id', 'feedback.id'],
                                name='fk_risk_findings_feedback_same_project'),
        sa.Index('ix_risk_findings_project_id', 'project_id'),
        sa.Index('ix_risk_findings_run_id', 'run_id'),
        sa.Index('ix_risk_findings_feedback_id', 'feedback_id'),
        sa.Index('ix_risk_findings_project_review_severity', 'project_id', 'review_state', 'severity'),
    )


def _model_calls(metadata):
    return sa.Table(
        'model_calls', metadata,
        sa.Column('id', sa.String(96), primary_key=True),
        sa.Column('project_id', sa.String(64), nullable=False),
        sa.Column('run_id', sa.String(64)),
        sa.Column('purpose', sa.String(64), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('provider', sa.String(64), nullable=False),
        sa.Column('model', sa.String(128)),
        sa.Column('state', sa.String(32), nullable=False),
        sa.Column('tokens_in', sa.Integer),
        sa.Column('tokens_out', sa.Integer),
        sa.Column('cost_estimated', sa.Numeric(12, 6)),
        sa.Column('cost_actual', sa.Numeric(12, 6)),
        sa.Column('provider_request_id', sa.String(128)),
        sa.Column('response_file_id', sa.String(96)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Index('ix_model_calls_project_id', 'project_id'),
        sa.Index('ix_model_calls_run_id', 'run_id'),
        sa.Index('ix_model_calls_project_created', 'project_id', 'created_at'),
    )


def _split_rule(value: str) -> tuple[str, str]:
    """`{rule_id} · {policy_version}` → (rule_id, policy_version)。

    拆不出来就保留原串当 rule_id、版本记 unknown。不编一个看起来像真的版本号:
    策略版本是回放与去重的依据,猜错了会让「换策略后应当再有候选」永远不成立。
    """
    text = str(value or '').strip()
    if ' · ' in text:
        head, tail = text.split(' · ', 1)
        if head.strip() and tail.strip():
            return head.strip(), tail.strip()
    return (text or 'unknown'), 'unknown'


def backfill_risk_findings(bind) -> tuple[int, int]:
    """把 `risks` 逐行搬进 `risk_findings`;返回 (写入, 跳过)。"""
    inspector = sa.inspect(bind)
    names = set(inspector.get_table_names())
    if 'risks' not in names:
        return 0, 0
    metadata = sa.MetaData()
    risks = sa.Table('risks', metadata, autoload_with=bind)
    findings = sa.Table('risk_findings', metadata, autoload_with=bind)

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    present = {(row[0], row[1], row[2]) for row in bind.execute(
        sa.select(findings.c.id, findings.c.rule_id, findings.c.policy_version)).fetchall()}

    payload: list[dict] = []
    skipped = 0
    for row in bind.execute(sa.select(risks)).mappings().all():
        rule_id, policy_version = _split_rule(row.get('rule'))
        # `risks` 没有 feedback_id 这一列——旧 schema 把它静默丢掉了,而 id 是四元组的
        # 哈希、不可逆,所以真实归属找不回来。留 NULL 而不是拿别的值占位:NULL 明确
        # 表示「这条候选没有可回溯的反馈行」,而复合外键在任一列为 NULL 时不校验。
        feedback_id = None
        key = (str(row['id']), rule_id, policy_version)
        if key in present:
            skipped += 1
            continue
        present.add(key)
        payload.append({
            'id': str(row['id']), 'project_id': row['project_id'], 'run_id': None,
            'feedback_id': feedback_id, 'source_row': None,
            'rule_id': rule_id, 'policy_version': policy_version,
            'severity': str(row.get('severity') or 'MEDIUM'),
            'reason': str(row.get('title') or ''),
            'evidence_offsets': None,
            'review_state': str(row.get('review_state') or 'pending'),
            'status': str(row.get('status') or 'OPEN'),
            'version': int(row.get('version') or 1),
            'reviewer_id': row.get('reviewed_by'),
            'review_reason': row.get('review_reason'),
            'reviewed_at': row.get('reviewed_at'),
            'created_at': now,
        })
    if payload:
        bind.execute(findings.insert(), payload)
    return len(payload), skipped


def _legacy_risks(metadata):
    """0016 时的 `risks` 结构,供降级时重建(仅结构,数据不回来)。"""
    return sa.Table(
        'risks', metadata,
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('project_id', sa.String(64), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('severity', sa.String(32)),
        sa.Column('status', sa.String(32)),
        sa.Column('evidence_count', sa.Integer),
        sa.Column('rule', sa.String(128)),
        sa.Column('review_state', sa.String(32)),
        sa.Column('version', sa.Integer),
        sa.Column('reviewed_by', sa.String(64)),
        sa.Column('review_reason', sa.Text),
        sa.Column('reviewed_at', sa.String(64)),
        sa.Index('ix_risks_project_id', 'project_id'),
    )


def upgrade():
    bind = op.get_bind()
    metadata = sa.MetaData()
    # feedback 也要在同一份 metadata 里:risk_findings 的复合外键指向它
    sa.Table('feedback', metadata, autoload_with=bind)
    stages = _analysis_stages(metadata)
    findings = _risk_findings(metadata)
    calls = _model_calls(metadata)
    for table in (stages, findings, calls):
        table.create(bind, checkfirst=True)
    backfill_risk_findings(bind)
    # 候选已经搬进 risk_findings,旧表就此退场——留着它就是同一概念的两份存储,
    # 而两份存储会分叉,且不会有任何东西发现(这正是本迁移要消除的东西)。
    op.drop_table('risks')


def downgrade():
    """重建空的 `risks` 结构并删掉三张新表。

    **复核队列的内容不会回来**:候选已经搬进 risk_findings(它同样被删),而
    `risks` 里那几列本来就装不下 feedback_id / rule_id / policy_version /
    evidence_offsets。降级得到的是一张空队列,旧代码能起来,但要重新扫一遍。
    """
    _legacy_risks(sa.MetaData()).create(op.get_bind(), checkfirst=True)
    for name in ('model_calls', 'risk_findings', 'analysis_stages'):
        op.drop_table(name)
