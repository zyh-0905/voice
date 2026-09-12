"""W12 行动首页聚合(工程计划 7.7)。

insight_metrics 绑定所选分析 + 反馈筛选(scope=selected_analysis);
action_metrics 绑定当前项目全部任务(scope=project_all_runs),不受反馈筛选影响。
无已发布 run 时 insight 指标为 null(不伪造 0),项目任务仍可读。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Sequence

DEFINITION_VERSION = 'summary-ui-v1'
UNCLOSED_STATES = ('OPEN', 'IN_PROGRESS', 'PENDING_REVIEW')
# 反馈行中可识别的时间字段(治理后的脱敏行)
_TIME_KEYS = ('occurred_at', 'occurredAt', 'time', 'date', 'created_at', 'event_time')


class SummaryRequestError(ValueError):
    """请求本身不合法(如只给 revision 不给 run_id)。"""

    def __init__(self, status_code: int, code: str):
        super().__init__(code)
        self.status_code = status_code
        self.code = code


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _row_matches(row: Mapping, filters: Mapping[str, str | None]) -> bool:
    """按可用字段尽力应用筛选:只有行里存在对应字段时才参与过滤。"""
    for key in ('channel', 'product'):
        wanted = filters.get(key)
        if wanted and key in row and str(row.get(key)) != wanted:
            return False
    start = _parse_time(filters.get('start'))
    end = _parse_time(filters.get('end'))
    if start or end:
        row_time = next((_parse_time(row.get(k)) for k in _TIME_KEYS if row.get(k)), None)
        if row_time is not None:
            # 半开区间:[start, end)
            if start and row_time < start:
                return False
            if end and row_time >= end:
                return False
    return True


def selected_rows(run: Mapping, filters: Mapping[str, str | None]) -> list[dict]:
    """本 run 输入集合中通过筛选的反馈行。"""
    rows: list[dict] = []
    for dataset in run.get('datasets') or []:
        for row in (dataset.get('preview') or {}).get('rows') or []:
            if isinstance(row, dict) and _row_matches(row, filters):
                rows.append(row)
    return rows


def _latest_published_run(analysis_values: Sequence[dict], project_id: str) -> dict | None:
    published = None
    for run in analysis_values:
        if run.get('project_id') != project_id:
            continue
        revision = (run.get('result') or {}).get('revision')
        if not revision:
            continue
        if published is None or int(revision) >= int(published['result']['revision']):
            published = run
    return published


def resolve_run(analysis_values: Sequence[dict], project_id: str, run_id: str | None, revision: int | None) -> dict | None:
    """按 7.7 选择规则定位 run:指定则校验归属与 revision;未指定取最近已发布 run。"""
    if revision is not None and not run_id:
        raise SummaryRequestError(422, 'revision_requires_run_id')
    if run_id:
        run = next((item for item in analysis_values if item.get('id') == run_id), None)
        if run is None or run.get('project_id') != project_id:
            raise SummaryRequestError(404, 'run_not_found')
        published = run.get('result') or {}
        if not published.get('revision'):
            return None
        if revision is not None and int(published['revision']) != int(revision):
            raise SummaryRequestError(404, 'revision_not_found')
        return run
    return _latest_published_run(analysis_values, project_id)


def pending_risk_feedback_count(run: Mapping) -> int:
    """本次 run 输入集合内、至少有一个 PENDING 风险 finding 的 distinct 反馈数(全 severity)。"""
    findings = run.get('risk_findings') or []
    return len({
        str(item.get('feedback_id'))
        for item in findings
        if str(item.get('review_state', 'PENDING')).upper() == 'PENDING' and item.get('feedback_id')
    })


def task_metrics(tasks: Sequence[Mapping], as_of: datetime) -> tuple[int, int]:
    """未关闭任务数与其中逾期数;边界 due_at == as_of 不算逾期。"""
    active = [t for t in tasks if str(t.get('state') or t.get('status') or '').upper() in UNCLOSED_STATES]
    overdue = 0
    for task in active:
        due = _parse_time(task.get('due_at'))
        if due is not None and due < as_of:
            overdue += 1
    return len(active), overdue


def build_summary(
    analysis_values: Sequence[dict],
    tasks: Sequence[Mapping],
    project_id: str,
    run_id: str | None = None,
    revision: int | None = None,
    filters: Mapping[str, str | None] | None = None,
    now: datetime | None = None,
) -> dict:
    """组装 7.7 契约响应。"""
    filters = dict(filters or {})
    timestamp = now or datetime.now(timezone.utc)
    run = resolve_run(analysis_values, project_id, run_id, revision)
    active_count, overdue_count = task_metrics(tasks, timestamp)

    payload = {
        'project_id': project_id,
        'run_id': None,
        'revision': None,
        'denominator': None,
        'definition_version': DEFINITION_VERSION,
        'computed_at': timestamp.isoformat(),
        'filters': {
            'start': filters.get('start'), 'end': filters.get('end'),
            'channel': filters.get('channel'), 'product': filters.get('product'),
        },
        'insight_metrics': {
            'scope': 'selected_analysis',
            'valid_feedback_count': None,
            'topic_count': None,
            'pending_risk_feedback_count': None,
        },
        'action_metrics': {
            'scope': 'project_all_runs',
            'active_task_count': active_count,
            'overdue_task_count': overdue_count,
            'task_as_of': timestamp.isoformat(),
        },
    }
    if run is None:
        return payload  # 无已发布 run:洞察为空,项目任务仍可读

    published = run.get('result') or {}
    rows = selected_rows(run, filters)
    payload.update({
        'run_id': run.get('id'),
        'revision': published.get('revision'),
        'denominator': len(rows),
    })
    payload['insight_metrics'].update({
        'valid_feedback_count': len(rows),
        'topic_count': len(published.get('topics') or []),
        'pending_risk_feedback_count': pending_risk_feedback_count(run),
    })
    return payload
