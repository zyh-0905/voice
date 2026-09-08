from collections.abc import MutableMapping
from copy import deepcopy
from typing import Protocol
import os


class Repository(Protocol):
    datasets: MutableMapping[str, dict]
    analyses: MutableMapping[str, dict]
    outbox: list[dict]

    def create_dataset(self, value: dict) -> dict: ...
    def update_dataset(self, key: str, changes: dict) -> dict: ...
    def create_analysis(self, value: dict) -> dict: ...
    def update_analysis(self, key: str, changes: dict) -> dict: ...
    def create_outbox_event(self, event: dict) -> dict: ...
    def list_pending_outbox(self) -> list[dict]: ...
    def mark_published(self, event_key: str) -> None: ...


class InMemoryRepository:
    def __init__(self):
        self.datasets = {}
        self.analyses = {}
        self.outbox = []

    def _create(self, collection, value):
        key = value['id']
        if key in collection:
            raise ValueError(f'Entity already exists: {key}')
        collection[key] = deepcopy(value)
        return deepcopy(collection[key])

    def _update(self, collection, key, changes):
        collection[key].update(deepcopy(changes))
        return deepcopy(collection[key])

    def create_dataset(self, value): return self._create(self.datasets, value)
    def update_dataset(self, key, changes): return self._update(self.datasets, key, changes)
    def create_analysis(self, value): return self._create(self.analyses, value)
    def update_analysis(self, key, changes): return self._update(self.analyses, key, changes)
    def create_outbox_event(self, event):
        if any(e['event_key'] == event['event_key'] for e in self.outbox): return next(e for e in self.outbox if e['event_key'] == event['event_key'])
        value = deepcopy({**event, 'status': event.get('status', 'pending')}); self.outbox.append(value); return deepcopy(value)
    def list_pending_outbox(self): return [deepcopy(e) for e in self.outbox if e.get('status') == 'pending']
    def mark_published(self, event_key):
        for e in self.outbox:
            if e['event_key'] == event_key: e['status'] = 'published'; return


repository = InMemoryRepository()


def get_repository():
    if os.getenv('USE_DATABASE', '').lower() in ('1', 'true', 'yes'):
        from .sql_repository import SQLAlchemyRepository
        return SQLAlchemyRepository()
    return InMemoryRepository()
