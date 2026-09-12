"""工程计划 10.4 删除:预览不写入、二次确认、级联清理、回执不含正文、OWNER 专有。"""
import pytest

from app.deletions import DeletionConflict, DeletionError, preview_deletion
from app.main import repository
from support.client import make_client

client = make_client()
PROJECT = 'demo-project'


def _project(name='删除用例项目'):
    """返回 (project_id, name);确认时必须逐字匹配 name。"""
    from uuid import uuid4
    project_id = f'del_case_{uuid4().hex[:8]}'
    repository.create_project({'id': project_id, 'name': name})
    return project_id, name


def test_preview_writes_nothing():
    project_id, name = _project('预览项目')
    repository.create_dataset({'id': 'ds_prev', 'project_id': project_id, 'name': '批次', 'rows': 3})
    repository.create_entity('tasks', {'id': 't_prev', 'project_id': project_id, 'title': '任务', 'state': 'OPEN'})

    before = len(repository.datasets)
    preview = preview_deletion(repository, project_id, 'project', project_id)
    assert preview['datasets'] == 1
    assert preview['tasks'] == 1
    # 只读:对象数量不变
    assert len(repository.datasets) == before
    assert repository.get_project(project_id) is not None


def test_preview_unknown_targets():
    with pytest.raises(DeletionError, match='project_not_found'):
        preview_deletion(repository, 'no-such-project', 'project', 'no-such-project')
    with pytest.raises(DeletionError, match='dataset_not_found'):
        preview_deletion(repository, PROJECT, 'dataset', 'ds_ghost')
    with pytest.raises(DeletionError, match='unsupported_target_type'):
        preview_deletion(repository, PROJECT, 'everything', 'x')


def test_confirm_name_mismatch_rejected_and_nothing_removed():
    project_id, name = _project('名称校验')
    repository.create_dataset({'id': 'ds_name', 'project_id': project_id, 'name': '批次', 'rows': 1})
    response = client.post(f'/api/v1/projects/{project_id}/deletions', json={
        'target_type': 'project', 'target_id': project_id, 'confirm_name': '写错的项目名',
    })
    assert response.status_code == 409
    assert response.json()['detail']['code'] == 'confirm_name_mismatch'
    assert repository.get_project(project_id) is not None


def test_project_deletion_cascades_and_leaves_no_reports():
    project_id, name = _project('级联清理')
    repository.create_dataset({'id': 'ds_casc', 'project_id': project_id, 'name': '批次', 'rows': 5})
    repository.create_analysis({
        'id': 'run_casc', 'project_id': project_id, 'dataset_ids': ['ds_casc'], 'datasets': [],
        'status': 'done', 'stage': 'completed', 'total': 5,
        'result': {'revision': 1, 'topics': [{'topic_id': 't1', 'name': '主题', 'feedback_count': 2}],
                   'evidence_by_topic': {'t1': [{'feedback_id': 'fb1'}]}, 'unassigned_count': 0},
    })
    repository.create_entity('tasks', {'id': 't_casc', 'project_id': project_id, 'title': '任务', 'state': 'OPEN'})
    repository.create_entity('reviews', {'id': 'rv_casc', 'project_id': project_id, 'status': 'pending', 'finding': 'x'})

    receipt = client.post(f'/api/v1/projects/{project_id}/deletions', json={
        'target_type': 'project', 'target_id': project_id, 'confirm_name': '级联清理',
    }).json()

    assert receipt['state'] == 'DONE'
    step_names = [step['name'] for step in receipt['steps']]
    assert step_names[:3] == ['tombstone', 'cancel_jobs', 'purge_runs']
    assert 'verify' in step_names
    # 删除后不留旧报告:项目、批次、分析、任务、复盘全部消失
    assert repository.get_project(project_id) is None
    assert all(d.get('project_id') != project_id for d in repository.datasets.values())
    assert all(a.get('project_id') != project_id for a in repository.analyses.values())
    assert repository.list_entities('tasks', project_id) == []
    assert repository.list_entities('reviews', project_id) == []


def test_dataset_deletion_invalidates_referencing_reports():
    project_id, name = _project('批次删除')
    repository.create_dataset({'id': 'ds_keep', 'project_id': project_id, 'name': '保留批次', 'rows': 1})
    repository.create_dataset({'id': 'ds_drop', 'project_id': project_id, 'name': '待删批次', 'rows': 4})
    repository.create_analysis({
        'id': 'run_drop', 'project_id': project_id, 'dataset_ids': ['ds_drop'], 'datasets': [],
        'status': 'done', 'stage': 'completed', 'total': 4,
        'result': {'revision': 1, 'topics': [{'topic_id': 'x', 'name': 't', 'feedback_count': 1}],
                   'evidence_by_topic': {}, 'unassigned_count': 0},
    })

    preview = client.post(f'/api/v1/projects/{project_id}/deletions/preview', json={
        'target_type': 'dataset', 'target_id': 'ds_drop', 'confirm_name': '待删批次',
    }).json()
    assert preview['invalidates_reports'] is True  # 确认前必须说明会失效
    assert preview['runs'] == 1

    receipt = client.post(f'/api/v1/projects/{project_id}/deletions', json={
        'target_type': 'dataset', 'target_id': 'ds_drop', 'confirm_name': '待删批次',
    }).json()
    assert receipt['state'] == 'DONE'
    assert 'ds_drop' not in repository.datasets
    # 引用该批次的报告被清理,保留批次不受影响
    assert 'run_drop' not in repository.analyses
    assert 'ds_keep' in repository.datasets


def test_running_jobs_are_cancelled_before_purge():
    project_id, name = _project('取消作业')
    repository.create_dataset({'id': 'ds_run', 'project_id': project_id, 'name': '批次', 'rows': 2})
    repository.create_analysis({
        'id': 'run_busy', 'project_id': project_id, 'dataset_ids': ['ds_run'], 'datasets': [],
        'status': 'running', 'stage': 'analyzing', 'total': 2,
        'lease_owner': 'worker-x', 'lease_expires_at': 9_999_999_999,
    })
    client.post(f'/api/v1/projects/{project_id}/deletions', json={
        'target_type': 'project', 'target_id': project_id, 'confirm_name': '取消作业',
    })
    assert 'run_busy' not in repository.analyses


def test_receipt_survives_deletion_and_contains_no_content():
    project_id, name = _project('回执查询')
    repository.create_dataset({'id': 'ds_rc', 'project_id': project_id, 'name': '批次', 'rows': 1})
    created = client.post(f'/api/v1/projects/{project_id}/deletions', json={
        'target_type': 'project', 'target_id': project_id, 'confirm_name': '回执查询',
    }).json()
    job_id = created['job_id']

    # 项目本体已清理,回执仍可查
    receipt = client.get(f'/api/v1/projects/{project_id}/deletions/{job_id}').json()
    assert receipt['state'] == 'DONE'
    assert receipt['removed']['datasets'] == 1
    # 回执不含任何正文或文件名之外的客户内容
    assert 'rows' not in receipt['removed']
    assert 'preview' not in str(receipt)


def test_viewer_cannot_delete():
    project_id, name = _project('只读拒绝')
    token = client.post('/api/v1/auth/login', json={'username': 'viewer', 'password': 'viewer'}).json()['access_token']
    client.cookies.clear()
    response = client.post(f'/api/v1/projects/{project_id}/deletions/preview',
                           json={'target_type': 'project', 'target_id': project_id, 'confirm_name': 'x'},
                           headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 403


def test_idempotent_deletion_returns_same_receipt():
    project_id, name = _project('幂等删除')
    repository.create_dataset({'id': 'ds_idem', 'project_id': project_id, 'name': '批次', 'rows': 1})
    headers = {'Idempotency-Key': f'del-{project_id}'}
    body = {'target_type': 'project', 'target_id': project_id, 'confirm_name': '幂等删除'}
    first = client.post(f'/api/v1/projects/{project_id}/deletions', json=body, headers=headers)
    second = client.post(f'/api/v1/projects/{project_id}/deletions', json=body, headers=headers)
    assert first.status_code == 202 and second.status_code == 202
    assert first.json()['job_id'] == second.json()['job_id']


def test_deletion_writes_audit_entry():
    project_id, name = _project('审计留痕')
    client.post(f'/api/v1/projects/{project_id}/deletions', json={
        'target_type': 'project', 'target_id': project_id, 'confirm_name': '审计留痕',
    })
    # 审计挂在被删项目下;项目清理后回执是最小访问路径,登记本身仍保留
    entries = repository.list_entities('audits', project_id)
    assert len(entries) == 1
    assert entries[0]['action'] == 'project.deletion'
    assert entries[0]['detail']['target_type'] == 'project'
