import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.sql_repository import SQLAlchemyRepository
from app.worker import AnalysisWorker

@pytest.fixture
def repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'repository.db'}")
    repository = SQLAlchemyRepository(session_factory=sessionmaker(bind=engine))
    yield repository
    engine.dispose()

def test_explicit_writes_survive_new_sessions(repo):
    repo.create_dataset({'id': 'ds', 'project_id': 'p', 'name': 'a.csv', 'version': 1})
    repo.update_dataset('ds', {'status': 'ready', 'version': 2})
    assert repo.datasets['ds']['version'] == 2
    assert repo.datasets['ds']['status'] == 'ready'
    repo.create_analysis({'id': 'run', 'project_id': 'p', 'dataset_ids': ['ds'], 'status': 'queued'})
    repo.update_analysis('run', {'status': 'running'})
    assert repo.analyses['run']['status'] == 'running'
    assert repo.analyses['run']['dataset_ids'] == ['ds']

def test_worker_states_are_committed(repo):
    repo.analyses['run'] = {'id': 'run', 'project_id': 'p', 'dataset_ids': ['ds'], 'status': 'queued', 'total': 2}
    worker = AnalysisWorker(repo.analyses)
    worker.cancel('run')
    assert repo.analyses['run']['status'] == 'cancelled'
    worker.retry('run')
    assert repo.analyses['run']['status'] == 'queued'
    worker.run('run')
    assert repo.analyses['run']['status'] == 'done'
    assert repo.analyses['run']['progress'] == 2

def test_api_validation_and_inline_run_persist(repo, monkeypatch):
    from fastapi.testclient import TestClient
    import app.main as main
    monkeypatch.setattr(main, 'repository', repo)
    monkeypatch.setattr(main, 'datasets', repo.datasets)
    monkeypatch.setattr(main, 'analyses', repo.analyses)
    monkeypatch.setattr(main, 'worker', AnalysisWorker(repo.analyses))
    monkeypatch.setenv('RUN_WORKER_INLINE', 'true')
    client = TestClient(main.app)
    uploaded = client.post('/api/v1/projects/p/datasets', files={'file': ('a.csv', b'text\nhello\n')}, data={'consent': 'true'})
    assert uploaded.status_code == 201
    dataset_id = uploaded.json()['id']
    validated = client.post(f'/api/v1/projects/p/datasets/{dataset_id}/validate', json={})
    assert validated.status_code == 202
    assert repo.datasets[dataset_id]['status'] == 'ready'
    created = client.post('/api/v1/projects/p/analyses', json={'dataset_ids': [dataset_id]})
    assert created.status_code == 202
    assert created.json()['status'] == 'done'
    assert repo.analyses[created.json()['id']]['status'] == 'done'


# —— 迁移 0006:SQL 模式与 InMemory 行为对齐 ——

def test_task_state_machine_columns_round_trip(repo):
    from app.tasks import confirm_draft, transition_task
    repo.create_entity('tasks', {
        'id': 't1', 'project_id': 'p', 'title': '整改草稿', 'state': 'DRAFT',
        'version': 1, 'events': [], 'idempotency_keys': [], 'effect_status': 'NOT_EVALUATED',
    })
    task = repo.list_entities('tasks', 'p')[0]
    confirm_draft(task, 1, 'owner-1', '2026-09-20T18:00:00+08:00', '验收标准', 'demo-user')
    repo.update_entity('tasks', 't1', task)

    stored = repo.list_entities('tasks', 'p')[0]
    assert stored['state'] == 'OPEN'
    assert stored['version'] == 2
    assert stored['owner_id'] == 'owner-1'
    assert stored['acceptance'] == '验收标准'
    assert len(stored['events']) == 1

    transition_task(stored, 'start', 2, 'demo-user', 'ANALYST', True, '')
    repo.update_entity('tasks', 't1', stored)
    assert repo.list_entities('tasks', 'p')[0]['state'] == 'IN_PROGRESS'


def test_task_events_and_idempotency_keys_persist(repo):
    repo.create_entity('tasks', {
        'id': 't2', 'project_id': 'p', 'title': '任务', 'state': 'DRAFT', 'version': 1,
        'events': [{'action': 'confirm', 'actor': 'u', 'comment': 'c', 'state': 'OPEN'}],
        'idempotency_keys': ['key-1'], 'effect_status': 'NOT_EVALUATED',
    })
    stored = repo.list_entities('tasks', 'p')[0]
    assert stored['events'][0]['action'] == 'confirm'
    assert stored['idempotency_keys'] == ['key-1']


def test_risk_review_state_persists(repo):
    repo.create_entity('risks', {
        'id': 'r1', 'project_id': 'p', 'title': '候选', 'severity': 'CRITICAL',
        'review_state': 'pending', 'status': 'OPEN', 'rule': 'R-302',
    })
    stored = repo.list_entities('risks', 'p')[0]
    assert stored['severity'] == 'CRITICAL'
    assert stored['review_state'] == 'pending'
    assert stored['rule'] == 'R-302'


def test_review_metrics_persist(repo):
    repo.create_entity('reviews', {
        'id': 'rv1', 'project_id': 'p', 'run_id': 'run', 'revision': 1,
        'topic_version_ids': ['t1'], 'before': {'n': 168, 'N': 1000}, 'after': {'n': 102, 'N': 1000},
        'metrics': {'count_change': -66, 'share_delta_pp': -6.6, 'comparable': True},
        'effect_status': 'OBSERVED_CHANGE', 'limitations': [], 'status': 'pending', 'finding': 'x',
    })
    stored = repo.list_entities('reviews', 'p')[0]
    assert stored['revision'] == 1
    assert stored['metrics']['share_delta_pp'] == -6.6
    assert stored['before'] == {'n': 168, 'N': 1000}
    assert stored['effect_status'] == 'OBSERVED_CHANGE'
