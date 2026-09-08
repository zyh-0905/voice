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
