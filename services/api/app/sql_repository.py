from collections.abc import MutableMapping
from sqlalchemy import select
from .db import Base, SessionLocal
from .models import Dataset, AnalysisRun, OutboxEvent


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

    def session(self):
        return self._session_factory()

    def create_dataset(self, value): return self.datasets.write(value['id'], value, 'create')
    def update_dataset(self, key, changes): return self.datasets.write(key, changes, 'update')
    def create_analysis(self, value): return self.analyses.write(value['id'], value, 'create')
    def update_analysis(self, key, changes): return self.analyses.write(key, changes, 'update')
    def create_outbox_event(self, event):
        with self.session() as session, session.begin():
            obj = OutboxEvent(event_key=event['event_key'], event_type=event['event_type'], payload=event.get('payload', {}), status=event.get('status','pending'))
            session.add(obj); session.flush()
            return {'id': obj.id, 'event_key': obj.event_key, 'event_type': obj.event_type, 'payload': obj.payload, 'status': obj.status, 'created_at': obj.created_at.isoformat()}
    def list_pending_outbox(self):
        with self.session() as session:
            return [{'id':o.id,'event_key':o.event_key,'event_type':o.event_type,'payload':o.payload,'status':o.status,'created_at':o.created_at.isoformat()} for o in session.scalars(select(OutboxEvent).where(OutboxEvent.status=='pending')).all()]
    def mark_published(self, event_key):
        with self.session() as session, session.begin():
            obj = session.scalars(select(OutboxEvent).where(OutboxEvent.event_key==event_key)).first()
            if obj: obj.status='published'





