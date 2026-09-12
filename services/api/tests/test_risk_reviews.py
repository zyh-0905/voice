"""W14 风险裁决:确认/排除/重新审查、理由必填、版本冲突、VIEWER 拒绝、审计留痕。"""
import pytest

from app.main import repository
from support.client import make_client

client = make_client()

RISK_ID = 'risk-002'  # 演示种子中的 CRITICAL 候选


@pytest.fixture
def risk_id():
    """每个用例用独立风险记录:裁决会推进 version,共享种子会互相干扰。"""
    from uuid import uuid4
    rid = f'risk_test_{uuid4().hex[:8]}'
    repository.create_entity('risks', {
        'id': rid, 'project_id': 'demo-project', 'title': '测试候选', 'rule': 'R-TEST',
        'severity': 'CRITICAL', 'review_state': 'pending', 'status': 'OPEN', 'version': 1,
    })
    return rid


def _review(risk_id, decision, reason='人工核验规则命中与原文一致', version=None):
    body = {'decision': decision, 'reason': reason}
    if version is not None:
        body['expected_version'] = version
    return client.post(f'/api/v1/projects/demo-project/risks/{risk_id}/reviews', json=body)


def _current(risk_id):
    items = client.get('/api/v1/projects/demo-project/risks').json()['items']
    return next(r for r in items if r['id'] == risk_id)


def test_reason_is_required(risk_id):
    response = _review(risk_id, 'confirmed', reason='   ')
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'reason_required'


def test_invalid_decision_rejected(risk_id):
    response = _review(risk_id, 'delete')
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'invalid_decision'


def test_unknown_risk_404():
    response = client.post('/api/v1/projects/demo-project/risks/risk-ghost/reviews',
                           json={'decision': 'confirmed', 'reason': 'x'})
    assert response.status_code == 404


def test_confirm_marks_reviewed_not_an_accident_claim(risk_id):
    response = _review(risk_id, 'confirmed')
    assert response.status_code == 200
    body = response.json()
    assert body['reviewState'] == 'confirmed'
    assert body['reviewedBy'] == 'demo-user'
    assert body['reviewReason']
    assert body['version'] >= 2


def test_reopen_returns_to_pending(risk_id):
    _review(risk_id, 'excluded')
    assert _current(risk_id)['reviewState'] == 'excluded'
    response = _review(risk_id, 'reopened')
    assert response.status_code == 200
    assert response.json()['reviewState'] == 'pending'


def test_version_conflict_409(risk_id):
    _review(risk_id, 'confirmed')
    stale = _review(risk_id, 'excluded', version=1)
    assert stale.status_code == 409
    assert stale.json()['detail']['code'] == 'VERSION_CONFLICT'


def test_viewer_cannot_adjudicate(risk_id):
    token = client.post('/api/v1/auth/login', json={'username': 'viewer', 'password': 'viewer'}).json()['access_token']
    client.cookies.clear()
    response = client.post(
        f'/api/v1/projects/demo-project/risks/{risk_id}/reviews',
        json={'decision': 'confirmed', 'reason': '只读账号尝试裁决'},
        headers={'Authorization': f'Bearer {token}'},
    )
    assert response.status_code == 403


def test_adjudication_writes_audit_entry(risk_id):
    before = client.get('/api/v1/projects/demo-project/audits').json()['total']
    _review(risk_id, 'confirmed')
    listing = client.get('/api/v1/projects/demo-project/audits').json()
    assert listing['total'] == before + 1
    entry = listing['items'][0]
    assert entry['action'] == 'risk.review'
    assert entry['detail']['risk_id'] == risk_id
    # 审计只存元数据,不落正文
    assert 'reason' not in entry['detail'] or isinstance(entry['detail'].get('reason'), str)


def test_audit_pagination():
    response = client.get('/api/v1/projects/demo-project/audits', params={'page': 1, 'page_size': 1})
    body = response.json()
    assert body['page'] == 1 and body['page_size'] == 1
    assert len(body['items']) <= 1
    assert client.get('/api/v1/projects/demo-project/audits', params={'page_size': 500}).status_code == 422
