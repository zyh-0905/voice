"""W17 集成:复盘创建保存不可变结果;不可比不输出改善结论;详情查询。

请求体按计划 7.5 的冻结契约给的是**两个窗口 + filters + alignment**,不是 n/N:
口径由服务端从 run 推导(推导细节与各道闸门见 test_reviews_service.py)。
"""
from uuid import uuid4

from app.main import repository
from support.client import make_client

client = make_client()

BEFORE = {'start': '2026-08-01T00:00:00+00:00', 'end': '2026-08-31T00:00:00+00:00'}
AFTER = {'start': '2026-09-01T00:00:00+00:00', 'end': '2026-10-01T00:00:00+00:00'}


def _run_with_review_data(before_hits: int = 168, after_hits: int = 102) -> tuple[str, str]:
    """造一个已发布 revision 的 run:前窗 168/1000、后窗 102/1000(计划 8.7 黄金用例一)。"""
    project_id = f'rv_{uuid4().hex[:8]}'
    repository.create_project({'id': project_id, 'name': '复盘用例'})
    rows = [
        {'feedback_id': f'before_{i}', 'text': '物流信息一直没有更新',
         'occurred_at': f'2026-08-{1 + i % 28:02d}T00:00:00+00:00'}
        for i in range(1000)
    ] + [
        {'feedback_id': f'after_{i}', 'text': '物流信息一直没有更新',
         'occurred_at': f'2026-09-{1 + i % 28:02d}T00:00:00+00:00'}
        for i in range(1000)
    ]
    evidence = ([{'feedback_id': f'before_{i}'} for i in range(before_hits)]
                + [{'feedback_id': f'after_{i}'} for i in range(after_hits)])
    run_id = f'run_{uuid4().hex[:8]}'
    repository.create_analysis({
        'id': run_id, 'project_id': project_id, 'dataset_ids': ['ds_rv'],
        'status': 'done', 'stage': 'completed', 'total': 2000,
        'datasets': [{'id': 'ds_rv', 'project_id': project_id, 'preview': {'rows': rows}}],
        'result': {'revision': 1, 'topics': [], 'evidence_by_topic': {'t1': evidence},
                   'unassigned_count': 0, 'status': 'done'},
    })
    return project_id, run_id


def _create_review(project_id: str, run_id: str, **overrides):
    body = {
        'run_id': run_id, 'revision': 1, 'topic_version_ids': ['t1'],
        'before': BEFORE, 'after': AFTER, 'alignment_confirmed': True,
    }
    body.update(overrides)
    return client.post(f'/api/v1/projects/{project_id}/reviews', json=body)


def test_create_review_derives_metrics_from_the_run():
    project_id, run_id = _run_with_review_data()
    response = _create_review(project_id, run_id)

    assert response.status_code == 201
    data = response.json()
    assert data['effect_status'] == 'OBSERVED_CHANGE'
    assert data['metrics']['share_delta_pp'] == -6.6
    assert data['metrics']['relative_share_change'] == -0.3929
    assert data['metrics']['comparable'] is True
    # 分母与分子来自 run,不是请求里给的
    assert data['before']['n'] == 168 and data['before']['N'] == 1000
    assert data['after']['n'] == 102 and data['after']['N'] == 1000


def test_insufficient_review_shows_no_improvement():
    """目标映射未确认 → 不可比,不给任何变化结论。"""
    project_id, run_id = _run_with_review_data()
    response = _create_review(project_id, run_id, alignment_confirmed=False)

    assert response.status_code == 201
    data = response.json()
    assert data['effect_status'] == 'INSUFFICIENT_DATA'
    assert data['metrics'] is None
    assert data['comparability'] == 'insufficient'
    assert any('人工确认' in line for line in data['reasons'])


def test_unequal_windows_are_rejected_as_incomparable():
    project_id, run_id = _run_with_review_data()
    short = {'start': '2026-09-01T00:00:00+00:00', 'end': '2026-09-21T00:00:00+00:00'}
    data = _create_review(project_id, run_id, after=short).json()

    assert data['effect_status'] == 'INSUFFICIENT_DATA'
    assert any('时长不等' in line for line in data['reasons'])


def test_unknown_run_is_404():
    project_id, _ = _run_with_review_data()
    assert _create_review(project_id, 'run_ghost').status_code == 404


def test_review_detail_queryable():
    project_id, run_id = _run_with_review_data()
    created = _create_review(project_id, run_id).json()

    detail = client.get(f'/api/v1/projects/{project_id}/reviews/{created["id"]}')
    assert detail.status_code == 200
    assert detail.json()['metrics']['share_delta_pp'] == -6.6
    assert detail.json()['before']['n'] == 168 and detail.json()['before']['N'] == 1000


def test_review_detail_404():
    assert client.get('/api/v1/projects/demo-project/reviews/review-ghost').status_code == 404


def test_review_list_contains_created():
    project_id, run_id = _run_with_review_data()
    created = _create_review(project_id, run_id).json()

    listing = client.get(f'/api/v1/projects/{project_id}/reviews').json()
    assert any(item['id'] == created['id'] for item in listing['items'])
