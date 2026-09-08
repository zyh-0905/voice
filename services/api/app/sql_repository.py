from collections.abc import MutableMapping, Iterator
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import Base, engine, SessionLocal
from .models import Dataset, AnalysisRun

class _EntityMap(MutableMapping):
    def __init__(self, repo, kind): self.repo, self.kind = repo, kind
    def _model(self): return Dataset if self.kind == 'datasets' else AnalysisRun
    def _to_dict(self, obj):
        if self.kind == 'datasets':
            d = dict(obj.governance or {})
            d.update(id=obj.id, project_id=obj.project_id, name=obj.filename,
                     status=obj.status, created_at=obj.created_at.isoformat() if obj.created_at else None)
            return d
        d = dict(obj.result or {})
        d.update(id=obj.id, project_id=obj.project_id, status=obj.status)
        return d
    def __getitem__(self, key):
        with self.repo.session() as s:
            obj = s.get(self._model(), key)
            if obj is None: raise KeyError(key)
            return self._to_dict(obj)
    def __setitem__(self, key, value):
        with self.repo.session() as s:
            m = self._model(); obj = s.get(m, key)
            if self.kind == 'datasets':
                if obj is None: obj = m(id=key, project_id=value['project_id'], filename=value.get('name', key))
                obj.project_id = value.get('project_id', obj.project_id); obj.filename = value.get('name', obj.filename); obj.status = value.get('status', obj.status); obj.governance = dict(value)
            else:
                if obj is None: obj = m(id=key, project_id=value['project_id'], dataset_id=(value.get('dataset_ids') or [''])[0])
                obj.project_id = value.get('project_id', obj.project_id); obj.status = value.get('status', obj.status); obj.result = dict(value)
            s.add(obj); s.commit()
    def __delitem__(self, key):
        with self.repo.session() as s:
            obj=s.get(self._model(), key)
            if obj is None: raise KeyError(key)
            s.delete(obj); s.commit()
    def __iter__(self):
        with self.repo.session() as s:
            rows=s.scalars(select(self._model())).all()
        return iter([x.id for x in rows])
    def __len__(self):
        with self.repo.session() as s: return len(s.scalars(select(self._model())).all())
    def values(self):
        with self.repo.session() as s: return [self._to_dict(x) for x in s.scalars(select(self._model())).all()]

class SQLAlchemyRepository:
    def __init__(self, create_schema=True):
        if create_schema: Base.metadata.create_all(engine)
        self.datasets = _EntityMap(self, 'datasets'); self.analyses = _EntityMap(self, 'analyses')
    def session(self): return SessionLocal()

repository = SQLAlchemyRepository()
