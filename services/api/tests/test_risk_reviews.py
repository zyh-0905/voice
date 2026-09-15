"""W14 风险裁决:确认/排除/重新审查、理由必填、版本冲突、VIEWER 拒绝、审计留痕。"""
import pytest

from app.main import repository
from support.client import make_client

client = make_client()

RISK_ID = 'risk-002'  # 演示种子中的 CRITICAL 候选


@pytest.fixture
def risk_id():
    """每个用例用独立风险记录:裁决会推进 version,共享种子会互相干扰。

    复核队列就是 `risk_findings` 表(计划 5.2)。feedback_id 留空:这是用例自造的
    候选,没有可回溯的 feedback 行;真实扫描出的候选一定带,并受复合外键约束。
    """
    from uuid import uuid4
    rid = f'risk_test_{uuid4().hex[:8]}'
    repository.save_risk_findings('demo-project', None, [{
        'id': rid, 'rule_id': 'R-TEST', 'policy_version': 'ecommerce-v1',
        'severity': 'CRITICAL', 'reason': '测试候选',
    }])
    return rid


def _review(risk_id, decision, reason='人工核验规则命中与原文一致', version=None):
    # 契约(6.5)现在要求必带 expected_version;缺省自动取当前版本——
    # 与前端行为一致(它一直发列表里的 version),不指定版本时才构造冲突场景
    body = {'decision': decision, 'reason': reason}
    body['expected_version'] = version if version is not None else _current(risk_id)['version']
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
    # 带上版本,确保测的是「目标不存在」而不是字段校验
    response = client.post('/api/v1/projects/demo-project/risks/risk-ghost/reviews',
                           json={'decision': 'confirmed', 'reason': 'x', 'expected_version': 1})
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


def test_missing_expected_version_rejected(risk_id):
    """6.5:状态操作必须带乐观锁版本;缺字段 422 而不是静默无锁写入。

    旧实现的 `is not None` 短路让漏字段等于 last-write-wins——客户端 bug
    直接变成数据丢失,而服务端看起来一切正常。
    """
    response = client.post(
        f'/api/v1/projects/demo-project/risks/{risk_id}/reviews',
        json={'decision': 'confirmed', 'reason': '缺乐观锁版本'},
    )
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'expected_version_required'


def test_repository_cas_returns_none_on_stale_version(risk_id):
    """仓储层的条件更新:expected 不匹配返回 None(端点翻译成 409)。

    旧路径是端点先读一次、再另开事务写,两个并发裁决都能通过检查;
    现在读-校验-写在同一事务(SQL 侧带行锁)。
    """
    from app.main import repository
    current = repository.get_risk_finding('demo-project', risk_id)
    version = int(current['version'])
    stale = repository.update_risk_finding(
        'demo-project', risk_id, {'review_state': 'confirmed'}, expected_version=version - 1)
    assert stale is None
    fresh = repository.update_risk_finding(
        'demo-project', risk_id, {'review_state': 'pending', 'version': version + 1},
        expected_version=version)
    assert fresh is not None and int(fresh['version']) == version + 1
