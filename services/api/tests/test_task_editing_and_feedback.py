"""7.5 任务编辑(草稿/正式可改字段不同)与证据源查询(脱敏全文 + 分块 + 项目隔离)。"""
import json
from uuid import uuid4

import pytest

from app.feedback import FeedbackNotFound, find_feedback
from app.main import repository
from support.client import make_client

client = make_client()


def _draft(project_id='demo-project'):
    return client.post(f'/api/v1/projects/{project_id}/tasks/drafts', json={'title': '待编辑草稿'}).json()


def _patch(task_id, project_id='demo-project', **body):
    return client.patch(f'/api/v1/projects/{project_id}/tasks/{task_id}', json=body)


# —— PATCH 任务 ——

def test_draft_can_edit_draft_fields():
    task = _draft()
    response = _patch(task['id'], expected_version=1, title='改过的标题', source='人工复核', priority='HIGH')
    assert response.status_code == 200
    body = response.json()
    assert body['title'] == '改过的标题'
    assert body['source'] == '人工复核'
    assert body['version'] == 2


def test_draft_cannot_edit_formal_fields():
    task = _draft()
    response = _patch(task['id'], expected_version=1, due_at='2026-10-01')
    assert response.status_code == 422
    detail = response.json()['detail']
    assert detail['code'] == 'field_not_editable'
    assert detail['fields'] == ['due_at']
    assert detail['state'] == 'DRAFT'


def test_formal_task_cannot_edit_title_but_can_edit_schedule():
    task = _draft()
    client.post(f"/api/v1/projects/demo-project/tasks/{task['id']}/confirm", json={
        'expected_version': 1, 'owner_id': 'owner-1', 'due_at': '2026-09-20T18:00:00+08:00', 'acceptance': '标准',
    })
    # 正式任务仍可调整期限与验收标准
    ok = _patch(task['id'], expected_version=2, due_at='2026-09-25T18:00:00+08:00', acceptance='新标准')
    assert ok.status_code == 200
    assert ok.json()['due_at'].startswith('2026-09-25')
    # 标题不在正式任务的可改清单内
    rejected = _patch(task['id'], expected_version=3, title='不该改的名字')
    assert rejected.status_code == 422
    assert rejected.json()['detail']['fields'] == ['title']


def test_state_cannot_be_changed_through_patch():
    task = _draft()
    # state 不在可改字段里,会被当作非法字段拒绝(状态必须走状态机端点)
    response = _patch(task['id'], expected_version=1, state='CLOSED')
    assert response.status_code == 422


def test_patch_version_conflict_409():
    task = _draft()
    client.patch(f"/api/v1/projects/demo-project/tasks/{task['id']}", json={'expected_version': 1, 'title': '第一次'})
    stale = _patch(task['id'], expected_version=1, title='第二次')
    assert stale.status_code == 409
    assert stale.json()['detail']['code'] == 'VERSION_CONFLICT'


def test_patch_requires_at_least_one_field():
    task = _draft()
    assert _patch(task['id'], expected_version=1).status_code == 422


def test_patch_unknown_task_404():
    assert _patch('task-ghost', expected_version=1, title='x').status_code == 404


# —— 证据源 ——

def _dataset_with_feedback(project_id, dataset_id, rows):
    repository.create_project({'id': project_id, 'name': f'项目 {project_id}'})
    repository.create_dataset({
        'id': dataset_id, 'project_id': project_id, 'name': '批次', 'rows': len(rows),
        'preview': {'rows': rows},
    })


def test_feedback_returns_redacted_text_row_and_segments():
    project_id = f'fb_case_{uuid4().hex[:6]}'
    _dataset_with_feedback(project_id, f'ds_{project_id}', [
        {'feedback_id': 'fb_target', 'text': '物流很慢。', 'channel': '在线客服',
         'occurred_at': '2026-08-26T09:12:00+08:00'},
    ])
    response = client.get(f'/api/v1/projects/{project_id}/feedback/fb_target')
    assert response.status_code == 200
    body = response.json()
    assert body['feedback_id'] == 'fb_target'
    assert body['source_row'] == 0
    assert body['channel'] == '在线客服'
    assert body['occurred_at'].startswith('2026-08-26')
    assert '物流很慢' in body['text']
    # 分块来自 W07 的分块器,offset 可复原原文
    assert body['segments']
    for segment in body['segments']:
        assert body['text'][segment['start']:segment['end']] == segment['text']
    # 不返回原始文件
    assert 'file' not in body and 'raw' not in body


def test_feedback_row_index_is_reported_for_generated_ids():
    project_id = f'fb_gen_{uuid4().hex[:6]}'
    _dataset_with_feedback(project_id, f'ds_{project_id}', [
        {'text': '第一条'}, {'text': '第二条'},
    ])
    # 生成 id 的规范形状:fb_{dataset_id}_{index}(与流水线一致)
    body = client.get(f'/api/v1/projects/{project_id}/feedback/fb_ds_{project_id}_1').json()
    assert body['source_row'] == 1
    assert body['text'] == '第二条'


def test_feedback_is_project_scoped():
    owner = f'fb_own_{uuid4().hex[:6]}'
    other = f'fb_oth_{uuid4().hex[:6]}'
    _dataset_with_feedback(owner, f'ds_{owner}', [{'feedback_id': 'fb_secret', 'text': '本项目反馈'}])
    _dataset_with_feedback(other, f'ds_{other}', [{'feedback_id': 'fb_foreign', 'text': '外项目反馈'}])

    # 本项目可查
    assert client.get(f'/api/v1/projects/{owner}/feedback/fb_secret').status_code == 200
    # 用别人的项目路径查同一 id → 404(不暴露跨项目数据)
    assert client.get(f'/api/v1/projects/{other}/feedback/fb_secret').status_code == 404
    # 外项目反馈在本项目下不可见
    assert client.get(f'/api/v1/projects/{owner}/feedback/fb_foreign').status_code == 404


def test_feedback_not_found_404():
    with pytest.raises(FeedbackNotFound):
        find_feedback(repository, 'demo-project', 'fb_ghost')
    assert client.get('/api/v1/projects/demo-project/feedback/fb_ghost').status_code == 404


def test_feedback_never_returns_raw_pii():
    """仓储存的是解析后的原始行(parse_csv_text 只对 stats 脱敏),端点必须自建脱敏边界。

    与 GET /exports/redacted.csv 的既有做法一致:出站前再脱敏一次,避免旧解析器
    写入的裸数据从这个端点漏出。
    """
    project_id = f'fb_pii_{uuid4().hex[:6]}'
    _dataset_with_feedback(project_id, f'ds_{project_id}', [
        {'feedback_id': 'fb_pii', 'email': 'real-person@example.com',
         'phone': '13812345678', 'order': 'ORD-123456', 'note': '物流很慢'},
    ])
    response = client.get(f'/api/v1/projects/{project_id}/feedback/fb_pii')
    assert response.status_code == 200
    body = response.json()

    blob = json.dumps(body, ensure_ascii=False)
    assert 'real-person@example.com' not in blob, '端点不能返回未脱敏邮箱'
    assert '13812345678' not in blob, '端点不能返回未脱敏手机号'
    assert 'ORD-123456' not in blob, '端点不能返回未脱敏订单号'
    assert '<EMAIL_REDACTED>' in body['text']
    assert '<PHONE_REDACTED>' in body['text']
    # 脱敏后分块 offset 仍可逐字复原
    assert body['segments']
    for segment in body['segments']:
        assert body['text'][segment['start']:segment['end']] == segment['text']
