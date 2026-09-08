from collections.abc import MutableMapping
from copy import deepcopy
from typing import Protocol
import os


class Repository(Protocol):
    def list_projects(self) -> list[dict]: ...
    def get_project(self, key: str) -> dict | None: ...
    def create_project(self, value: dict) -> dict: ...
    datasets: MutableMapping[str, dict]
    analyses: MutableMapping[str, dict]
    outbox: list[dict]

    def create_dataset(self, value: dict) -> dict: ...
    def update_dataset(self, key: str, changes: dict) -> dict: ...
    def delete_dataset(self, key: str) -> None: ...
    def create_analysis(self, value: dict) -> dict: ...
    def update_analysis(self, key: str, changes: dict) -> dict: ...
    def create_outbox_event(self, event: dict) -> dict: ...
    def list_pending_outbox(self, limit: int | None = None) -> list[dict]: ...
    def mark_published(self, event_key: str) -> None: ...
    def mark_publish_failed(self, event_key: str, error: str) -> None: ...
    def list_entities(self, kind: str, project_id: str) -> list[dict]: ...
    def create_entity(self, kind: str, value: dict) -> dict: ...
    def update_entity(self, kind: str, key: str, changes: dict) -> dict: ...


class InMemoryRepository:
    def __init__(self):
        self.projects = {}
        self.datasets = {}
        self.analyses = {}
        self.outbox = []
        self.risks, self.tasks, self.reviews = {}, {}, {}

    def _create(self, collection, value):
        key = value['id']
        if key in collection:
            raise ValueError(f'Entity already exists: {key}')
        collection[key] = deepcopy(value)
        return deepcopy(collection[key])

    def list_projects(self): return [deepcopy(v) for v in self.projects.values()]
    def get_project(self, key): return deepcopy(self.projects.get(key))
    def create_project(self, value): return self._create(self.projects, value)

    def _update(self, collection, key, changes):
        collection[key].update(deepcopy(changes))
        return deepcopy(collection[key])

    def create_dataset(self, value): return self._create(self.datasets, value)
    def update_dataset(self, key, changes): return self._update(self.datasets, key, changes)
    def delete_dataset(self, key):
        if key not in self.datasets: raise KeyError(key)
        del self.datasets[key]
    def create_analysis(self, value): return self._create(self.analyses, value)
    def update_analysis(self, key, changes): return self._update(self.analyses, key, changes)
    def list_entities(self, kind, project_id): return [deepcopy(v) for v in getattr(self, kind).values() if v.get('project_id') == project_id]
    def create_entity(self, kind, value): return self._create(getattr(self, kind), value)
    def update_entity(self, kind, key, changes): return self._update(getattr(self, kind), key, changes)
    def create_outbox_event(self, event):
        if any(e['event_key'] == event['event_key'] for e in self.outbox): return next(e for e in self.outbox if e['event_key'] == event['event_key'])
        value = deepcopy({**event, 'status': event.get('status', 'pending')}); self.outbox.append(value); return deepcopy(value)
    def list_pending_outbox(self, limit=None):
        events = [e for e in self.outbox if e.get('status') == 'pending']
        return deepcopy(events[:limit] if limit is not None else events)
    def mark_published(self, event_key):
        for e in self.outbox:
            if e['event_key'] == event_key: e['status'] = 'published'; return
    def mark_publish_failed(self, event_key, error):
        for e in self.outbox:
            if e['event_key'] == event_key:
                e['last_error'] = str(error)
                e['attempts'] = int(e.get('attempts', 0)) + 1
                return


repository = InMemoryRepository()


def get_repository():
    if os.getenv('USE_DATABASE', '').lower() in ('1', 'true', 'yes'):
        from .sql_repository import SQLAlchemyRepository
        return SQLAlchemyRepository()
    return InMemoryRepository()
