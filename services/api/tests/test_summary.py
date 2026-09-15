"""W12 聚合契约:scope 分组、去重计数、筛选范围隔离、逾期边界、无 run 语义。"""
from datetime import datetime, timedelta, timezone

import pytest

from app.main import app
from app.summary import build_summary
from support.client import make_client
from support.feedback import new_repository, publish_revision_rows, seed_run_feedback

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
        # 用例的输入声明:真实 run 上没有这个键(5.2 之后候选只存 risk_findings 表),
        # 由 _summary 写进表里——聚合读的也是表,两边走同一条路径
        'risk_findings': findings or [],
    }


def _task(state, due_at=None, project_id='p'):
    return {'id': f'task-{state}-{due_at}', 'project_id': project_id, 'state': state, 'due_at': due_at}


def _summary(analysis_runs, tasks, project_id='p', **kwargs):
    """播种 feedback 行与风险候选后再聚合。

    工程计划 5.2 之后正文取自 `feedback` 表、候选取自 `risk_findings` 表,run 里
    内嵌的行只是用例的输入声明;直接调用 build_summary 会测到一条生产上不存在的
    取数路径。
    """
    repository = new_repository()
    for run in analysis_runs:
        seed_run_feedback(repository, run)
        # 主题与证据现在落在实体表里,读模型按 manifest 现算(5.2):
        # 不物化的话「主题数是 0」,而那看起来像「这次分析没有主题」
        publish_revision_rows(repository, run)
        # 候选也必须真的落表:只在用例里摆着的话「待复核风险数」是 0,而那看起来
        # 像「本项目没有待复核风险」——正是这条链路哑掉时的样子
        findings = run.pop('risk_findings', None) or []
        if findings:
            repository.save_risk_findings(project_id, run['id'], findings)
    return build_summary(analysis_runs, tasks, project_id, repository=repository, **kwargs)


def test_summary_exposes_scopes():
    summary = _summary([_run()], [_task('OPEN')], 'p', now=AS_OF)
    assert summary['insight_metrics']['scope'] == 'selected_analysis'
    assert summary['action_metrics']['scope'] == 'project_all_runs'
    assert summary['action_metrics']['overdue_task_count'] <= summary['action_metrics']['active_task_count']


def test_denominator_matches_valid_feedback_count():
    summary = _summary([_run(rows=[{'text': 'a'}, {'text': 'b'}, {'text': 'c'}])], [], 'p', now=AS_OF)
    assert summary['denominator'] == summary['insight_metrics']['valid_feedback_count'] == 3


def test_topic_count_from_published_revision():
    summary = _summary([_run(topics=5)], [], 'p', now=AS_OF)
    assert summary['insight_metrics']['topic_count'] == 5


def test_pending_risk_counts_distinct_feedback_all_severities():
    # 行形状即 risk_findings 表(5.2)的列:id 与 (feedback_id, rule_id, policy_version)
    # 唯一键都要在,否则写进表的候选不幂等,计数也会随着重跑漂移
    findings = [
        {'id': 'rf-1', 'feedback_id': 'fb1', 'rule_id': 'r1', 'policy_version': 'v1',
         'severity': 'HIGH', 'review_state': 'PENDING'},
        {'id': 'rf-2', 'feedback_id': 'fb1', 'rule_id': 'r2', 'policy_version': 'v1',
         'severity': 'CRITICAL', 'review_state': 'PENDING'},
        {'id': 'rf-3', 'feedback_id': 'fb2', 'rule_id': 'r1', 'policy_version': 'v1',
         'severity': 'LOW', 'review_state': 'PENDING'},
        {'id': 'rf-4', 'feedback_id': 'fb3', 'rule_id': 'r1', 'policy_version': 'v1',
         'severity': 'HIGH', 'review_state': 'CONFIRMED'},
    ]
    summary = _summary([_run(findings=findings)], [], 'p', now=AS_OF)
    # 同一反馈命中两条规则只计 1;已确认的不计入
    assert summary['insight_metrics']['pending_risk_feedback_count'] == 2


def test_filters_only_affect_insight_metrics():
    tasks = [_task('OPEN'), _task('IN_PROGRESS', due_at='2026-09-01T00:00:00+00:00')]
    unfiltered = _summary([_run()], tasks, 'p', now=AS_OF)
    filtered = _summary([_run()], tasks, 'p', filters={'channel': 'phone'}, now=AS_OF)
    # 无 channel 字段的行不被筛掉,但 action 指标在任何筛选下都不变
    assert filtered['action_metrics'] == unfiltered['action_metrics']
    assert filtered['action_metrics']['active_task_count'] == 2
    assert filtered['action_metrics']['overdue_task_count'] == 1


def test_channel_filter_narrows_insight_denominator():
    rows = [{'text': 'a', 'channel': 'phone'}, {'text': 'b', 'channel': 'chat'}]
    summary = _summary([_run(rows=rows)], [], 'p', filters={'channel': 'phone'}, now=AS_OF)
    assert summary['denominator'] == 1


def test_time_window_is_half_open():
    rows = [
        {'text': 'before', 'occurred_at': '2026-08-31T23:59:59+00:00'},
        {'text': 'at-start', 'occurred_at': '2026-09-01T00:00:00+00:00'},
        {'text': 'at-end', 'occurred_at': '2026-09-02T00:00:00+00:00'},
    ]
    summary = _summary([_run(rows=rows)], [], 'p',
                            filters={'start': '2026-09-01T00:00:00+00:00', 'end': '2026-09-02T00:00:00+00:00'},
                            now=AS_OF)
    assert summary['denominator'] == 1  # [start, end)


def test_overdue_boundary_due_equals_as_of_is_not_overdue():
    due = AS_OF.isoformat()
    just_before = (AS_OF - timedelta(seconds=1)).isoformat()
    summary = _summary([_run()], [_task('OPEN', due_at=due), _task('OPEN', due_at=just_before)], 'p', now=AS_OF)
    assert summary['action_metrics']['active_task_count'] == 2
    assert summary['action_metrics']['overdue_task_count'] == 1


def test_closed_states_excluded_from_active():
    tasks = [_task('DRAFT'), _task('CLOSED'), _task('CANCELLED'), _task('PENDING_REVIEW')]
    summary = _summary([_run()], tasks, 'p', now=AS_OF)
    assert summary['action_metrics']['active_task_count'] == 1


def test_no_published_run_returns_null_insight_but_readable_tasks():
    run = {'id': 'run-q', 'project_id': 'p', 'status': 'queued', 'datasets': [],
           'result': {}}
    summary = _summary([run], [_task('OPEN')], 'p', now=AS_OF)
    assert summary['run_id'] is None and summary['revision'] is None
    assert summary['insight_metrics']['valid_feedback_count'] is None
    assert summary['insight_metrics']['topic_count'] is None
    assert summary['insight_metrics']['pending_risk_feedback_count'] is None
    assert summary['denominator'] is None
    assert summary['action_metrics']['active_task_count'] == 1


def test_revision_without_run_id_rejected():
    with pytest.raises(Exception) as exc:
        _summary([_run()], [], 'p', revision=1, now=AS_OF)
    assert getattr(exc.value, 'status_code', None) == 422


def test_foreign_run_not_found():
    with pytest.raises(Exception) as exc:
        _summary([_run(project_id='other')], [], 'p', run_id='run-1', now=AS_OF)
    assert getattr(exc.value, 'status_code', None) == 404


def test_latest_published_run_is_selected():
    runs = [_run(run_id='run-old', revision=1), _run(run_id='run-new', revision=3)]
    summary = _summary(runs, [], 'p', now=AS_OF)
    assert summary['run_id'] == 'run-new'
    assert summary['revision'] == 3


def test_endpoint_requires_project_access():
    assert client.get('/api/v1/projects/unknown-project/summary').status_code == 404
    response = client.get('/api/v1/projects/demo-project/summary')
    assert response.status_code == 200
    body = response.json()
    assert body['insight_metrics']['scope'] == 'selected_analysis'
    assert body['action_metrics']['scope'] == 'project_all_runs'


def test_bare_dates_use_the_project_timezone():
    """裸日期按项目时区解释:前端日期选择器发 YYYY-MM-DD。

    按 UTC 解释时「9 月 1 日」不含 +08:00 的 1 日 0~8 点——同一天筛选
    偏 8 小时。这里的行落在 UTC 8 月 31 日 20 点(= +08:00 的 9 月 1 日):
    旧口径(UTC)会把它挡在 start 之外,新口径按项目时区应算进去。
    end 同理取次日零点,所选日期含当日。
    """
    rows = [
        {'text': 'utc-aug31-20h', 'occurred_at': '2026-08-31T20:00:00+00:00'},
        {'text': 'sept1-morning', 'occurred_at': '2026-09-01T02:00:00+08:00'},
    ]
    summary = _summary([_run(rows=rows)], [], 'p',
                       filters={'start': '2026-09-01', 'end': '2026-09-01'},
                       now=AS_OF, timezone_name='Asia/Shanghai')
    assert summary['denominator'] == 2  # [9-01 00:00, 9-02 00:00) 项目本地


def test_bare_dates_still_utc_without_timezone():
    """不传项目时区时保持旧口径(UTC),显式完整时间戳也原样解析。"""
    rows = [{'text': 'utc-aug31-20h', 'occurred_at': '2026-08-31T20:00:00+00:00'}]
    summary = _summary([_run(rows=rows)], [], 'p',
                       filters={'start': '2026-09-01', 'end': '2026-09-01'},
                       now=AS_OF)
    assert summary['denominator'] == 0  # UTC 解释:行在 9-01 之前


# —— /trend:真实聚合(此前是硬编码合成点列,真实模式也发假数据) ——

def test_trend_aggregates_published_run_by_day():
    rows = [
        {'text': 'a', 'occurred_at': '2026-09-01T10:00:00+08:00'},
        {'text': 'b', 'occurred_at': '2026-09-01T18:00:00+08:00'},
        {'text': 'c', 'occurred_at': '2026-09-02T10:00:00+08:00'},
        {'text': 'no-time'},  # 无时间行不进点列,不造 0
    ]
    from app.summary import build_trend
    repository = new_repository()
    run = _run(rows=rows)
    seed_run_feedback(repository, run)
    publish_revision_rows(repository, run)
    trend = build_trend([run], 'p', repository=repository,
                        timezone_name='Asia/Shanghai')
    assert trend['items'] == [{'date': '09-01', 'value': 2}, {'date': '09-02', 'value': 1}]
    assert trend['total'] == 2


def test_trend_without_published_run_falls_back_to_synthetic():
    from app.summary import build_trend, SYNTHETIC_TREND_POINTS
    # 没有任何 run(_run 不播种 revision)→ 合成演示点列
    trend = build_trend([], 'p', repository=new_repository())
    assert trend['items'] == SYNTHETIC_TREND_POINTS


def test_trend_respects_the_window_filter():
    rows = [
        {'text': 'in', 'occurred_at': '2026-09-02T10:00:00+08:00'},
        {'text': 'out', 'occurred_at': '2026-09-05T10:00:00+08:00'},
    ]
    from app.summary import build_trend
    repository = new_repository()
    run = _run(rows=rows)
    seed_run_feedback(repository, run)
    publish_revision_rows(repository, run)
    trend = build_trend([run], 'p', repository=repository,
                        start='2026-09-01', end='2026-09-03', timezone_name='Asia/Shanghai')
    assert trend['items'] == [{'date': '09-02', 'value': 1}]
