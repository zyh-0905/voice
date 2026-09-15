"""W12 行动首页聚合(工程计划 7.7)。

insight_metrics 绑定所选分析 + 反馈筛选(scope=selected_analysis);
action_metrics 绑定当前项目全部任务(scope=project_all_runs),不受反馈筛选影响。
无已发布 run 时 insight 指标为 null(不伪造 0),项目任务仍可读。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Mapping, Sequence

from .ingestion import run_feedback

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


def _parse_time(value: object, *, timezone_name: str | None = None,
                end_of_day: bool = False) -> datetime | None:
    """解析时间筛选值;带时区的完整时间戳原样解析,裸日期按项目时区解释。

    前端日期选择器发 `YYYY-MM-DD`。此前一律按 UTC 解释,而数据里的
    occurred_at 多为 +08:00——「8 月 15 日」按 UTC 不含 +08:00 的 15 日
    0~8 点,跨日边界偏 8 小时。裸日期按 project.timezone 解释:
    start=当日 00:00;end=次日 00:00(所选 end 日期含当日),半开区间
    语义不变。无法识别的时区名回落 UTC。
    """
    if not isinstance(value, str) or not value:
        return None
    if len(value) == 10 and value[4] == '-' and value[7] == '-':
        try:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
            tz = ZoneInfo(timezone_name) if timezone_name else timezone.utc
        except (ZoneInfoNotFoundError, ValueError):
            tz = timezone.utc
        try:
            day = datetime.fromisoformat(value)
        except ValueError:
            return None
        if end_of_day:
            day = day + timedelta(days=1)
        return day.replace(tzinfo=tz)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _row_matches(row: Mapping, filters: Mapping[str, str | None],
                 timezone_name: str | None = None) -> bool:
    """按可用字段尽力应用筛选:只有行里存在对应字段时才参与过滤。"""
    for key in ('channel', 'product'):
        wanted = filters.get(key)
        if wanted and key in row and str(row.get(key)) != wanted:
            return False
    start = _parse_time(filters.get('start'), timezone_name=timezone_name)
    end = _parse_time(filters.get('end'), timezone_name=timezone_name, end_of_day=True)
    if start or end:
        row_time = next((_parse_time(row.get(k)) for k in _TIME_KEYS if row.get(k)), None)
        if row_time is not None:
            # 半开区间:[start, end);裸日期的 end 取次日零点,所选日期含当日
            if start and row_time < start:
                return False
            if end and row_time >= end:
                return False
    return True


def selected_rows(run: Mapping, filters: Mapping[str, str | None], repository,
                  timezone_name: str | None = None) -> list[dict]:
    """本 run 输入集合中通过筛选的反馈行(取自 feedback 实体表)。

    反馈行带 channel/product/occurred_at,与治理后行同名,所以 `_row_matches`
    的筛选口径不用改——换的只是取数来源。
    """
    return [row for row in run_feedback(dict(run), repository)
            if _row_matches(row, filters, timezone_name)]


def _latest_published_run(analysis_values: Sequence[dict], project_id: str, repository) -> dict | None:
    """最近已发布 revision 的 run;revision 取自 analysis_revisions(5.2)。"""
    published = None
    best = 0
    for run in analysis_values:
        if run.get('project_id') != project_id:
            continue
        revision = repository.latest_revision(project_id, run['id'])
        if not revision:
            continue
        if published is None or int(revision) >= best:
            best = int(revision)
            published = run
    return published


def resolve_run(analysis_values: Sequence[dict], project_id: str, run_id: str | None,
                revision: int | None, repository) -> dict | None:
    """按 7.7 选择规则定位 run:指定则校验归属与 revision;未指定取最近已发布 run。"""
    if revision is not None and not run_id:
        raise SummaryRequestError(422, 'revision_requires_run_id')
    if run_id:
        run = next((item for item in analysis_values if item.get('id') == run_id), None)
        if run is None or run.get('project_id') != project_id:
            raise SummaryRequestError(404, 'run_not_found')
        published = repository.latest_revision(project_id, run_id)
        if not published:
            return None
        if revision is not None and int(published) != int(revision):
            raise SummaryRequestError(404, 'revision_not_found')
        return run
    return _latest_published_run(analysis_values, project_id, repository)


def pending_risk_feedback_count(project_id: str, repository) -> int:
    """本项目至少有一条 PENDING 候选的 distinct 反馈数(全 severity,4.6 口径)。

    取数来自 `risk_findings` 实体(5.2)。不再按 run 过滤:候选挂在反馈上,而
    同一反馈的候选不因重跑分析而增加——按 run 过滤会让数字随分析次数变化。
    """
    return len({
        str(item['feedback_id'])
        for item in repository.list_risk_findings(project_id)
        if str(item.get('review_state', 'pending')).lower() == 'pending' and item.get('feedback_id')
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
    *,
    # 反馈正文来自 feedback 实体表,所以聚合必须拿到仓储。不给默认值:
    # 一个「没有仓储也能算」的降级会走一条与生产不同的路径,而且没有任何东西在读。
    repository,
    # 裸日期筛选按项目时区解释(见 _parse_time);不给则按 UTC
    timezone_name: str | None = None,
) -> dict:
    """组装 7.7 契约响应。"""
    filters = dict(filters or {})
    timestamp = now or datetime.now(timezone.utc)
    run = resolve_run(analysis_values, project_id, run_id, revision, repository)
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

    from .revisions import load_revision_snapshot
    snapshot = load_revision_snapshot(repository, run) or {}
    rows = selected_rows(run, filters, repository, timezone_name)
    payload.update({
        'run_id': run.get('id'),
        'revision': snapshot.get('revision'),
        'denominator': len(rows),
    })
    payload['insight_metrics'].update({
        'valid_feedback_count': len(rows),
        'topic_count': len(snapshot.get('topics') or []),
        'pending_risk_feedback_count': pending_risk_feedback_count(project_id, repository),
    })
    return payload


# 演示回退点列:无已发布 run 时与旧实现完全一致(合成、固定、含一个缺失断点)
SYNTHETIC_TREND_POINTS = [
    {'date': '08-26', 'value': 142}, {'date': '08-27', 'value': 151},
    {'date': '08-28', 'value': None}, {'date': '08-29', 'value': 158},
    {'date': '08-30', 'value': 149}, {'date': '08-31', 'value': 161},
    {'date': '09-01', 'value': 155},
]


def _tz(timezone_name: str | None):
    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        return ZoneInfo(timezone_name) if timezone_name else timezone.utc
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc


def build_trend(analysis_values: Sequence[dict], project_id: str,
                start: str | None = None, end: str | None = None,
                channel: str | None = None, product: str | None = None,
                repository=None, timezone_name: str | None = None) -> dict:
    """趋势点列:有已发布 run 时按其冻结输入的 occurred_at 聚合每自然日计数。

    此前 `/trend` 返回硬编码的合成点列——真实模式下趋势图与上传数据无关,
    而它看起来完全是真数据。现在:

    - 有已发布 run → 按**项目时区**的自然日分组计数,窗口与渠道/产品筛选
      和 summary 同口径(7.7:筛选只约束反馈侧);无时间的行不进点列,
      **不造 0**、不编日期;窗口内没有任何带时间的行 → 空点列(如实为空)。
    - 无已发布 run → 合成演示点列(演示路径,与旧实现一致)。
    """
    if repository is None:
        raise ValueError('build_trend requires the repository: feedback rows live in the entity table')
    run = _latest_published_run(analysis_values, project_id, repository)
    if run is None:
        return {'items': [dict(point) for point in SYNTHETIC_TREND_POINTS],
                'total': len(SYNTHETIC_TREND_POINTS)}

    filters = {'start': start, 'end': end, 'channel': channel, 'product': product}
    tz = _tz(timezone_name)
    counts: dict[str, int] = {}
    for row in selected_rows(run, filters, repository, timezone_name):
        row_time = next((_parse_time(row.get(k)) for k in _TIME_KEYS if row.get(k)), None)
        if row_time is None:
            continue
        # 内部键用完整日期:输出格式只有 MM-DD,跨年时按 MM-DD 排序会错位
        day = row_time.astimezone(tz).strftime('%Y-%m-%d')
        counts[day] = counts.get(day, 0) + 1
    items = [{'date': day[5:].replace('-', '-'), 'value': counts[day]}
             for day in sorted(counts)]
    return {'items': items, 'total': len(items)}
