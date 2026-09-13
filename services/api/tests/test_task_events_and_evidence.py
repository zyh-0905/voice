"""工程计划 5.2:`task_events` 与 `task_evidence`。

两者此前都有替代品,而两个替代品都丢掉了计划要的语义:

- 事件是 `tasks.events` 的 JSON 数组——不可按时间线查询,也没记 `from_state`;
- 任务是**没有**来源快照的,只有一个 `source` 字符串。那不是快照而是指针:源数据
  被删之后它指向不存在的东西,而 §10.4 要求「数据集删除会使…任务证据失效/被清理」。
"""
from uuid import uuid4

import pytest

import app.main as main
from app.main import repository
from app.tasks import DRAFT, OPEN, transition_task
from support.client import make_client

client = make_client()


def _project(prefix='te'):
    project_id = f'{prefix}_{uuid4().hex[:8]}'
    created = client.post('/api/v1/projects',
                          json={'name': f'测试项目 {project_id}', 'timezone': 'Asia/Shanghai'})
    assert created.status_code == 201, created.text
    return created.json()['id']


def _seed_feedback(project_id, dataset_id='ds_te', contents=('重复扣款了两次',)):
    rows = [{'id': f'fb_{dataset_id}_{i}', 'event_key': f'k-{project_id}-{i}',
             'content_redacted': text, 'content_hash': f'h{i}', 'source_row': i,
             'channel': 'unknown', 'product': 'unknown', 'time_quality': 'missing',
             'identity_quality': 'source_id', 'redaction_version': 'v1'}
            for i, text in enumerate(contents)]
    repository.save_feedback_rows(project_id, dataset_id, rows)
    return [row['id'] for row in rows]


# —— 事件:同一事务 + from→to ——

def test_transition_writes_state_and_event_together():
    """5.2:事件与任务状态更新**同一事务**。

    分开写会留下「状态变了但没有对应事件」的任务,而时间线正是用来回答
    「这个状态是谁改的」。
    """
    project_id = _project('both')
    task = {'id': 't_both', 'project_id': project_id, 'title': '任务', 'state': DRAFT,
            'version': 1, 'idempotency_keys': []}
    repository.create_entity('tasks', task)

    current = repository.list_entities('tasks', project_id)[0]
    updated, event = transition_task(current, 'confirm', 1, 'u1', 'ANALYST', False, '确认')
    repository.save_task_transition(project_id, 't_both', updated, event)

    events = repository.list_task_events(project_id, 't_both')
    assert len(events) == 1
    assert events[0]['from_state'] == DRAFT
    assert events[0]['to_state'] == OPEN
    assert events[0]['actor_id'] == 'u1'


def test_event_records_the_previous_state():
    """`from_state` 是 JSON 版本里没有的:看着时间线能猜改之前是什么,但猜不出。"""
    project_id = _project('from')
    task = {'id': 't_from', 'project_id': project_id, 'title': '任务', 'state': DRAFT,
            'version': 1, 'idempotency_keys': []}
    repository.create_entity('tasks', task)

    current = repository.list_entities('tasks', project_id)[0]
    updated, event = transition_task(current, 'confirm', 1, 'u', 'ANALYST', False, '')
    repository.save_task_transition(project_id, 't_from', updated, event)
    current = repository.list_entities('tasks', project_id)[0]
    updated, event = transition_task(current, 'start', 2, 'u', 'ANALYST', True, '')
    repository.save_task_transition(project_id, 't_from', updated, event)

    states = [(e['from_state'], e['to_state']) for e in repository.list_task_events(project_id, 't_from')]
    assert states == [(DRAFT, OPEN), (OPEN, 'IN_PROGRESS')]


def test_comment_is_redacted_before_it_lands():
    """评论是自由文本,用户可能顺手贴订单号、手机号;而事件表要长期保留。"""
    project_id = _project('redact')
    task = {'id': 't_r', 'project_id': project_id, 'title': '任务', 'state': DRAFT,
            'version': 1, 'idempotency_keys': []}
    repository.create_entity('tasks', task)

    current = repository.list_entities('tasks', project_id)[0]
    updated, event = transition_task(current, 'confirm', 1, 'u', 'ANALYST', False,
                                     '联系 13812345678 或 a@example.com')
    repository.save_task_transition(project_id, 't_r', updated, event)

    comment = repository.list_task_events(project_id, 't_r')[0]['comment_redacted']
    assert '13812345678' not in comment and 'a@example.com' not in comment
    assert '<PHONE_REDACTED>' in comment and '<EMAIL_REDACTED>' in comment


def test_task_detail_returns_events_from_the_table():
    project_id = _project('detail')
    task = {'id': 't_d', 'project_id': project_id, 'title': '任务', 'state': DRAFT,
            'version': 1, 'idempotency_keys': []}
    repository.create_entity('tasks', task)
    current = repository.list_entities('tasks', project_id)[0]
    updated, event = transition_task(current, 'confirm', 1, 'u', 'ANALYST', False, '')
    repository.save_task_transition(project_id, 't_d', updated, event)

    body = client.get(f'/api/v1/projects/{project_id}/tasks/t_d').json()
    assert [e['to_state'] for e in body['events']] == [OPEN]
    assert body['events'][0]['from_state'] == DRAFT


# —— 来源快照:固定、可清理 ——

def test_draft_snapshots_the_source_topic_evidence():
    """5.2:来源快照是**复制**,不是「按主题 id 去查」——后者会随主题新版本变化。"""
    project_id = _project('snap')
    feedback_id = _seed_feedback(project_id)[0]
    repository.save_revision(project_id, 'run_s', {
        'revision': {'id': 'rev_s_1', 'project_id': project_id, 'run_id': 'run_s', 'revision': 1,
                     'topic_manifest_json': {'t1': 'tv_run_s_t1_1'}, 'unassigned_count': 0,
                     'reason': None, 'actor_id': None},
        'topics': [{'project_id': project_id, 'run_id': 'run_s', 'id': 'tp_run_s_t1',
                    'topic_id': 't1', 'current_version_id': 'tv_run_s_t1_1', 'state': 'ACTIVE'}],
        'versions': [{'id': 'tv_run_s_t1_1', 'project_id': project_id, 'run_id': 'run_s',
                      'topic_id': 't1', 'topic_row_id': 'tp_run_s_t1', 'version': 1, 'revision': 1,
                      'name': '重复扣款', 'summary': '', 'severity': 'high', 'department': None,
                      'claims': [], 'suggested_action': None, 'needs_review': True,
                      'summary_revalidated': True, 'limitations': [], 'origin': None}],
        'evidence': [{'id': 'te_1', 'project_id': project_id, 'topic_version_id': 'tv_run_s_t1_1',
                      'feedback_id': feedback_id, 'segment_id': '', 'source_row': 0,
                      'quote': '重复扣款', 'quote_start': 0, 'quote_end': 4,
                      'similarity': None, 'is_representative': True}],
    })

    created = client.post(f'/api/v1/projects/{project_id}/tasks/drafts',
                          json={'title': '核查重复扣款', 'source_topic_version_id': 'tv_run_s_t1_1'})
    assert created.status_code == 201, created.text
    task_id = created.json()['id']

    snapshot = repository.list_task_evidence(project_id, task_id)
    assert len(snapshot) == 1
    assert snapshot[0]['feedback_id'] == feedback_id
    assert snapshot[0]['quote_redacted'] == '重复扣款'


def test_deleting_the_batch_purges_task_evidence(schema_session_factory):
    """10.4:数据集删除会使任务证据失效/被清理。

    没有 task_evidence 表时这条要求没有可执行的对象——任务只有一个指向主题版本的
    字符串,源被删之后它悬空,却没有任何东西知道该清理它。
    """
    from app.deletions import execute_deletion
    from app.sql_repository import SQLAlchemyRepository

    repo = SQLAlchemyRepository(create_schema=False, session_factory=schema_session_factory)
    project_id = _project('purge')
    repo.create_project({'id': project_id, 'name': '清理用例'})
    repo.save_feedback_rows(project_id, 'ds_p', [
        {'id': 'fb_p_0', 'event_key': 'k-p', 'content_redacted': '重复扣款了两次',
         'content_hash': 'hp', 'source_row': 0, 'channel': 'unknown', 'product': 'unknown',
         'time_quality': 'missing', 'identity_quality': 'source_id', 'redaction_version': 'v1'}])
    repo.create_dataset({'id': 'ds_p', 'project_id': project_id, 'name': '批次', 'rows': 1,
                         'preview': {'rows': []}})
    repo.create_entity('tasks', {'id': 't_p', 'project_id': project_id, 'title': '任务',
                                 'state': 'DRAFT', 'version': 1, 'idempotency_keys': []})
    repo.save_task_evidence(project_id, 't_p', [
        {'id': 'tve_1', 'feedback_id': 'fb_p_0', 'topic_version_id': 'tv_x',
         'quote_redacted': '重复扣款'}])

    execute_deletion(repo, project_id, 'dataset', 'ds_p', '批次', f'job_{uuid4().hex[:8]}', 'demo-user')

    assert repo.list_task_evidence(project_id, 't_p') == []
    assert repo.list_feedback(project_id, ['ds_p']) == []


def test_project_deletion_clears_the_timeline(schema_session_factory):
    """任务被删之后事件指向不存在的任务——时间线必须随项目走。"""
    from app.deletions import execute_deletion
    from app.sql_repository import SQLAlchemyRepository

    repo = SQLAlchemyRepository(create_schema=False, session_factory=schema_session_factory)
    project_id = _project('purgeproj')
    repo.create_project({'id': project_id, 'name': '整项目'})
    repo.create_entity('tasks', {'id': 't_q', 'project_id': project_id, 'title': '任务',
                                 'state': 'DRAFT', 'version': 1, 'idempotency_keys': []})
    repo.append_task_event(project_id, 't_q', {
        'id': 'e_q', 'action': 'confirm', 'from_state': DRAFT, 'to_state': OPEN,
        'actor_id': 'u', 'comment_redacted': '', 'material_refs_json': []})

    execute_deletion(repo, project_id, 'project', project_id, '整项目', f'job_{uuid4().hex[:8]}', 'demo-user')

    assert repo.list_task_events(project_id, 't_q') == []


def test_source_pointer_and_snapshot_are_separate_fields():
    """`source` 是指针,`evidence_snapshot` 才是快照——此前两者共用一个骗人的字段名。"""
    project_id = _project('fields')
    task = {'id': 't_f', 'project_id': project_id, 'title': '手工任务', 'state': DRAFT,
            'version': 1, 'source': 'manual', 'idempotency_keys': []}
    repository.create_entity('tasks', task)

    body = client.get(f'/api/v1/projects/{project_id}/tasks/t_f').json()
    assert body['source'] == 'manual'
    assert body['evidence_snapshot'] == []
