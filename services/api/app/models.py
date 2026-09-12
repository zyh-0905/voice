from datetime import datetime
from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    source_namespace: Mapped[str | None] = mapped_column(String(128), index=True)
    source_kind: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

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

class RiskAudit(Base):
    """W14 审计:风险裁决等动作的脱敏元数据(不含正文)。"""
    __tablename__ = 'risk_audits'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[str | None] = mapped_column(String(64))

class Risk(Base):
    __tablename__ = 'risks'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), default='medium', nullable=False)
    status: Mapped[str] = mapped_column(String(32), default='open', nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # W14:候选来源规则与复核状态与 severity 分开
    rule: Mapped[str | None] = mapped_column(String(128))
    review_state: Mapped[str] = mapped_column(String(32), default='pending', nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(64))
    review_reason: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[str | None] = mapped_column(String(64))

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
    finding: Mapped[str] = mapped_column(Text, nullable=False)
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





