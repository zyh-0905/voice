from collections.abc import MutableMapping
from copy import deepcopy
from typing import Protocol
import os

MAX_PUBLISH_ATTEMPTS = 3


class Repository(Protocol):
    def list_projects(self) -> list[dict]: ...
    def get_project(self, key: str) -> dict | None: ...
    def create_project(self, value: dict) -> dict: ...
    def list_members(self, project_id: str) -> list[dict]: ...
    def list_user_memberships(self, user_id: str) -> list[dict]: ...
    def get_membership(self, project_id: str, user_id: str) -> dict | None: ...
    def get_member_role(self, project_id: str, user_id: str) -> str | None: ...
    def create_membership(self, value: dict) -> dict: ...
    def set_member_role(self, project_id: str, user_id: str, role: str) -> dict: ...
    def delete_memberships(self, project_id: str) -> int: ...
    def get_project_settings(self, project_id: str) -> dict | None: ...
    def update_project_settings(self, project_id: str, changes: dict) -> dict: ...
    datasets: MutableMapping[str, dict]
    analyses: MutableMapping[str, dict]
    outbox: list[dict]

    def create_dataset(self, value: dict) -> dict: ...
    def update_dataset(self, key: str, changes: dict) -> dict: ...
    def delete_dataset(self, key: str) -> None: ...
    def get_analysis(self, key: str) -> dict | None: ...
    def create_analysis(self, value: dict) -> dict: ...
    def update_analysis(self, key: str, changes: dict) -> dict: ...
    def create_outbox_event(self, event: dict) -> dict: ...
    def list_pending_outbox(self, limit: int | None = None) -> list[dict]: ...
    def mark_published(self, event_key: str) -> None: ...
    def mark_publish_failed(self, event_key: str, error: str) -> None: ...
    def get_idempotency(self, key: str) -> dict | None: ...
    def create_idempotency(self, key: str, value: dict) -> dict: ...
    def list_entities(self, kind: str, project_id: str) -> list[dict]: ...
    def create_entity(self, kind: str, value: dict) -> dict: ...
    def update_entity(self, kind: str, key: str, changes: dict) -> dict: ...
    def delete_entity(self, kind: str, key: str) -> None: ...
    def delete_analysis(self, key: str) -> None: ...
    def delete_project(self, key: str) -> None: ...


class InMemoryRepository:
    def __init__(self):
        self.projects = {}
        self.memberships = {}
        self.datasets = {}
        self.analyses = {}
        self.outbox = []
        self.idempotency = {}
        self.risks, self.tasks, self.reviews, self.audits, self.deletions, self.exports = {}, {}, {}, {}, {}, {}

    def _create(self, collection, value):
        key = value['id']
        if key in collection:
            raise ValueError(f'Entity already exists: {key}')
        collection[key] = deepcopy(value)
        return deepcopy(collection[key])

    def list_projects(self): return [deepcopy(v) for v in self.projects.values()]
    def get_project(self, key): return deepcopy(self.projects.get(key))
    def create_project(self, value): return self._create(self.projects, value)

    # —— W03 成员关系:以 (project_id, user_id) 为键,读取一律 deepcopy ——
    def list_members(self, project_id):
        items = [deepcopy(v) for v in self.memberships.values() if v['project_id'] == project_id]
        items.sort(key=lambda item: item['user_id'])
        return items

    def list_user_memberships(self, user_id):
        items = [deepcopy(v) for v in self.memberships.values() if v['user_id'] == user_id]
        items.sort(key=lambda item: item['project_id'])
        return items

    def get_membership(self, project_id, user_id):
        return deepcopy(self.memberships.get((project_id, user_id)))

    def get_member_role(self, project_id, user_id):
        membership = self.get_membership(project_id, user_id)
        return membership['role'] if membership else None

    def create_membership(self, value):
        key = (value['project_id'], value['user_id'])
        if key in self.memberships:
            raise ValueError(f'Membership already exists: {value["project_id"]}/{value["user_id"]}')
        self.memberships[key] = deepcopy(value)
        return deepcopy(self.memberships[key])

    def set_member_role(self, project_id, user_id, role):
        membership = self.memberships.get((project_id, user_id))
        if membership is None:
            raise KeyError(f'{project_id}/{user_id}')
        membership['role'] = role
        return deepcopy(membership)

    def delete_memberships(self, project_id):
        """项目删除时连同成员关系一起清理(10.4 级联):留下孤儿行等于留了访问权。"""
        keys = [key for key, value in self.memberships.items() if value['project_id'] == project_id]
        for key in keys:
            del self.memberships[key]
        return len(keys)

    # —— W03 项目设置:timezone 与 settings_json 合并为一份存储值 ——
    def get_project_settings(self, project_id):
        project = self.projects.get(project_id)
        if project is None:
            return None
        stored = dict(project.get('settings_json') or {})
        if project.get('timezone') is not None:
            stored['timezone'] = project['timezone']
        return deepcopy(stored)

    def update_project_settings(self, project_id, changes):
        project = self.projects.get(project_id)
        if project is None:
            raise KeyError(project_id)
        if changes.get('timezone') is not None:
            project['timezone'] = changes['timezone']
        stored = dict(project.get('settings_json') or {})
        stored.update({key: deepcopy(value) for key, value in changes.items() if key != 'timezone'})
        project['settings_json'] = stored
        return self.get_project_settings(project_id)

    def _update(self, collection, key, changes):
        collection[key].update(deepcopy(changes))
        return deepcopy(collection[key])

    def create_dataset(self, value): return self._create(self.datasets, value)
    def update_dataset(self, key, changes): return self._update(self.datasets, key, changes)
    def delete_dataset(self, key):
        if key not in self.datasets: raise KeyError(key)
        del self.datasets[key]
    def get_analysis(self, key): return deepcopy(self.analyses.get(key))
    def create_analysis(self, value): return self._create(self.analyses, value)
    def update_analysis(self, key, changes): return self._update(self.analyses, key, changes)
    def list_entities(self, kind, project_id): return [deepcopy(v) for v in getattr(self, kind).values() if v.get('project_id') == project_id]
    def create_entity(self, kind, value): return self._create(getattr(self, kind), value)
    def update_entity(self, kind, key, changes): return self._update(getattr(self, kind), key, changes)
    def delete_entity(self, kind, key):
        collection = getattr(self, kind)
        if key not in collection: raise KeyError(key)
        del collection[key]
    def delete_analysis(self, key):
        if key not in self.analyses: raise KeyError(key)
        del self.analyses[key]
    def delete_project(self, key):
        self.projects.pop(key, None)
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
        # 重投安全:attempts 达上限才转 failed 死信,期间保持 pending 供下轮重试
        for e in self.outbox:
            if e['event_key'] == event_key:
                e['last_error'] = str(error)
                attempts = int(e.get('attempts', 0)) + 1
                e['attempts'] = attempts
                if attempts >= MAX_PUBLISH_ATTEMPTS:
                    e['status'] = 'failed'
                return

    def get_idempotency(self, key):
        return deepcopy(self.idempotency.get(key))

    def create_idempotency(self, key, value):
        if key in self.idempotency:
            raise ValueError(f'Idempotency key already exists: {key}')
        self.idempotency[key] = deepcopy(value)
        return deepcopy(value)


repository = InMemoryRepository()


def get_repository():
    if os.getenv('USE_DATABASE', '').lower() in ('1', 'true', 'yes'):
        from .sql_repository import SQLAlchemyRepository
        return SQLAlchemyRepository()
    return InMemoryRepository()
