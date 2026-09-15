from collections.abc import MutableMapping
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from .db import Base, SessionLocal
from .models import (AnalysisRevision, AnalysisRun, AnalysisStage, Dataset, DeletionJob,
                     ExportJob, Feedback, IdempotencyKey, Membership, ModelCall, OutboxEvent,
                     Project, Review, RiskAudit, RiskFinding, RunFeedback, Segment, Task,
                     TaskEvent, TaskEvidence, Topic, TopicCorrection, TopicEvidence,
                     TopicVersion)
from .repository import MAX_PUBLISH_ATTEMPTS, same_event
from .segments import segment_id as segments_segment_id

# 模型列与 plan 行的字段名不完全一致(claims/limitations 在库里带 _json 后缀),
# 映射集中在这里:散在调用点上会漏掉一处,而漏掉的表现是「这个字段永远是默认值」。
_VERSION_FIELDS = ('id', 'project_id', 'run_id', 'topic_id', 'topic_row_id', 'version',
                   'revision', 'name', 'summary', 'severity', 'department',
                   'suggested_action', 'needs_review', 'summary_revalidated', 'origin')
_VERSION_JSON_FIELDS = {'claims_json': 'claims', 'limitations_json': 'limitations'}
_EVIDENCE_FIELDS = ('id', 'project_id', 'topic_version_id', 'feedback_id', 'segment_id',
                    'source_row', 'quote', 'quote_start', 'quote_end', 'similarity',
                    'is_representative')


def _version_kwargs(version: dict) -> dict:
    kwargs = {key: version.get(key) for key in _VERSION_FIELDS}
    for column, source in _VERSION_JSON_FIELDS.items():
        kwargs[column] = list(version.get(source) or [])
    return kwargs


def _evidence_kwargs(evidence: dict) -> dict:
    return {key: evidence.get(key) for key in _EVIDENCE_FIELDS}


def _task_event_kwargs(project_id: str, task_id: str, event: dict) -> dict:
    """事件行的列映射;`material_refs_json` 缺省为空列表而不是 None——
    计划要求它是「材料引用」,首版没有材料,空列表表示「没有引用」,
    而 None 会让人分不清「没有」还是「没记」。"""
    return {
        'id': event['id'], 'project_id': project_id, 'task_id': task_id,
        'action': str(event.get('action') or ''),
        'from_state': str(event.get('from_state') or ''),
        'to_state': str(event.get('to_state') or ''),
        'actor_id': event.get('actor_id'),
        'comment_redacted': str(event.get('comment_redacted') or ''),
        'material_refs_json': list(event.get('material_refs_json') or []),
    }


class _EntityMap(MutableMapping):
    """Compatibility mapping. Reads are snapshots; writes explicitly commit."""
    def __init__(self, repo, kind):
        self.repo, self.kind = repo, kind

    def _model(self):
        return Dataset if self.kind == 'datasets' else AnalysisRun

    def _to_dict(self, obj):
        if self.kind == 'datasets':
            value = dict(obj.governance or {})
            # **只覆盖真正的列。** content_hash / source_namespace / source_kind 不是
            # datasets 表的列——它们存在 governance 里。此前这里用
            # `getattr(obj, 'content_hash', None)` 读回来(永远 None),把 governance 里
            # 正确的值覆盖成空:于是 SQL 模式下
            # `event_key = HMAC(secret, content_hash + sheet_name + source_row)`
            # 退化成 `HMAC(secret, '' + '' + source_row)`——一个项目里所有数据集按行号
            # 共用同一个事件键,第二批次的第 0 行被判成第一批次第 0 行的冲突。
            # 内存仓储原样存 dict,所以完全看不见。
            value.update(id=obj.id, project_id=obj.project_id, name=obj.filename, status=obj.status)
            value.setdefault('created_at', obj.created_at.isoformat() if obj.created_at else None)
            return value
        value = dict(obj.result or {})
        value.update(id=obj.id, project_id=obj.project_id, status=obj.status)
        return value

    def _assign(self, obj, key, value):
        if value.get('id', key) != key:
            raise ValueError('Entity ID cannot change')
        obj.project_id = value['project_id']
        obj.status = value.get('status', 'uploaded' if self.kind == 'datasets' else 'queued')
        if self.kind == 'datasets':
            obj.filename = value.get('name', key)
            # 不写 obj.content_hash / source_namespace / source_kind:它们不是列,
            # 赋上去只会成为「本进程可见、重启即消失」的幻影属性,而读取端会以为拿到了真值。
            # governance 是这些字段的唯一存储。
            obj.governance = dict(value)
        else:
            obj.dataset_id = (value.get('dataset_ids') or [''])[0]
            obj.result = dict(value)

    def __getitem__(self, key):
        with self.repo.session() as session:
            obj = session.get(self._model(), key)
            if obj is None:
                raise KeyError(key)
            return self._to_dict(obj)

    def write(self, key, value, operation='upsert'):
        with self.repo.session() as session, session.begin():
            obj = session.get(self._model(), key, with_for_update=True)
            if operation == 'create' and obj is not None:
                raise ValueError(f'Entity already exists: {key}')
            if operation == 'update':
                if obj is None:
                    raise KeyError(key)
                value = {**self._to_dict(obj), **value}
            if obj is None:
                obj = self._model()(id=key)
                session.add(obj)
            self._assign(obj, key, value)
            session.flush()
            result = self._to_dict(obj)
        return result

    def __setitem__(self, key, value):
        self.write(key, value)

    def __delitem__(self, key):
        with self.repo.session() as session, session.begin():
            obj = session.get(self._model(), key)
            if obj is None:
                raise KeyError(key)
            session.delete(obj)

    def __iter__(self):
        with self.repo.session() as session:
            return iter(session.scalars(select(self._model().id)).all())

    def __len__(self):
        return len(list(iter(self)))

    def values(self):
        with self.repo.session() as session:
            return [self._to_dict(obj) for obj in session.scalars(select(self._model())).all()]


class SQLAlchemyRepository:
    def __init__(self, create_schema=True, session_factory=None):
        self._session_factory = session_factory or SessionLocal
        if create_schema:
            with self.session() as session:
                Base.metadata.create_all(session.get_bind())
        self.datasets = _EntityMap(self, 'datasets')
        self.analyses = _EntityMap(self, 'analyses')
        self._domain = {'tasks': Task, 'reviews': Review, 'audits': RiskAudit, 'deletions': DeletionJob, 'exports': ExportJob}

    def _project_dict(self, obj):
        return {'id': obj.id, 'name': obj.name, 'description': 'Project', 'status': 'active',
                'timezone': obj.timezone}
    def list_projects(self):
        with self.session() as s:
            return [self._project_dict(o) for o in s.scalars(select(Project)).all()]
    def get_project(self, key):
        with self.session() as s:
            o = s.get(Project, key)
            return self._project_dict(o) if o else None
    def create_project(self, value):
        with self.session() as s, s.begin():
            o = Project(id=value['id'], name=value['name'], timezone=value.get('timezone'))
            s.add(o); s.flush()
            return self._project_dict(o)

    # —— W03 成员关系与项目设置:显式提交,返回普通 dict ——
    @staticmethod
    def _membership_dict(obj):
        return {'project_id': obj.project_id, 'user_id': obj.user_id,
                'role': obj.role, 'display_name': obj.display_name}

    def list_members(self, project_id):
        with self.session() as s:
            rows = s.scalars(select(Membership).where(Membership.project_id == project_id)
                             .order_by(Membership.user_id)).all()
            return [self._membership_dict(o) for o in rows]

    def list_user_memberships(self, user_id):
        with self.session() as s:
            rows = s.scalars(select(Membership).where(Membership.user_id == user_id)
                             .order_by(Membership.project_id)).all()
            return [self._membership_dict(o) for o in rows]

    def get_membership(self, project_id, user_id):
        with self.session() as s:
            o = s.get(Membership, (project_id, user_id))
            return self._membership_dict(o) if o is not None else None

    def get_member_role(self, project_id, user_id):
        membership = self.get_membership(project_id, user_id)
        return membership['role'] if membership else None

    def create_membership(self, value):
        with self.session() as s, s.begin():
            o = Membership(project_id=value['project_id'], user_id=value['user_id'],
                           role=value['role'], display_name=value.get('display_name'))
            s.add(o)
            try:
                s.flush()
            except IntegrityError:
                raise ValueError(f'Membership already exists: {value["project_id"]}/{value["user_id"]}') from None
            return self._membership_dict(o)

    def set_member_role(self, project_id, user_id, role):
        with self.session() as s, s.begin():
            o = s.get(Membership, (project_id, user_id))
            if o is None:
                raise KeyError(f'{project_id}/{user_id}')
            o.role = role
            s.flush()
            return self._membership_dict(o)

    def delete_memberships(self, project_id):
        """项目删除时连同成员关系一起清理(10.4 级联):留下孤儿行等于留了访问权。"""
        with self.session() as s, s.begin():
            return s.query(Membership).filter(Membership.project_id == project_id).delete()

    def get_project_settings(self, project_id):
        with self.session() as s:
            o = s.get(Project, project_id)
            if o is None:
                return None
            stored = dict(o.settings_json or {})
            if o.timezone is not None:
                stored['timezone'] = o.timezone
            return stored

    def update_project_settings(self, project_id, changes):
        with self.session() as s, s.begin():
            o = s.get(Project, project_id)
            if o is None:
                raise KeyError(project_id)
            if changes.get('timezone') is not None:
                o.timezone = changes['timezone']
            stored = dict(o.settings_json or {})
            stored.update({key: value for key, value in changes.items() if key != 'timezone'})
            o.settings_json = stored
            s.flush()
            result = dict(stored)
            if o.timezone is not None:
                result['timezone'] = o.timezone
            return result

    def list_entities(self, kind, project_id):
        model = self._domain[kind]
        with self.session() as s:
            return [{c.name: getattr(o,c.name) for c in model.__table__.columns} for o in s.scalars(select(model).where(model.project_id == project_id)).all()]
    def create_entity(self, kind, value):
        model = self._domain[kind]
        with self.session() as s, s.begin():
            o = model(**{k:v for k,v in value.items() if k in model.__table__.columns.keys()}); s.add(o); s.flush()
            return {c.name:getattr(o,c.name) for c in model.__table__.columns}
    def update_entity(self, kind, key, changes):
        model = self._domain[kind]
        with self.session() as s, s.begin():
            o=s.get(model,key)
            if o is None: raise KeyError(key)
            for k,v in changes.items():
                if k in model.__table__.columns.keys() and k != 'id': setattr(o,k,v)
            s.flush(); return {c.name:getattr(o,c.name) for c in model.__table__.columns}

    def delete_entity(self, kind, key):
        model = self._domain[kind]
        with self.session() as s, s.begin():
            o = s.get(model, key)
            if o is None: raise KeyError(key)
            s.delete(o)

    def delete_analysis(self, key):
        del self.analyses[key]

    def delete_project(self, key):
        with self.session() as s, s.begin():
            o = s.get(Project, key)
            if o is not None: s.delete(o)

    def session(self):
        return self._session_factory()

    def create_dataset(self, value): return self.datasets.write(value['id'], value, 'create')
    def update_dataset(self, key, changes): return self.datasets.write(key, changes, 'update')
    def delete_dataset(self, key): del self.datasets[key]
    def get_analysis(self, key):
        try:
            return self.analyses[key]
        except KeyError:
            return None
    def create_analysis(self, value): return self.analyses.write(value['id'], value, 'create')
    def update_analysis(self, key, changes): return self.analyses.write(key, changes, 'update')
    def create_outbox_event(self, event):
        with self.session() as session, session.begin():
            obj = OutboxEvent(event_key=event['event_key'], event_type=event['event_type'], payload=event.get('payload', {}), status=event.get('status','pending'))
            session.add(obj); session.flush()
            return {'id': obj.id, 'event_key': obj.event_key, 'event_type': obj.event_type, 'payload': obj.payload, 'status': obj.status, 'created_at': obj.created_at.isoformat()}
    def list_pending_outbox(self, limit=None):
        with self.session() as session:
            query = select(OutboxEvent).where(OutboxEvent.status=='pending').order_by(OutboxEvent.id)
            if limit is not None: query = query.limit(limit)
            return [{'id':o.id,'event_key':o.event_key,'event_type':o.event_type,'payload':o.payload,'status':o.status,'created_at':o.created_at.isoformat()} for o in session.scalars(query).all()]
    def mark_published(self, event_key):
        with self.session() as session, session.begin():
            obj = session.scalars(select(OutboxEvent).where(OutboxEvent.event_key==event_key)).first()
            if obj: obj.status='published'
    def mark_publish_failed(self, event_key, error):
        with self.session() as session, session.begin():
            obj = session.scalars(select(OutboxEvent).where(OutboxEvent.event_key==event_key)).first()
            if obj:
                attempts = int((obj.payload or {}).get('_relay_attempts', 0)) + 1
                obj.payload = {**(obj.payload or {}), '_relay_error': str(error), '_relay_attempts': attempts}
                if attempts >= MAX_PUBLISH_ATTEMPTS:
                    obj.status = 'failed'

    def get_idempotency(self, key):
        with self.session() as session:
            obj = session.get(IdempotencyKey, key)
            if obj is None:
                return None
            return {'key': obj.key, 'project_id': obj.project_id, 'fingerprint': obj.fingerprint, 'analysis_id': obj.analysis_id}

    # —— §5.2 反馈与分块实体 ——
    # 读取一律返回普通 dict 而不是 ORM 对象:session 一关就 detached,
    # 调用方拿到的行在别处访问会炸,而内存仓储不会——那种差异只在真实部署出现。
    @staticmethod
    def _feedback_dict(obj):
        return {
            'id': obj.id, 'project_id': obj.project_id, 'dataset_id': obj.dataset_id,
            'external_id': obj.external_id, 'event_key': obj.event_key,
            'content_redacted': obj.content_redacted, 'content_hash': obj.content_hash,
            'occurred_at': obj.occurred_at.isoformat() if obj.occurred_at else None,
            'time_quality': obj.time_quality, 'channel': obj.channel, 'product': obj.product,
            'rating': float(obj.rating) if obj.rating is not None else None,
            'source_status': obj.source_status, 'order_ref_redacted': obj.order_ref_redacted,
            'source_row': obj.source_row, 'source_kind': obj.source_kind,
            'identity_quality': obj.identity_quality,
            'redaction_version': obj.redaction_version,
        }

    # —— §5.2 分析修订与主题版本 ——
    @staticmethod
    def _topic_version_dict(obj):
        return {'id': obj.id, 'project_id': obj.project_id, 'topic_id': obj.topic_id,
                'version': obj.version, 'revision': obj.revision, 'name': obj.name,
                'summary': obj.summary, 'severity': obj.severity, 'department': obj.department,
                'claims': list(obj.claims_json or []), 'suggested_action': obj.suggested_action,
                'needs_review': obj.needs_review, 'summary_revalidated': obj.summary_revalidated,
                'limitations': list(obj.limitations_json or []), 'origin': obj.origin}

    @staticmethod
    def _evidence_dict(obj):
        return {'id': obj.id, 'project_id': obj.project_id, 'topic_version_id': obj.topic_version_id,
                'feedback_id': obj.feedback_id, 'segment_id': obj.segment_id,
                'source_row': obj.source_row, 'quote': obj.quote,
                'quote_start': obj.quote_start, 'quote_end': obj.quote_end,
                'similarity': float(obj.similarity) if obj.similarity is not None else None,
                'is_representative': obj.is_representative}

    def save_revision(self, project_id, run_id, plan):
        """一次事务写入主题行、版本行、证据行与该 revision 记录。

        半份修订会同时破坏「(run_id, revision) 唯一」与「旧 revision 永远可读」:
        manifest 会指向不存在的版本,而读取端只能少给一个主题——那是最难发现的
        失败,因为它看起来像「这个主题没有证据」。
        """

        with self.session() as s, s.begin():
            for topic in plan['topics']:
                existing = s.get(Topic, topic['id'])
                if existing is None:
                    s.add(Topic(project_id=project_id, run_id=run_id, **{
                        key: topic[key] for key in ('id', 'topic_id', 'current_version_id', 'state')}))
                else:
                    # 主题在同一次分析内 id 稳定,但版本指针要推进到最新
                    existing.current_version_id = topic['current_version_id']
                    existing.state = topic['state']
            s.flush()
            for version in plan['versions']:
                s.add(TopicVersion(**_version_kwargs(version)))
            s.flush()
            for evidence in plan['evidence']:
                s.add(TopicEvidence(**_evidence_kwargs(evidence)))
            record = plan['revision']
            s.add(AnalysisRevision(**{key: record[key] for key in (
                'id', 'project_id', 'run_id', 'revision', 'topic_manifest_json',
                'unassigned_count', 'reason', 'actor_id')}))
            s.flush()
        return record

    def latest_revision(self, project_id, run_id):
        with self.session() as s:
            return s.scalar(select(func.max(AnalysisRevision.revision)).where(
                AnalysisRevision.project_id == project_id,
                AnalysisRevision.run_id == run_id))

    def get_analysis_revision(self, project_id, run_id, revision):
        with self.session() as s:
            obj = s.scalars(select(AnalysisRevision).where(
                AnalysisRevision.project_id == project_id,
                AnalysisRevision.run_id == run_id,
                AnalysisRevision.revision == revision)).first()
            if obj is None:
                return None
            return {'id': obj.id, 'project_id': obj.project_id, 'run_id': obj.run_id,
                    'revision': obj.revision,
                    'topic_manifest_json': dict(obj.topic_manifest_json or {}),
                    'unassigned_count': obj.unassigned_count,
                    'reason': obj.reason, 'actor_id': obj.actor_id}

    def get_topic_version(self, project_id, version_id):
        with self.session() as s:
            obj = s.get(TopicVersion, version_id)
            if obj is None or obj.project_id != project_id:
                return None
            return self._topic_version_dict(obj)

    def list_topic_evidence(self, project_id, version_id):
        with self.session() as s:
            rows = s.scalars(select(TopicEvidence).where(
                TopicEvidence.project_id == project_id,
                TopicEvidence.topic_version_id == version_id).order_by(TopicEvidence.id)).all()
            return [self._evidence_dict(o) for o in rows]

    def save_topic_correction(self, project_id, record):
        with self.session() as s, s.begin():
            s.add(TopicCorrection(project_id=project_id, **{
                key: record[key] for key in (
                    'id', 'run_id', 'from_revision', 'to_revision', 'operation',
                    'source_topic_ids', 'target_topic_ids', 'reason', 'actor_id')}))
            s.flush()
        return record

    def list_topic_corrections(self, project_id, run_id):
        with self.session() as s:
            rows = s.scalars(select(TopicCorrection).where(
                TopicCorrection.project_id == project_id,
                TopicCorrection.run_id == run_id).order_by(TopicCorrection.id)).all()
            return [{'id': o.id, 'project_id': o.project_id, 'run_id': o.run_id,
                     'from_revision': o.from_revision, 'to_revision': o.to_revision,
                     'operation': o.operation,
                     'source_topic_ids': list(o.source_topic_ids or []),
                     'target_topic_ids': list(o.target_topic_ids or []),
                     'reason': o.reason, 'actor_id': o.actor_id} for o in rows]

    def next_versions_for_run(self, project_id, run_id):
        """每个主题的下一个可用版本号,键是**业务 topic_id**(见内存实现处的说明)。"""
        with self.session() as s:
            topic_ids = list(s.scalars(select(Topic.topic_id).where(
                Topic.project_id == project_id, Topic.run_id == run_id)).all())
            if not topic_ids:
                return {}
            rows = s.execute(
                select(TopicVersion.topic_id, func.max(TopicVersion.version))
                .where(TopicVersion.project_id == project_id,
                       TopicVersion.run_id == run_id,
                       TopicVersion.topic_id.in_(topic_ids))
                .group_by(TopicVersion.topic_id)).all()
            highest = {topic_id: int(version or 0) for topic_id, version in rows}
            return {topic_id: highest.get(topic_id, 0) + 1 for topic_id in topic_ids}

    # —— §5.2 分析阶段 / 风险候选 / 模型调用 ——
    @staticmethod
    def _stage_dict(obj):
        return {'id': obj.id, 'project_id': obj.project_id, 'run_id': obj.run_id,
                'stage': obj.stage, 'config_hash': obj.config_hash, 'attempt': obj.attempt,
                'state': obj.state, 'output_file_id': obj.output_file_id,
                'output_hash': obj.output_hash,
                'started_at': obj.started_at.isoformat() if obj.started_at else None,
                'finished_at': obj.finished_at.isoformat() if obj.finished_at else None,
                'lease_epoch': obj.lease_epoch}

    @staticmethod
    def _finding_dict(obj):
        return {'id': obj.id, 'project_id': obj.project_id, 'run_id': obj.run_id,
                'feedback_id': obj.feedback_id, 'source_row': obj.source_row,
                'rule_id': obj.rule_id, 'policy_version': obj.policy_version,
                'severity': obj.severity, 'reason': obj.reason,
                'evidence_offsets': dict(obj.evidence_offsets or {}) or None,
                'review_state': obj.review_state, 'status': obj.status,
                'version': obj.version, 'reviewer_id': obj.reviewer_id,
                'review_reason': obj.review_reason, 'reviewed_at': obj.reviewed_at}

    def save_stages(self, project_id, run_id, stages):
        """写阶段记录;`(run_id, stage, config_hash)` 已存在则推进 attempt 与状态。"""
        with self.session() as s, s.begin():
            for stage in stages:
                key = (run_id, stage['stage'], stage.get('config_hash') or '')
                config_hash = stage.get('config_hash') or ''
                row = s.scalars(select(AnalysisStage).where(
                    AnalysisStage.run_id == run_id, AnalysisStage.stage == stage['stage'],
                    # 括号不能省:`A == x or ''` 会被解析成 `(A == x) or ''`,
                    # 而 SQLAlchemy 子句转 bool 直接抛异常——整条流水线在 SQL 模式下
                    # 会以 status='error' 结束,内存模式却完全正常。
                    AnalysisStage.config_hash == config_hash)).first()
                if row is None:
                    s.add(AnalysisStage(
                        id=stage.get('id') or f'stg_{run_id}_{stage["stage"]}_{key[2]}',
                        project_id=project_id, run_id=run_id, stage=stage['stage'],
                        config_hash=stage.get('config_hash') or '',
                        attempt=int(stage.get('attempt') or 1),
                        state=stage.get('state') or 'PENDING',
                        output_file_id=stage.get('output_file_id'),
                        output_hash=stage.get('output_hash'),
                        started_at=stage.get('started_at'), finished_at=stage.get('finished_at'),
                        lease_epoch=int(stage.get('lease_epoch') or 0)))
                else:
                    row.attempt = int(stage.get('attempt') or row.attempt)
                    row.state = stage.get('state') or row.state
                    for name in ('output_file_id', 'output_hash', 'started_at', 'finished_at'):
                        if stage.get(name) is not None:
                            setattr(row, name, stage[name])
            s.flush()
            return len(stages)

    def list_stages(self, project_id, run_id):
        with self.session() as s:
            rows = s.scalars(select(AnalysisStage).where(
                AnalysisStage.project_id == project_id,
                AnalysisStage.run_id == run_id).order_by(AnalysisStage.stage)).all()
            return [self._stage_dict(o) for o in rows]

    def save_risk_findings(self, project_id, run_id, findings):
        """按 (feedback_id, rule_id, policy_version) 写入或刷新;人工裁决优先。"""
        created = refreshed = human_decided = 0
        with self.session() as s, s.begin():
            for finding in findings:
                prior = s.get(RiskFinding, finding['id'])
                if prior is None:
                    s.add(RiskFinding(
                        id=finding['id'], project_id=project_id, run_id=run_id,
                        feedback_id=finding.get('feedback_id'), source_row=finding.get('source_row'),
                        rule_id=finding['rule_id'], policy_version=finding['policy_version'],
                        severity=finding.get('severity') or 'MEDIUM',
                        reason=str(finding.get('reason') or ''),
                        evidence_offsets=finding.get('evidence_offsets'),
                        review_state='pending', status='OPEN', version=1))
                    created += 1
                    continue
                if str(prior.review_state or 'pending').lower() != 'pending':
                    human_decided += 1
                    continue
                prior.severity = finding.get('severity') or prior.severity
                prior.reason = str(finding.get('reason') or prior.reason)
                prior.evidence_offsets = finding.get('evidence_offsets')
                prior.source_row = finding.get('source_row')
                prior.run_id = run_id
                refreshed += 1
            s.flush()
        return {'created': created, 'refreshed': refreshed, 'human_decided': human_decided}

    def list_risk_findings(self, project_id):
        with self.session() as s:
            rows = s.scalars(select(RiskFinding).where(
                RiskFinding.project_id == project_id
            ).order_by(RiskFinding.severity, RiskFinding.id)).all()
            return [self._finding_dict(o) for o in rows]

    def get_risk_finding(self, project_id, finding_id):
        with self.session() as s:
            obj = s.get(RiskFinding, finding_id)
            if obj is None or obj.project_id != project_id:
                return None
            return self._finding_dict(obj)

    def update_risk_finding(self, project_id, finding_id, changes):
        with self.session() as s, s.begin():
            obj = s.get(RiskFinding, finding_id)
            if obj is None or obj.project_id != project_id:
                raise KeyError(finding_id)
            for key, value in changes.items():
                if hasattr(obj, key) and key != 'id':
                    setattr(obj, key, value)
            s.flush()
            return self._finding_dict(obj)

    def delete_risk_findings_for_project(self, project_id):
        with self.session() as s, s.begin():
            return s.query(RiskFinding).filter(RiskFinding.project_id == project_id).delete()

    def delete_risk_findings_for_feedback(self, project_id, feedback_ids):
        """候选挂在 feedback 上(复合外键),删反馈前必须先删它们。"""
        ids = [str(item) for item in feedback_ids]
        if not ids:
            return 0
        with self.session() as s, s.begin():
            return s.query(RiskFinding).filter(
                RiskFinding.project_id == project_id,
                RiskFinding.feedback_id.in_(ids)).delete(synchronize_session=False)

    def save_model_call(self, project_id, record):
        with self.session() as s, s.begin():
            s.add(ModelCall(project_id=project_id, **{
                key: record.get(key) for key in (
                    'id', 'run_id', 'purpose', 'request_hash', 'provider', 'model', 'state',
                    'tokens_in', 'tokens_out', 'cost_estimated', 'cost_actual',
                    'provider_request_id', 'response_file_id')}))
            s.flush()
        return record

    def list_model_calls(self, project_id, run_id=None):
        with self.session() as s:
            query = select(ModelCall).where(ModelCall.project_id == project_id)
            if run_id is not None:
                query = query.where(ModelCall.run_id == run_id)
            rows = s.scalars(query.order_by(ModelCall.created_at)).all()
            return [{'id': o.id, 'project_id': o.project_id, 'run_id': o.run_id,
                     'purpose': o.purpose, 'provider': o.provider, 'model': o.model,
                     'state': o.state, 'tokens_in': o.tokens_in, 'tokens_out': o.tokens_out,
                     'cost_estimated': float(o.cost_estimated) if o.cost_estimated is not None else None,
                     'cost_actual': float(o.cost_actual) if o.cost_actual is not None else None,
                     'provider_request_id': o.provider_request_id,
                     'response_file_id': o.response_file_id,
                     'created_at': o.created_at.isoformat() if o.created_at else None} for o in rows]

    # —— §5.2 任务事件:与任务状态更新同一事务 ——
    @staticmethod
    def _task_event_dict(obj):
        return {'id': obj.id, 'project_id': obj.project_id, 'task_id': obj.task_id,
                'action': obj.action, 'from_state': obj.from_state, 'to_state': obj.to_state,
                'actor_id': obj.actor_id, 'comment_redacted': obj.comment_redacted,
                'material_refs_json': list(obj.material_refs_json or []),
                'created_at': obj.created_at.isoformat() if obj.created_at else None}

    def save_task_transition(self, project_id, task_id, changes, event):
        """更新任务并追加事件,**同一事务**。

        分成两步的话,中间失败会留下一个状态变了但没有对应事件的任务,而时间线
        正好是用来回答「这个状态是谁改的」。
        """
        with self.session() as s, s.begin():
            task = s.get(Task, task_id)
            if task is None or task.project_id != project_id:
                raise KeyError(task_id)
            for key, value in changes.items():
                if key != 'events' and hasattr(task, key):
                    setattr(task, key, value)
            s.add(TaskEvent(**_task_event_kwargs(project_id, task_id, event)))
            s.flush()
            return {column.name: getattr(task, column.name) for column in Task.__table__.columns}

    def append_task_event(self, project_id, task_id, event):
        with self.session() as s, s.begin():
            s.add(TaskEvent(**_task_event_kwargs(project_id, task_id, event)))
            s.flush()
            return event

    def list_task_events(self, project_id, task_id):
        with self.session() as s:
            rows = s.scalars(select(TaskEvent).where(
                TaskEvent.project_id == project_id,
                TaskEvent.task_id == task_id).order_by(TaskEvent.created_at, TaskEvent.id)).all()
            return [self._task_event_dict(o) for o in rows]

    def save_task_evidence(self, project_id, task_id, rows):
        """写入来源快照;已存在的 (task, feedback, version) 不重复写。"""
        added = 0
        with self.session() as s, s.begin():
            for row in rows:
                existing = s.scalars(select(TaskEvidence).where(
                    TaskEvidence.task_id == task_id,
                    TaskEvidence.feedback_id == row['feedback_id'],
                    TaskEvidence.topic_version_id == row.get('topic_version_id'))).first()
                if existing is not None:
                    continue
                s.add(TaskEvidence(
                    id=row['id'], project_id=project_id, task_id=task_id,
                    feedback_id=row['feedback_id'], topic_version_id=row.get('topic_version_id'),
                    quote_redacted=str(row.get('quote_redacted') or '')))
                added += 1
            s.flush()
        return added

    def list_task_evidence(self, project_id, task_id):
        with self.session() as s:
            rows = s.scalars(select(TaskEvidence).where(
                TaskEvidence.project_id == project_id,
                TaskEvidence.task_id == task_id).order_by(TaskEvidence.id)).all()
            return [{'id': o.id, 'project_id': o.project_id, 'task_id': o.task_id,
                     'feedback_id': o.feedback_id, 'topic_version_id': o.topic_version_id,
                     'quote_redacted': o.quote_redacted} for o in rows]

    def delete_task_evidence_for_feedback(self, project_id, feedback_ids):
        """10.4:删源数据要连任务证据一起清——它是源数据的快照,留着就是留着内容。"""
        ids = [str(item) for item in feedback_ids]
        if not ids:
            return 0
        with self.session() as s, s.begin():
            return s.query(TaskEvidence).filter(
                TaskEvidence.project_id == project_id,
                TaskEvidence.feedback_id.in_(ids)).delete(synchronize_session=False)

    def delete_task_data_for_project(self, project_id):
        with self.session() as s, s.begin():
            removed = s.query(TaskEvent).filter(TaskEvent.project_id == project_id).delete()
            s.query(TaskEvidence).filter(TaskEvidence.project_id == project_id).delete()
            return removed

    def delete_run_data_for_project(self, project_id):
        """项目级:阶段与模型调用一同清理。"""
        with self.session() as s, s.begin():
            removed = s.query(AnalysisStage).filter(AnalysisStage.project_id == project_id).delete()
            s.query(ModelCall).filter(ModelCall.project_id == project_id).delete()
            return removed

    def delete_run_data_for_run(self, project_id, run_id):
        """run 级:数据集删除清掉受影响 run 的阶段与模型调用,不留孤儿行。"""
        with self.session() as s, s.begin():
            removed = s.query(AnalysisStage).filter(
                AnalysisStage.project_id == project_id,
                AnalysisStage.run_id == run_id).delete()
            s.query(ModelCall).filter(
                ModelCall.project_id == project_id,
                ModelCall.run_id == run_id).delete()
            return removed

    def count_run_data_for_run(self, project_id, run_id):
        with self.session() as s:
            stages = s.query(AnalysisStage).filter(
                AnalysisStage.project_id == project_id,
                AnalysisStage.run_id == run_id).count()
            calls = s.query(ModelCall).filter(
                ModelCall.project_id == project_id,
                ModelCall.run_id == run_id).count()
            return stages + calls

    def count_run_data_for_project(self, project_id):
        with self.session() as s:
            stages = s.query(AnalysisStage).filter(
                AnalysisStage.project_id == project_id).count()
            calls = s.query(ModelCall).filter(
                ModelCall.project_id == project_id).count()
            return stages + calls

    def count_task_evidence_for_feedback(self, project_id, feedback_ids):
        ids = [str(item) for item in feedback_ids]
        if not ids:
            return 0
        with self.session() as s:
            return s.query(TaskEvidence).filter(
                TaskEvidence.project_id == project_id,
                TaskEvidence.feedback_id.in_(ids)).count()

    def count_topics_for_run(self, project_id, run_id):
        """删除与隔离核验用:某个 run 自己有多少个主题行。"""
        with self.session() as s:
            return int(s.query(Topic).filter(
                Topic.project_id == project_id, Topic.run_id == run_id).count())

    def delete_topics_for_run(self, project_id, run_id):
        """删 run 的主题与修订:证据 → 版本 → 主题 → 修订 → 校正记录。

        顺序由复合外键决定:topic_versions 引用 topics,先删版本再删主题。
        """
        with self.session() as s, s.begin():
            topic_ids = list(s.scalars(select(Topic.id).where(
                Topic.project_id == project_id, Topic.run_id == run_id)).all())
            version_ids = list(s.scalars(select(TopicVersion.id).where(
                TopicVersion.project_id == project_id,
                TopicVersion.topic_row_id.in_(topic_ids or ['']))).all())
            if version_ids:
                s.query(TopicEvidence).filter(
                    TopicEvidence.project_id == project_id,
                    TopicEvidence.topic_version_id.in_(version_ids)).delete(synchronize_session=False)
                s.query(TopicVersion).filter(
                    TopicVersion.project_id == project_id,
                    TopicVersion.id.in_(version_ids)).delete(synchronize_session=False)
            s.query(Topic).filter(Topic.project_id == project_id,
                                  Topic.run_id == run_id).delete(synchronize_session=False)
            s.query(AnalysisRevision).filter(
                AnalysisRevision.project_id == project_id,
                AnalysisRevision.run_id == run_id).delete(synchronize_session=False)
            s.query(TopicCorrection).filter(
                TopicCorrection.project_id == project_id,
                TopicCorrection.run_id == run_id).delete(synchronize_session=False)
            return len(topic_ids)

    def delete_topics_for_project(self, project_id):
        with self.session() as s, s.begin():
            for model in (TopicEvidence, TopicVersion, Topic, AnalysisRevision, TopicCorrection):
                s.query(model).filter(model.project_id == project_id).delete(synchronize_session=False)
            return 0

    def delete_idempotency_for_project(self, project_id):
        """10.4:删除项目要清理「幂等响应正文」(见内存实现处的说明)。"""
        with self.session() as s, s.begin():
            return s.query(IdempotencyKey).filter(
                IdempotencyKey.project_id == project_id).delete()

    def count_idempotency(self, project_id):
        """删除核验用:幂等记录不在 _domain 映射里,不能走 list_entities。"""
        with self.session() as s:
            return int(s.query(IdempotencyKey).filter(
                IdempotencyKey.project_id == project_id).count())

    def save_feedback_rows(self, project_id, dataset_id, rows):
        """按 4.4 写入反馈行;同键同内容算重复,同键异内容记冲突且不覆盖。

        整个批次在一个事务内完成:只写进去一半的话,`input=valid+invalid+duplicate`
        与库里的行数就对不上了。
        """
        inserted = duplicate = 0
        conflicts: list[dict] = []
        claimed: set[str] = set()
        stored: list[int] = []
        with self.session() as s, s.begin():
            # 先删本批次的旧行:重新治理会改变行的位置,而 id 由位置派生,
            # 保旧 id 会与新手行撞主键,按新位置重算又会与本轮旧行撞 event_key。
            removed = s.query(Feedback).filter(
                Feedback.project_id == project_id,
                Feedback.dataset_id == dataset_id).delete(synchronize_session=False)
            s.flush()
            existing = {o.event_key: o for o in s.scalars(
                select(Feedback).where(Feedback.project_id == project_id)).all()}
            for index, row in enumerate(rows):
                prior = existing.get(row['event_key'])
                if prior is not None:
                    if same_event(self._feedback_dict(prior), row):
                        duplicate += 1
                    else:
                        conflicts.append({'source_row': row['source_row'],
                                          'code': 'SOURCE_ID_CONFLICT',
                                          'existing_dataset_id': prior.dataset_id})
                    claimed.add(prior.dataset_id)
                    continue
                obj = Feedback(
                    id=row['id'], project_id=project_id, dataset_id=dataset_id,
                    external_id=row.get('external_id'), event_key=row['event_key'],
                    content_redacted=row['content_redacted'], content_hash=row['content_hash'],
                    occurred_at=row.get('occurred_at'), time_quality=row.get('time_quality') or 'missing',
                    channel=row.get('channel') or 'unknown', product=row.get('product') or 'unknown',
                    rating=row.get('rating'), source_status=row.get('source_status'),
                    order_ref_redacted=row.get('order_ref_redacted'), source_row=row['source_row'],
                    source_kind=row.get('source_kind'),
                    identity_quality=row.get('identity_quality') or 'source_row',
                    redaction_version=row.get('redaction_version') or 'v1',
                )
                s.add(obj)
                s.flush()
                existing[row['event_key']] = obj
                inserted += 1
                stored.append(index)
        return {'inserted': inserted, 'duplicate': duplicate, 'conflicts': conflicts,
                'existing_dataset_ids': sorted(claimed), 'removed': removed,
                # 落库行在入参列表中的下标:调用方据此把预览对齐到**真正存在**的行
                'stored_indexes': stored}

    def list_feedback(self, project_id, dataset_ids=None, feedback_ids=None):
        if feedback_ids is not None and not list(feedback_ids):
            return []
        with self.session() as s:
            query = select(Feedback).where(Feedback.project_id == project_id)
            if dataset_ids is not None:
                query = query.where(Feedback.dataset_id.in_(list(dataset_ids)))
            if feedback_ids is not None:
                query = query.where(Feedback.id.in_(list(feedback_ids)))
            # 与导入时的枚举顺序一致:source_row 升序
            query = query.order_by(Feedback.dataset_id, Feedback.source_row, Feedback.id)
            return [self._feedback_dict(o) for o in s.scalars(query).all()]

    def get_feedback(self, project_id, feedback_id):
        with self.session() as s:
            obj = s.get(Feedback, feedback_id)
            if obj is None or obj.project_id != project_id:
                return None
            return self._feedback_dict(obj)

    def delete_feedback_for_dataset(self, project_id, dataset_id):
        with self.session() as s, s.begin():
            return s.query(Feedback).filter(
                Feedback.project_id == project_id, Feedback.dataset_id == dataset_id).delete()

    def delete_feedback_for_project(self, project_id):
        with self.session() as s, s.begin():
            return s.query(Feedback).filter(Feedback.project_id == project_id).delete()

    def replace_segments(self, project_id, feedback_id, spans, redaction_version):
        """整批替换该反馈的分块;重新分块是重算,不是追加。"""
        with self.session() as s, s.begin():
            s.query(Segment).filter(Segment.project_id == project_id,
                                    Segment.feedback_id == feedback_id).delete()
            for index, span in enumerate(spans):
                s.add(Segment(id=segments_segment_id(feedback_id, index), project_id=project_id,
                              feedback_id=feedback_id, start_offset=span.start,
                              end_offset=span.end, segment_index=index,
                              redaction_version=redaction_version))
            s.flush()
            return len(spans)

    def list_segments(self, project_id, feedback_id):
        with self.session() as s:
            rows = s.scalars(select(Segment).where(
                Segment.project_id == project_id, Segment.feedback_id == feedback_id
            ).order_by(Segment.segment_index)).all()
            return [{'id': o.id, 'project_id': o.project_id, 'feedback_id': o.feedback_id,
                     'start_offset': o.start_offset, 'end_offset': o.end_offset,
                     'segment_index': o.segment_index,
                     'redaction_version': o.redaction_version} for o in rows]

    def count_segments(self, project_id):
        """删除核验用:按项目统计分块数,而不是逐个反馈去问。"""
        with self.session() as s:
            return int(s.query(Segment).filter(Segment.project_id == project_id).count())

    # —— §5.2 run_feedbacks:冻结一次分析的输入集合 ——
    def save_run_feedbacks(self, project_id, run_id, feedback_ids):
        """整批替换该 run 的输入清单;只写 feedback 表里确实存在的 id。

        复合外键本身会拒绝悬空引用,这里先过滤是为了让「输入集合」与
        「实际存在的反馈」一致地收窄,而不是在写入时炸掉整个 run 创建。
        """
        with self.session() as s, s.begin():
            s.query(RunFeedback).filter(RunFeedback.project_id == project_id,
                                        RunFeedback.run_id == run_id).delete(synchronize_session=False)
            live = set(s.scalars(select(Feedback.id).where(
                Feedback.project_id == project_id,
                Feedback.id.in_(list(feedback_ids)))).all()) if feedback_ids else set()
            rows = [RunFeedback(id=f'rf_{run_id}_{index}', project_id=project_id, run_id=run_id,
                                feedback_id=feedback_id)
                    for index, feedback_id in enumerate(feedback_ids) if feedback_id in live]
            for row in rows:
                s.add(row)
            s.flush()
            return len(rows)

    def list_run_feedback_ids(self, project_id, run_id):
        with self.session() as s:
            return list(s.scalars(select(RunFeedback.feedback_id).where(
                RunFeedback.project_id == project_id,
                RunFeedback.run_id == run_id).order_by(RunFeedback.id)).all())

    def delete_run_feedbacks_for_run(self, project_id, run_id):
        with self.session() as s, s.begin():
            return s.query(RunFeedback).filter(
                RunFeedback.project_id == project_id,
                RunFeedback.run_id == run_id).delete()

    def delete_run_feedbacks_for_project(self, project_id):
        with self.session() as s, s.begin():
            return s.query(RunFeedback).filter(RunFeedback.project_id == project_id).delete()

    def count_segments_for_feedback(self, project_id, feedback_ids):
        """数据集级的删除核验:反馈行删掉后无法再按 dataset_id 反查分块,
        所以按删除前捕获的 feedback_id 清单核验。"""
        ids = list(feedback_ids)
        if not ids:
            return 0
        with self.session() as s:
            return int(s.query(Segment).filter(
                Segment.project_id == project_id, Segment.feedback_id.in_(ids)).count())

    def delete_segments_for_project(self, project_id):
        with self.session() as s, s.begin():
            return s.query(Segment).filter(Segment.project_id == project_id).delete()

    def delete_segments_for_dataset(self, project_id, dataset_id):
        """分块随其反馈走:先在同一个事务里定位本批次的反馈,再删除它们的分块。"""
        with self.session() as s, s.begin():
            ids = list(s.scalars(select(Feedback.id).where(
                Feedback.project_id == project_id, Feedback.dataset_id == dataset_id)).all())
            if not ids:
                return 0
            return s.query(Segment).filter(
                Segment.project_id == project_id, Segment.feedback_id.in_(ids)).delete(
                synchronize_session=False)

    def create_idempotency(self, key, value):
        with self.session() as session, session.begin():
            session.add(IdempotencyKey(
                key=key,
                project_id=value['project_id'],
                fingerprint=value['fingerprint'],
                analysis_id=value['analysis_id'],
            ))
            try:
                session.flush()
            except IntegrityError:
                raise ValueError(f'Idempotency key already exists: {key}') from None
            return {'key': key, 'project_id': value['project_id'], 'fingerprint': value['fingerprint'], 'analysis_id': value['analysis_id']}
