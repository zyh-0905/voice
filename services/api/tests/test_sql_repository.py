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
    # 流水线需要仓储:反馈正文取自 feedback 实体表,风险候选也要写进项目队列
    worker = AnalysisWorker(repo.analyses, repo)
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
    monkeypatch.setattr(main, 'worker', AnalysisWorker(repo.analyses, repo))
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
        'version': 1, 'idempotency_keys': [], 'effect_status': 'NOT_EVALUATED',
    })
    task = repo.list_entities('tasks', 'p')[0]
    task, event = confirm_draft(task, 1, 'owner-1', '2026-09-20T18:00:00+08:00', '验收标准', 'demo-user')
    # 状态与事件同一次仓储调用(5.2:与任务状态更新同一事务)
    repo.save_task_transition('p', 't1', task, event)

    stored = repo.list_entities('tasks', 'p')[0]
    assert stored['state'] == 'OPEN'
    assert stored['version'] == 2
    assert stored['owner_id'] == 'owner-1'
    assert stored['acceptance'] == '验收标准'
    events = repo.list_task_events('p', 't1')
    assert len(events) == 1 and events[0]['from_state'] == 'DRAFT'
    assert events[0]['to_state'] == 'OPEN'

    stored, event = transition_task(stored, 'start', 2, 'demo-user', 'ANALYST', True, '')
    repo.save_task_transition('p', 't1', stored, event)
    assert repo.list_entities('tasks', 'p')[0]['state'] == 'IN_PROGRESS'
    assert len(repo.list_task_events('p', 't1')) == 2


def test_task_events_and_idempotency_keys_persist(repo):
    """事件走 task_events 表;幂等键仍留在任务行上(短列表,按任务读)。"""
    repo.create_entity('tasks', {
        'id': 't2', 'project_id': 'p', 'title': '任务', 'state': 'DRAFT', 'version': 1,
        'idempotency_keys': ['key-1'], 'effect_status': 'NOT_EVALUATED',
    })
    repo.append_task_event('p', 't2', {
        'id': 'e1', 'action': 'confirm', 'from_state': 'DRAFT', 'to_state': 'OPEN',
        'actor_id': 'u', 'comment_redacted': 'c', 'material_refs_json': [],
    })

    stored = repo.list_entities('tasks', 'p')[0]
    assert stored['idempotency_keys'] == ['key-1']
    events = repo.list_task_events('p', 't2')
    assert len(events) == 1
    assert events[0]['action'] == 'confirm'
    assert events[0]['from_state'] == 'DRAFT' and events[0]['to_state'] == 'OPEN'


def test_risk_review_state_persists(repo):
    """候选落 `risk_findings` 表(5.2):旧 `risks` 表少的那几列必须真的往返。

    旧表把 feedback_id / rule_id / policy_version / evidence_offsets 静默丢掉,
    SQL 仓储按列过滤时两个模式各说各话——这里正是钉住这一点的用例。
    """
    repo.save_risk_findings('p', 'run-1', [{
        'id': 'r1', 'rule_id': 'R-302', 'policy_version': 'ecommerce-v1',
        'severity': 'CRITICAL', 'reason': '候选', 'evidence_offsets': {'start': 1, 'end': 4},
    }])
    stored = repo.list_risk_findings('p')[0]
    assert stored['severity'] == 'CRITICAL'
    assert stored['review_state'] == 'pending'
    assert stored['rule_id'] == 'R-302'
    assert stored['policy_version'] == 'ecommerce-v1'
    assert stored['evidence_offsets'] == {'start': 1, 'end': 4}


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


def test_review_comparability_fields_persist(repo):
    """复盘口径四字段必须真的往返(0020 之前它们不在表里)。

    POST /reviews 的响应一直带 comparability/reasons/filters/alignment_confirmed,
    但列不在 reviews 表上——SQL 仓储按列过滤,GET 读回永远缺字段,前端复盘
    详情 `reasons.length` 直接 TypeError。内存仓储照收,全套件绿:这是
    「SQL-only 缺陷」的标准形态,只能这样钉住。
    """
    repo.create_entity('reviews', {
        'id': 'rv2', 'project_id': 'p', 'run_id': 'run', 'revision': 1,
        'topic_version_ids': ['t1'], 'before': {'n': 168, 'N': 1000},
        'after': {'n': 102, 'N': 1000},
        'metrics': {'comparable': False},
        'effect_status': 'INSUFFICIENT_DATA', 'limitations': [], 'status': 'pending',
        'comparability': 'insufficient', 'reasons': ['分母为 0'],
        'filters': {'channel': 'phone'}, 'alignment_confirmed': True,
    })
    stored = repo.list_entities('reviews', 'p')[0]
    assert stored['comparability'] == 'insufficient'
    assert stored['reasons'] == ['分母为 0']
    assert stored['filters'] == {'channel': 'phone'}
    assert stored['alignment_confirmed'] is True


# —— 迁移 0012:成员与项目设置与 InMemory 行为对齐 ——

def test_memberships_round_trip(repo):
    """W03:成员表 (project_id,user_id) 唯一;按项目/用户两向可查,角色可改。"""
    repo.create_project({'id': 'p1', 'name': '成员用例', 'timezone': 'UTC'})
    repo.create_membership({'project_id': 'p1', 'user_id': 'u1', 'role': 'OWNER', 'display_name': '一号'})
    repo.create_membership({'project_id': 'p1', 'user_id': 'u2', 'role': 'VIEWER'})
    repo.create_membership({'project_id': 'p2', 'user_id': 'u1', 'role': 'EDITOR'})

    assert [m['user_id'] for m in repo.list_members('p1')] == ['u1', 'u2']
    assert repo.list_members('p1')[0]['display_name'] == '一号'
    assert repo.get_member_role('p1', 'u1') == 'OWNER'
    assert repo.get_member_role('p1', 'missing') is None
    repo.set_member_role('p1', 'u2', 'EDITOR')
    assert repo.get_member_role('p1', 'u2') == 'EDITOR'
    assert {m['project_id'] for m in repo.list_user_memberships('u1')} == {'p1', 'p2'}

    with pytest.raises(ValueError):
        repo.create_membership({'project_id': 'p1', 'user_id': 'u1', 'role': 'OWNER'})
    with pytest.raises(KeyError):
        repo.set_member_role('p1', 'missing', 'VIEWER')


def test_project_settings_round_trip(repo):
    """W03:时区落列、其余设置落 settings_json;合并写入后读回一致。"""
    repo.create_project({'id': 'p1', 'name': '设置用例', 'timezone': 'UTC'})
    assert repo.get_project_settings('p1') == {'timezone': 'UTC'}
    assert repo.get_project_settings('missing') is None

    repo.update_project_settings('p1', {'timezone': 'Asia/Shanghai',
                                        'limits': {'max_feedback_rows': 10}, 'version': 2})
    stored = repo.get_project_settings('p1')
    assert stored['timezone'] == 'Asia/Shanghai'
    assert stored['limits'] == {'max_feedback_rows': 10}
    assert stored['version'] == 2
    # 未提交的键不丢弃
    repo.update_project_settings('p1', {'rules': {'scan_on_import': False}})
    assert repo.get_project_settings('p1')['limits'] == {'max_feedback_rows': 10}
