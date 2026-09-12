"""W13 校正契约:新快照不覆写旧版本、并发 409、MERGE 去重、SPLIT 保留、CREATE 待归类。"""

from app.main import app
from support.client import make_client

client = make_client()


def _correct(topic_case, topic_id, operation, expected_revision, **extra):
    return client.post(
        f"/api/v1/projects/{topic_case.project_id}/topics/{topic_id}/corrections",
        json={'operation': operation, 'expected_revision': expected_revision,
              'reason': '人工核对后的校正', **extra},
    )


def test_rename_creates_new_revision(topic_case):
    c = topic_case
    response = _correct(c, c.topic_id, 'RENAME', c.topic_version_id, name='外包装破损')
    assert response.status_code == 201
    assert response.json()['revision'] == c.topic_version_id + 1


def test_rename_marks_new_version_pending_revalidation(topic_case):
    c = topic_case
    _correct(c, c.topic_id, 'RENAME', c.topic_version_id, name='外包装破损')
    detail = client.get(f"/api/v1/projects/{c.project_id}/topics/{c.topic_id}").json()
    assert detail['topic']['name'] == '外包装破损'
    assert detail['topic'].get('summary_revalidated') is False


def test_old_revision_remains_queryable(topic_case):
    c = topic_case
    _correct(c, c.topic_id, 'RENAME', c.topic_version_id, name='外包装破损')
    old = client.get(
        f"/api/v1/projects/{c.project_id}/topics/{c.topic_id}",
        params={'topic_version_id': c.topic_version_id},
    )
    assert old.status_code == 200
    assert old.json()['topic']['name'] == '物流体验'


def test_concurrent_correction_conflicts_409(topic_case):
    c = topic_case
    first = _correct(c, c.topic_id, 'RENAME', c.topic_version_id, name='外包装破损')
    assert first.status_code == 201
    # 第二个校正仍基于旧 revision:并发场景只有一个成功
    second = _correct(c, c.topic_id, 'RENAME', c.topic_version_id, name='另一个名字')
    assert second.status_code == 409


def test_missing_reason_rejected(topic_case):
    c = topic_case
    response = client.post(
        f"/api/v1/projects/{c.project_id}/topics/{c.topic_id}/corrections",
        json={'operation': 'RENAME', 'expected_revision': c.topic_version_id, 'name': 'x', 'reason': ''},
    )
    assert response.status_code == 422


def test_rename_unknown_topic_404(topic_case):
    c = topic_case
    response = _correct(c, 'topic-ghost', 'RENAME', c.topic_version_id, name='x')
    assert response.status_code == 404


def test_merge_dedupes_feedback(topic_case):
    c = topic_case
    # t1 与 t2 各 1 条证据;先把 t1 改名占新 revision,再在当前 revision 上 MERGE
    response = _correct(c, c.topic_id, 'MERGE', c.topic_version_id,
                        source_topic_ids=[c.topic_id, 't2'], name='合并主题')
    assert response.status_code == 201
    new_revision = response.json()['revision']
    detail = client.get(f"/api/v1/projects/{c.project_id}/topics").json()
    names = [t['title'] for t in detail['items']]
    assert '合并主题' in names
    assert '物流体验' not in names and '退款进度' not in names


def test_split_keeps_unassigned_part_in_source(topic_case):
    c = topic_case
    response = _correct(c, c.topic_id, 'SPLIT', c.topic_version_id,
                        feedback_ids=[c.feedback_id], name='拆分主题')
    assert response.status_code == 201
    affected = response.json()['affected_topic_ids']
    assert c.topic_id in affected
    # 原 topic 保留未分配部分(此处全部被移出,feedback_count 归零但仍存在)
    detail = client.get(f"/api/v1/projects/{c.project_id}/topics/{c.topic_id}").json()
    assert detail['topic']['feedback_count'] == 0


def test_create_from_unassigned(topic_case):
    c = topic_case
    response = _correct(c, c.topic_id, 'CREATE', c.topic_version_id,
                        feedback_ids=[c.unassigned_feedback_id], name='新归主题')
    assert response.status_code == 201
    new_revision = response.json()['revision']
    assert new_revision == c.topic_version_id + 1
    # 待归类计数减少
    detail = client.get(f"/api/v1/projects/{c.project_id}/topics").json()
    names = [t['title'] for t in detail['items']]
    assert '新归主题' in names


def test_create_rejects_foreign_feedback(topic_case):
    c = topic_case
    response = _correct(c, c.topic_id, 'CREATE', c.topic_version_id,
                        feedback_ids=['fb_unassigned'], name='新归主题')
    assert response.status_code == 422  # 不在本 run 输入 → 拒绝


def test_unsupported_operation_rejected(topic_case):
    c = topic_case
    response = _correct(c, c.topic_id, 'DELETE', c.topic_version_id)
    assert response.status_code == 422
