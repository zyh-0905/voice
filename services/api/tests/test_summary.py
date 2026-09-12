"""W12 聚合契约:scope 分组、去重计数、筛选范围隔离、逾期边界、无 run 语义。"""
from datetime import datetime, timedelta, timezone

import pytest

from app.main import app
from app.summary import build_summary
from support.client import make_client

client = make_client()

AS_OF = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)


def _run(project_id='p', run_id='run-1', revision=1, rows=None, topics=2, findings=None):
    return {
        'id': run_id, 'project_id': project_id, 'status': 'done', 'stage': 'completed',
        'datasets': [{'id': 'ds', 'preview': {'rows': rows if rows is not None else [{'text': 'a'}, {'text': 'b'}]}}],
        'result': {
            'revision': revision,
            'topics': [{'topic_id': f't{i}', 'name': f'主题{i}', 'feedback_count': 1} for i in range(topics)],
            'evidence_by_topic': {}, 'unassigned_count': 0,
        },
        'risk_findings': findings or [],
    }


def _task(state, due_at=None, project_id='p'):
    return {'id': f'task-{state}-{due_at}', 'project_id': project_id, 'state': state, 'due_at': due_at}


def test_summary_exposes_scopes():
    summary = build_summary([_run()], [_task('OPEN')], 'p', now=AS_OF)
    assert summary['insight_metrics']['scope'] == 'selected_analysis'
    assert summary['action_metrics']['scope'] == 'project_all_runs'
    assert summary['action_metrics']['overdue_task_count'] <= summary['action_metrics']['active_task_count']


def test_denominator_matches_valid_feedback_count():
    summary = build_summary([_run(rows=[{'text': 'a'}, {'text': 'b'}, {'text': 'c'}])], [], 'p', now=AS_OF)
    assert summary['denominator'] == summary['insight_metrics']['valid_feedback_count'] == 3


def test_topic_count_from_published_revision():
    summary = build_summary([_run(topics=5)], [], 'p', now=AS_OF)
    assert summary['insight_metrics']['topic_count'] == 5


def test_pending_risk_counts_distinct_feedback_all_severities():
    findings = [
        {'feedback_id': 'fb1', 'rule_id': 'r1', 'severity': 'HIGH', 'review_state': 'PENDING'},
        {'feedback_id': 'fb1', 'rule_id': 'r2', 'severity': 'CRITICAL', 'review_state': 'PENDING'},
        {'feedback_id': 'fb2', 'rule_id': 'r1', 'severity': 'LOW', 'review_state': 'PENDING'},
        {'feedback_id': 'fb3', 'rule_id': 'r1', 'severity': 'HIGH', 'review_state': 'CONFIRMED'},
    ]
    summary = build_summary([_run(findings=findings)], [], 'p', now=AS_OF)
    # 同一反馈命中两条规则只计 1;已确认的不计入
    assert summary['insight_metrics']['pending_risk_feedback_count'] == 2


def test_filters_only_affect_insight_metrics():
    tasks = [_task('OPEN'), _task('IN_PROGRESS', due_at='2026-09-01T00:00:00+00:00')]
    unfiltered = build_summary([_run()], tasks, 'p', now=AS_OF)
    filtered = build_summary([_run()], tasks, 'p', filters={'channel': 'phone'}, now=AS_OF)
    # 无 channel 字段的行不被筛掉,但 action 指标在任何筛选下都不变
    assert filtered['action_metrics'] == unfiltered['action_metrics']
    assert filtered['action_metrics']['active_task_count'] == 2
    assert filtered['action_metrics']['overdue_task_count'] == 1


def test_channel_filter_narrows_insight_denominator():
    rows = [{'text': 'a', 'channel': 'phone'}, {'text': 'b', 'channel': 'chat'}]
    summary = build_summary([_run(rows=rows)], [], 'p', filters={'channel': 'phone'}, now=AS_OF)
    assert summary['denominator'] == 1


def test_time_window_is_half_open():
    rows = [
        {'text': 'before', 'occurred_at': '2026-08-31T23:59:59+00:00'},
        {'text': 'at-start', 'occurred_at': '2026-09-01T00:00:00+00:00'},
        {'text': 'at-end', 'occurred_at': '2026-09-02T00:00:00+00:00'},
    ]
    summary = build_summary([_run(rows=rows)], [], 'p',
                            filters={'start': '2026-09-01T00:00:00+00:00', 'end': '2026-09-02T00:00:00+00:00'},
                            now=AS_OF)
    assert summary['denominator'] == 1  # [start, end)


def test_overdue_boundary_due_equals_as_of_is_not_overdue():
    due = AS_OF.isoformat()
    just_before = (AS_OF - timedelta(seconds=1)).isoformat()
    summary = build_summary([_run()], [_task('OPEN', due_at=due), _task('OPEN', due_at=just_before)], 'p', now=AS_OF)
    assert summary['action_metrics']['active_task_count'] == 2
    assert summary['action_metrics']['overdue_task_count'] == 1


def test_closed_states_excluded_from_active():
    tasks = [_task('DRAFT'), _task('CLOSED'), _task('CANCELLED'), _task('PENDING_REVIEW')]
    summary = build_summary([_run()], tasks, 'p', now=AS_OF)
    assert summary['action_metrics']['active_task_count'] == 1


def test_no_published_run_returns_null_insight_but_readable_tasks():
    run = {'id': 'run-q', 'project_id': 'p', 'status': 'queued', 'datasets': [],
           'result': {}, 'risk_findings': []}
    summary = build_summary([run], [_task('OPEN')], 'p', now=AS_OF)
    assert summary['run_id'] is None and summary['revision'] is None
    assert summary['insight_metrics']['valid_feedback_count'] is None
    assert summary['insight_metrics']['topic_count'] is None
    assert summary['insight_metrics']['pending_risk_feedback_count'] is None
    assert summary['denominator'] is None
    assert summary['action_metrics']['active_task_count'] == 1


def test_revision_without_run_id_rejected():
    with pytest.raises(Exception) as exc:
        build_summary([_run()], [], 'p', revision=1, now=AS_OF)
    assert getattr(exc.value, 'status_code', None) == 422


def test_foreign_run_not_found():
    with pytest.raises(Exception) as exc:
        build_summary([_run(project_id='other')], [], 'p', run_id='run-1', now=AS_OF)
    assert getattr(exc.value, 'status_code', None) == 404


def test_latest_published_run_is_selected():
    runs = [_run(run_id='run-old', revision=1), _run(run_id='run-new', revision=3)]
    summary = build_summary(runs, [], 'p', now=AS_OF)
    assert summary['run_id'] == 'run-new'
    assert summary['revision'] == 3


def test_endpoint_requires_project_access():
    assert client.get('/api/v1/projects/unknown-project/summary').status_code == 404
    response = client.get('/api/v1/projects/demo-project/summary')
    assert response.status_code == 200
    body = response.json()
    assert body['insight_metrics']['scope'] == 'selected_analysis'
    assert body['action_metrics']['scope'] == 'project_all_runs'
