"""W17 集成:复盘创建保存不可变结果;不可比不输出改善结论;详情查询。"""

from app.main import app
from support.client import make_client

client = make_client()


def _create_review(**overrides):
    body = {
        'run_id': 'run_demo_001', 'revision': 1, 'topic_version_ids': ['t1'],
        'n_before': 168, 'N_before': 1000, 'n_after': 102, 'N_after': 1000,
    }
    body.update(overrides)
    return client.post('/api/v1/projects/demo-project/reviews', json=body)


def test_create_review_computes_metrics():
    response = _create_review()
    assert response.status_code == 201
    data = response.json()
    assert data['effect_status'] == 'OBSERVED_CHANGE'
    assert data['metrics']['share_delta_pp'] == -6.6
    assert data['metrics']['relative_share_change'] == -0.3929
    assert data['metrics']['comparable'] is True


def test_insufficient_review_shows_no_improvement():
    response = _create_review(n_before=0, N_before=0)
    assert response.status_code == 201
    data = response.json()
    assert data['effect_status'] == 'INSUFFICIENT_DATA'
    assert data['metrics']['comparable'] is False
    assert any('数据不足' in line for line in data['limitations'])


def test_review_detail_queryable():
    created = _create_review().json()
    detail = client.get(f"/api/v1/projects/demo-project/reviews/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()['metrics']['share_delta_pp'] == -6.6
    assert detail.json()['before'] == {'n': 168, 'N': 1000}


def test_review_detail_404():
    assert client.get('/api/v1/projects/demo-project/reviews/review-ghost').status_code == 404


def test_review_list_contains_created():
    created = _create_review().json()
    listing = client.get('/api/v1/projects/demo-project/reviews').json()
    assert any(item['id'] == created['id'] for item in listing['items'])
