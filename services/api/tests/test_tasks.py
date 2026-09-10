"""W15 集成:草稿不能直接验收、缺字段 422、全生命周期、幂等确认、版本冲突。"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _draft(project_id='demo-project', title='整改草稿'):
    return client.post(f'/api/v1/projects/{project_id}/tasks/drafts', json={'title': title})


def test_draft_cannot_approve_directly():
    draft = _draft().json()
    response = client.post(
        f"/api/v1/projects/demo-project/tasks/{draft['id']}/transition",
        json={'action': 'approve', 'expected_version': 1, 'comment': '试图跳过执行直接关闭', 'material_refs': []},
        headers={'Idempotency-Key': 'illegal-approve-01'},
    )
    assert response.status_code == 409
    assert response.json()['detail']['code'] == 'INVALID_TRANSITION'


def test_confirm_missing_fields_422():
    draft = _draft().json()
    response = client.post(
        f"/api/v1/projects/demo-project/tasks/{draft['id']}/confirm",
        json={'expected_version': 1, 'owner_id': '', 'due_at': '', 'acceptance': ''},
    )
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'field_required'


def test_idempotent_confirm_produces_single_event():
    draft = _draft().json()
    headers = {'Idempotency-Key': 'confirm-once-01'}
    body = {'expected_version': 1, 'owner_id': 'owner-1', 'due_at': '2026-09-20T18:00:00+08:00', 'acceptance': '标准'}
    first = client.post(f"/api/v1/projects/demo-project/tasks/{draft['id']}/confirm", json=body, headers=headers)
    second = client.post(f"/api/v1/projects/demo-project/tasks/{draft['id']}/confirm", json=body, headers=headers)
    assert first.status_code == 200 and second.status_code == 200
    detail = client.get(f"/api/v1/projects/demo-project/tasks/{draft['id']}").json()
    confirm_events = [e for e in detail['events'] if e['action'] == 'confirm']
    assert len(confirm_events) == 1
    assert detail['version'] == 2


def test_assignee_cannot_self_approve():
    draft = _draft().json()
    tid = draft['id']
    client.post(f"/api/v1/projects/demo-project/tasks/{tid}/confirm",
                json={'expected_version': 1, 'owner_id': 'demo-user', 'due_at': '2026-09-20T18:00:00+08:00', 'acceptance': '标准'})
    client.post(f"/api/v1/projects/demo-project/tasks/{tid}/transition", json={'action': 'start', 'expected_version': 2, 'comment': ''})
    client.post(f"/api/v1/projects/demo-project/tasks/{tid}/transition", json={'action': 'submit', 'expected_version': 3, 'comment': ''})
    # 负责人(demo-user)试图自验收 → 409
    response = client.post(f"/api/v1/projects/demo-project/tasks/{tid}/transition",
                           json={'action': 'approve', 'expected_version': 4, 'comment': ''})
    assert response.status_code == 409
    assert response.json()['detail']['code'] == 'INVALID_TRANSITION'


def test_full_lifecycle_with_owner_and_reviewer():
    draft = _draft().json()
    tid = draft['id']
    client.post(f"/api/v1/projects/demo-project/tasks/{tid}/confirm",
                json={'expected_version': 1, 'owner_id': 'owner-1', 'due_at': '2026-09-20T18:00:00+08:00', 'acceptance': '标准'})
    client.post(f"/api/v1/projects/demo-project/tasks/{tid}/transition", json={'action': 'start', 'expected_version': 2, 'comment': ''})
    client.post(f"/api/v1/projects/demo-project/tasks/{tid}/transition", json={'action': 'submit', 'expected_version': 3, 'comment': ''})
    response = client.post(f"/api/v1/projects/demo-project/tasks/{tid}/transition",
                           json={'action': 'approve', 'expected_version': 4, 'comment': '验收通过'})
    assert response.status_code == 200
    assert response.json()['state'] == 'CLOSED'
    assert response.json()['effect_status'] == 'NOT_EVALUATED'


def test_version_conflict_409():
    draft = _draft().json()
    tid = draft['id']
    client.post(f"/api/v1/projects/demo-project/tasks/{tid}/confirm",
                json={'expected_version': 1, 'owner_id': 'owner-1', 'due_at': '2026-09-20T18:00:00+08:00', 'acceptance': '标准'})
    # 用过期版本再 start → 409
    response = client.post(f"/api/v1/projects/demo-project/tasks/{tid}/transition",
                           json={'action': 'start', 'expected_version': 1, 'comment': ''})
    assert response.status_code == 409
    assert response.json()['detail']['code'] == 'VERSION_CONFLICT'
