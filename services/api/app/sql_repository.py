from collections.abc import MutableMapping
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .db import Base, SessionLocal
from .models import Project, Membership, Dataset, AnalysisRun, OutboxEvent, Risk, RiskAudit, DeletionJob, ExportJob, Task, Review, IdempotencyKey, Feedback, Segment, RunFeedback
from .repository import MAX_PUBLISH_ATTEMPTS, same_event


class _EntityMap(MutableMapping):
    """Compatibility mapping. Reads are snapshots; writes explicitly commit."""
    def __init__(self, repo, kind):
        self.repo, self.kind = repo, kind

    def _model(self):
        return Dataset if self.kind == 'datasets' else AnalysisRun

    def _to_dict(self, obj):
        if self.kind == 'datasets':
            value = dict(obj.governance or {})
            value.update(id=obj.id, project_id=obj.project_id, name=obj.filename, status=obj.status, content_hash=getattr(obj, 'content_hash', None), source_namespace=getattr(obj, 'source_namespace', None), source_kind=getattr(obj, 'source_kind', None))
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
            obj.content_hash = value.get('content_hash')
            obj.source_namespace = value.get('source_namespace')
            obj.source_kind = value.get('source_kind')
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
        self._domain = {'risks': Risk, 'tasks': Task, 'reviews': Review, 'audits': RiskAudit, 'deletions': DeletionJob, 'exports': ExportJob}

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
                s.add(Segment(id=f'seg_{feedback_id}_{index}', project_id=project_id,
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
