from datetime import datetime
from sqlalchemy import (Boolean, DateTime, ForeignKeyConstraint, Index, Integer,
                        JSON, Numeric, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    source_namespace: Mapped[str | None] = mapped_column(String(128), index=True)
    source_kind: Mapped[str | None] = mapped_column(String(64), index=True)
    # W03 项目设置:timezone 单列,limits/rules/model_available/version 存 settings_json
    timezone: Mapped[str | None] = mapped_column(String(64))
    settings_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class Membership(Base):
    """W03 项目成员:(project_id, user_id) 唯一,角色 OWNER/EDITOR/VIEWER。"""
    __tablename__ = "memberships"
    project_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))

class Dataset(Base):
    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # HMAC of the source identity; nullable for rows created before dedupe migration.
    event_key: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="uploaded", nullable=False)
    governance: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    result: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(128))
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_key: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class IdempotencyKey(Base):
    """W06:分析创建幂等键持久化(key → fingerprint + analysis_id)。"""
    __tablename__ = "idempotency_keys"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    analysis_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class SessionToken(Base):
    """阶段三:服务端会话持久化(SESSION_STORE=db)。"""
    __tablename__ = "session_tokens"
    token: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    projects: Mapped[list] = mapped_column(JSON, nullable=False)
    issued_at: Mapped[float] = mapped_column(nullable=False)
    exp: Mapped[float] = mapped_column(nullable=False)
    # 空闲过期时间:每次访问滑动续期
    idle_exp: Mapped[float | None] = mapped_column(nullable=True)

class ExportJob(Base):
    """10.3 导出:24 小时失效、下载重新鉴权;删除项目后未过期导出一并失效。

    演示实现把内容存在行内;生产应落对象存储并以短期签名路径下发。
    """
    __tablename__ = 'export_jobs'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), default='DONE', nullable=False)
    columns: Mapped[list | None] = mapped_column(JSON)
    row_count: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[str | None] = mapped_column(String(64))
    invalidated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class DeletionJob(Base):
    """10.4 删除登记:写 tombstone 后级联清理,回执不含正文。"""
    __tablename__ = 'deletion_jobs'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_name: Mapped[str | None] = mapped_column(String(255))
    state: Mapped[str] = mapped_column(String(32), default='RUNNING', nullable=False)
    actor: Mapped[str | None] = mapped_column(String(64))
    steps: Mapped[list | None] = mapped_column(JSON, default=list)
    receipt: Mapped[dict | None] = mapped_column(JSON)


class RiskAudit(Base):
    """W14 审计:风险裁决等动作的脱敏元数据(不含正文)。"""
    __tablename__ = 'risk_audits'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[str | None] = mapped_column(String(64))

class Task(Base):
    __tablename__ = 'tasks'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    owner: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default='todo', nullable=False)
    priority: Mapped[str] = mapped_column(String(32), default='medium', nullable=False)
    # W15 状态机:state 为规范枚举,version 用于乐观锁,events 记录真实流转
    state: Mapped[str] = mapped_column(String(32), default='DRAFT', nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    owner_id: Mapped[str | None] = mapped_column(String(64))
    due_at: Mapped[str | None] = mapped_column(String(64))
    acceptance: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(255))
    effect_status: Mapped[str] = mapped_column(String(32), default='NOT_EVALUATED', nullable=False)
    events: Mapped[list | None] = mapped_column(JSON, default=list)
    idempotency_keys: Mapped[list | None] = mapped_column(JSON, default=list)

class Review(Base):
    __tablename__ = 'reviews'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default='pending', nullable=False)
    # 旧「效果复查」设计遗留:计划 5.2 的 reviews 表没有这一列,复盘也不再写它。
    # 保持可空,否则真实模式下插入复盘会 NotNullViolation(内存仓储看不见这个问题)。
    finding: Mapped[str | None] = mapped_column(Text)
    confirmed_by: Mapped[str | None] = mapped_column(String(128))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    # W17 复盘:固定口径结果不可变保存
    revision: Mapped[int | None] = mapped_column(Integer)
    topic_version_ids: Mapped[list | None] = mapped_column(JSON, default=list)
    task_id: Mapped[str | None] = mapped_column(String(64))
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict | None] = mapped_column(JSON)
    metrics: Mapped[dict | None] = mapped_column(JSON)
    effect_status: Mapped[str | None] = mapped_column(String(32))
    limitations: Mapped[list | None] = mapped_column(JSON, default=list)


class Feedback(Base):
    """工程计划 5.2 反馈实体:一行一条反馈,持久正文只保留脱敏结果。

    这张表此前不存在——反馈以 JSON 副本躺在 `datasets.governance->preview->rows`
    里,再整份复制进 `analysis_runs.result`。那不只是一次冗余:它让 4.4 的
    `(project_id, event_key)` 事件幂等、10.4 的按行删除清单、5.1 的
    `(project_id, id)` 复合外键三件事都没有可落地的约束载体,而计划明文禁止
    「把整个项目装进一个不可查询的 JSON 字段」。

    `id` 沿用既有派生规则 `fb_{dataset_id}_{序号}`,序号是**按 source_row 升序**
    的枚举位置而不是 source_row 本身:治理阶段会剔除无效行,两者不再相等,
    但下游(证据链接、导出、证据源查询)一直以枚举位置为准。
    """

    __tablename__ = 'feedback'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    dataset_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    # 来源系统的原始编号;id 是平台生成的,两者不能混用(4.2)
    external_id: Mapped[str | None] = mapped_column(String(255))
    event_key: Mapped[str] = mapped_column(String(64), nullable=False)
    content_redacted: Mapped[str] = mapped_column(Text, nullable=False)
    # 只用于相似文本候选,不用于幂等——幂等一律走 event_key(4.2)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_quality: Mapped[str] = mapped_column(String(16), nullable=False, default='missing')
    channel: Mapped[str] = mapped_column(String(64), nullable=False, default='unknown')
    product: Mapped[str] = mapped_column(String(64), nullable=False, default='unknown')
    rating: Mapped[float | None] = mapped_column(Numeric(3, 2))
    source_status: Mapped[str | None] = mapped_column(String(64))
    # 完整订单号不落库(4.2);这里存的已经是脱敏结果
    order_ref_redacted: Mapped[str | None] = mapped_column(Text)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    source_kind: Mapped[str | None] = mapped_column(String(64))
    # source_id(有来源编号)/ source_row(无来源编号,按文件+行号认身份)
    identity_quality: Mapped[str] = mapped_column(String(16), nullable=False, default='source_row')
    redaction_version: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    __table_args__ = (
        # 4.4 事件幂等:同项目同 event_key 只能有一条反馈
        UniqueConstraint('project_id', 'event_key', name='uq_feedback_project_event_key'),
        # 5.1 复合外键的被引用侧:让 segments 能表达「不得跨项目引用」
        UniqueConstraint('project_id', 'id', name='uq_feedback_project_id_id'),
        Index('ix_feedback_project_occurred', 'project_id', 'occurred_at'),
        Index('ix_feedback_project_channel', 'project_id', 'channel'),
        Index('ix_feedback_project_product', 'project_id', 'product'),
    )


class AnalysisStage(Base):
    """工程计划 5.2 分析阶段:`(run_id, stage, config_hash)` 业务唯一,attempt 为重试计数。

    一张表回答「这次分析跑到哪一步、重试了几次、那一步的产物哈希是什么」——
    此前这些只体现为 run 上的一个 `stage` 字符串,重试与产物哈希无从追溯
    (6.2 的恢复策略要靠它判断某一步是否已经成功过)。
    """

    __tablename__ = 'analysis_stages'
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False, default='')
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default='PENDING')
    output_file_id: Mapped[str | None] = mapped_column(String(96))
    output_hash: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    __table_args__ = (
        UniqueConstraint('run_id', 'stage', 'config_hash', name='uq_analysis_stages_run_stage_config'),
        Index('ix_analysis_stages_project_run', 'project_id', 'run_id'),
    )


class RiskFinding(Base):
    """工程计划 5.2 风险候选:`(feedback_id, rule_id, policy_version)` 唯一。

    这就是复核队列本身——此前它叫 `risks`,而那不在 5.2 的表清单里,且**少了
    feedback_id / rule_id / policy_version / evidence_offsets 四列**。
    `findings_to_entities` 一直在设这几个字段,SQL 仓储按列过滤时把它们静默丢掉
    (内存仓储照收),于是「命中位置」在真实部署里根本没落库,两个模式还各说各话。
    """

    __tablename__ = 'risk_findings'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    # 产生这条候选的 run;策略变更后同一对允许再有一条,所以它不是唯一键的一部分
    run_id: Mapped[str | None] = mapped_column(String(64), index=True)
    # 可空 + 复合外键:真实候选一定填 feedback_id 并因此受外键约束;存量行与演示
    # 种子填不出来(旧表把这一列静默丢掉了,而 id 是四元组的哈希、不可逆),
    # NULL 表示「这条候选没有可回溯的反馈行」——不编一个 id 去占位。
    feedback_id: Mapped[str | None] = mapped_column(String(80), index=True)
    source_row: Mapped[int | None] = mapped_column(Integer)
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default='MEDIUM')
    reason: Mapped[str] = mapped_column(Text, nullable=False, default='')
    evidence_offsets: Mapped[dict | None] = mapped_column(JSON)
    review_state: Mapped[str] = mapped_column(String(32), nullable=False, default='pending')
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='OPEN')
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reviewer_id: Mapped[str | None] = mapped_column(String(64))
    review_reason: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    __table_args__ = (
        UniqueConstraint('feedback_id', 'rule_id', 'policy_version',
                         name='uq_risk_findings_feedback_rule_policy'),
        ForeignKeyConstraint(['project_id', 'feedback_id'], ['feedback.project_id', 'feedback.id'],
                             name='fk_risk_findings_feedback_same_project'),
        Index('ix_risk_findings_project_review_severity', 'project_id', 'review_state', 'severity'),
    )


class ModelCall(Base):
    """工程计划 5.2 模型调用:预算、成本与 UNKNOWN 调用的唯一凭据(10.5)。

    此前这个表不存在,`model_calls` 全仓库零引用——于是「每日预算」「调用前预留、
    收到 usage 后结算」「没有可靠价格配置时禁用付费模式」全都没有落脚点。

    费用用定点数(5.1:金额不用 float)。没有可靠价格时留 NULL 而不是填 0:
    0 会让「免费」和「不知道多少钱」看起来一样,而预算判断依赖这个区别。
    """

    __tablename__ = 'model_calls'
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(64), index=True)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False, default='naming')
    # 请求指纹:不记录完整敏感请求,但同一个请求重放要能认出来
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False, default='')
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(32), nullable=False, default='SUCCESS')
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    cost_estimated: Mapped[float | None] = mapped_column(Numeric(12, 6))
    cost_actual: Mapped[float | None] = mapped_column(Numeric(12, 6))
    provider_request_id: Mapped[str | None] = mapped_column(String(128))
    response_file_id: Mapped[str | None] = mapped_column(String(96))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    __table_args__ = (
        Index('ix_model_calls_project_created', 'project_id', 'created_at'),
    )


class Topic(Base):
    """工程计划 5.2 主题:topic_id 在同一次分析内稳定,跨 run 不自动认为是同一语义。

    `current_version_id` 是活动版本指针(人工校正后原子推进)。它刻意不设外键:
    topics 与 topic_versions 互相引用,两张表谁先建都会撞上「引用的表还不存在」,
    而 SQLite 不支持建表后 ALTER ADD CONSTRAINT——那意味着闸门跑不过 sqlite,
    只能退回「只在 PostgreSQL 上能建」。真正要紧的方向(topic_versions 不得
    指向别的项目的主题)由 topic_versions 那侧的复合外键保证。
    """

    __tablename__ = 'topics'
    # 行 id 带 run_id:`topic_id` 只在一次分析内稳定(5.2),而每个 run 都会把簇命名为
    # topic-1、topic-2……。裸用 topic_id 做键会让同项目的第二个 run 撞主键,
    # 它的主题被静默丢弃。
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    # 业务 id(同一 run 内稳定),manifest 与 API 都用它
    topic_id: Mapped[str] = mapped_column(String(80), nullable=False)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    current_version_id: Mapped[str | None] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(16), nullable=False, default='ACTIVE')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    __table_args__ = (
        # topic_versions 的复合外键指向这里
        UniqueConstraint('project_id', 'id', name='uq_topics_project_id_id'),
        UniqueConstraint('run_id', 'topic_id', name='uq_topics_run_topic'),
        Index('ix_topics_project_run', 'project_id', 'run_id'),
    )


class TopicVersion(Base):
    """工程计划 5.2 主题版本:`(topic_id, version)` 唯一,**不可原地更新**。

    改名/合并/拆分的产物是新行,不是对被改行的 update。这一条此前只能靠「把旧快照
    复制进 revision_history 数组」近似实现——而那份副本与「当前」副本可以分叉,
    且没有任何东西会发现。
    """

    __tablename__ = 'topic_versions'
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    # 业务 id(manifest 与 API 用)与行 id 分开:行 id 必须全局唯一,业务 id 只在一个 run 内稳定
    topic_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    topic_row_id: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # 引入这个版本的分析 revision:人工校正每次推进 revision,topic_version 随之增加
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default='')
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default='medium')
    department: Mapped[str | None] = mapped_column(String(64))
    claims_json: Mapped[list | None] = mapped_column(JSON, default=list)
    suggested_action: Mapped[str | None] = mapped_column(Text)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 校正后摘要未重新验证前为 false:不能原样保留不适用的断言
    summary_revalidated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    limitations_json: Mapped[list | None] = mapped_column(JSON, default=list)
    origin: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    __table_args__ = (
        UniqueConstraint('topic_row_id', 'version', name='uq_topic_versions_topic_version'),
        ForeignKeyConstraint(['project_id', 'topic_row_id'], ['topics.project_id', 'topics.id'],
                             name='fk_topic_versions_topic_same_project'),
    )


class TopicEvidence(Base):
    """工程计划 5.2 主题证据:同版本/分块关联唯一,计数按 distinct feedback_id。

    `segment_id` 用空串表示「关联到反馈级」而不是分块级:首版一个反馈一段证据,
    而 SQL 唯一约束不约束 NULL(含 NULL 的行会被当成各不相同),用可空列的话
    「同版本同反馈只能有一条」这条约束在 PostgreSQL 上根本不生效。
    接分块级证据(8.3:同一反馈最多贡献两段)时填真实 segment_id。
    """

    __tablename__ = 'topic_evidence'
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    topic_version_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    feedback_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    segment_id: Mapped[str] = mapped_column(String(96), nullable=False, default='')
    source_row: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quote: Mapped[str] = mapped_column(Text, nullable=False, default='')
    quote_start: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quote_end: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    similarity: Mapped[float | None] = mapped_column(Numeric(6, 5))
    is_representative: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    __table_args__ = (
        UniqueConstraint('topic_version_id', 'feedback_id', 'segment_id',
                         name='uq_topic_evidence_version_feedback_segment'),
        ForeignKeyConstraint(['project_id', 'feedback_id'], ['feedback.project_id', 'feedback.id'],
                             name='fk_topic_evidence_feedback_same_project'),
    )


class AnalysisRevision(Base):
    """工程计划 5.2 分析修订:`(run_id, revision)` 唯一,manifest 固定
    topic_id → topic_version_id。

    旧 revision 永远可读,且**不随最新的主题版本被动改写**——这一点靠的是
    manifest 记的是那一版的具体 version id,而不是「按名字去找当前的同名主题」。
    """

    __tablename__ = 'analysis_revisions'
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    topic_manifest_json: Mapped[dict | None] = mapped_column(JSON, default=dict)
    unassigned_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str | None] = mapped_column(Text)
    actor_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    __table_args__ = (
        UniqueConstraint('run_id', 'revision', name='uq_analysis_revisions_run_revision'),
        Index('ix_analysis_revisions_project_run', 'project_id', 'run_id'),
    )


class TopicCorrection(Base):
    """工程计划 5.2 校正记录:记录 merge/split/rename/create;不保存未脱敏正文。"""

    __tablename__ = 'topic_corrections'
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    from_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    to_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    source_topic_ids: Mapped[list | None] = mapped_column(JSON, default=list)
    target_topic_ids: Mapped[list | None] = mapped_column(JSON, default=list)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)


class RunFeedback(Base):
    """工程计划 5.2:冻结一次分析的输入反馈集合。

    5.3「输入固定」要求「之后新增反馈不影响这个 run」。第一增量先把清单冻结在
    `analysis_runs.result->run_feedback_ids` 里,那是权宜之计:它不参与任何约束,
    删掉一条反馈后没有东西会阻止清单继续指向它。这张表把同一条语义变成
    `(run_id, feedback_id)` 唯一约束加复合外键。
    """

    __tablename__ = 'run_feedbacks'
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    feedback_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    __table_args__ = (
        UniqueConstraint('run_id', 'feedback_id', name='uq_run_feedbacks_run_feedback'),
        ForeignKeyConstraint(
            ['project_id', 'feedback_id'], ['feedback.project_id', 'feedback.id'],
            name='fk_run_feedbacks_feedback_same_project',
        ),
    )


class Segment(Base):
    """工程计划 5.2 分块:offset 指向 `feedback.content_redacted` 的 Unicode 字符位置。

    不存分块正文:正文是 `content_redacted[start:end]` 的函数,存一份副本就多一个
    与正文不一致的机会。8.2 要求的「offset 用脱敏正文的字符位置」在这里才真正成立。
    """

    __tablename__ = 'segments'
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    feedback_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    redaction_version: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    __table_args__ = (
        ForeignKeyConstraint(
            ['project_id', 'feedback_id'], ['feedback.project_id', 'feedback.id'],
            name='fk_segments_feedback_same_project',
        ),
        UniqueConstraint('feedback_id', 'segment_index', 'redaction_version',
                         name='uq_segments_feedback_index_version'),
    )





