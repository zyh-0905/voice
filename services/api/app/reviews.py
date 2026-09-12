"""W17 复盘同口径计算(工程计划 8.7)。

**口径由服务端从 run 里算,不由调用方提供。** 一个接受 n/N 的接口等于没有口径:
算术再正确,算的也是别人递进来的数字,窗口长度、是否重叠、目标主题是否属于这个
revision、样本量够不够,全都无从校验。所以请求体给的是**两个时间窗 + 筛选 + 目标
主题 + 人工确认**,分子分母在这里推导。

计划 8.7 的不变式:
- 两窗的日期/渠道/产品条件与分母定义必须相同;
- 多个 topic_version 取**反馈并集去重**,同一条反馈不重复相加;
- 半开区间 [start, end),两窗等长且不重叠;
- 无时间数据无法确认覆盖、分母为 0、窗口不等长、目标映射未确认 → insufficient;
- 每窗 N<50 保留原始数量,但不给效果判断。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Sequence

from .ingestion import iter_run_feedback, row_text
from .review_metrics import WindowMetrics, compare_counts

# 与 summary/feedback 一致的可用时间字段名
_TIME_KEYS = ('occurred_at', 'occurredAt', 'time', 'date', 'created_at', 'event_time')
_FILTER_KEYS = ('channel', 'product')
# 计划 8.7:每窗 N<50 时保留原始数量,但不给效果判断
MIN_WINDOW_SAMPLE = 50

COMPARABLE = 'ok'
INSUFFICIENT = 'insufficient'
LOW_SAMPLE = 'low_sample'


def _parse_time(value: object) -> datetime | None:
    """解析时间;naive 一律按 UTC 归一。

    不归一的话,带时区的窗口边界与不带时区的行时间比较会直接抛
    `can't compare offset-naive and offset-aware datetimes`——一个 500,而不是一个
    「不可比」结论。宁可给一个写明假设的默认值,也不要让请求崩掉。
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _row_time(row: Mapping) -> datetime | None:
    for key in _TIME_KEYS:
        parsed = _parse_time(row.get(key))
        if parsed is not None:
            return parsed
    return None


@dataclass(frozen=True)
class WindowSpec:
    start: str
    end: str


@dataclass(frozen=True)
class WindowQuery:
    """一个窗口的实测口径。untimed 是该窗口筛选条件下**时间不可用**的行数。"""
    start: str
    end: str
    n: int
    N: int
    untimed: int


@dataclass(frozen=True)
class ReviewComputation:
    comparability: str
    reasons: tuple[str, ...]
    before: WindowQuery
    after: WindowQuery
    metrics: WindowMetrics | None

    @property
    def comparable(self) -> bool:
        return self.comparability == COMPARABLE


def _topic_feedback_ids(run: Mapping, topic_version_ids: Sequence[str]) -> set[str]:
    """选中主题覆盖的反馈集合——多主题取并集,天然去重。"""
    evidence_by_topic = (run.get('result') or {}).get('evidence_by_topic') or {}
    ids: set[str] = set()
    for topic_id in topic_version_ids:
        for item in evidence_by_topic.get(topic_id) or []:
            if item.get('feedback_id'):
                ids.add(str(item['feedback_id']))
    return ids


def _matches_filters(row: Mapping, filters: Mapping) -> bool:
    """渠道/产品条件必须两窗相同,所以在一处判定后两窗共用。"""
    for key in _FILTER_KEYS:
        wanted = filters.get(key)
        if wanted and key in row and str(row.get(key)) != str(wanted):
            return False
    return True


def query_window(run: Mapping, spec: WindowSpec, filters: Mapping, topic_ids: set[str]) -> WindowQuery:
    """在 run 的输入集合内统计一个窗口。半开区间 [start, end),两窗共用同一套筛选。"""
    start, end = _parse_time(spec.start), _parse_time(spec.end)
    n = N = untimed = 0
    if start is None or end is None:
        return WindowQuery(spec.start, spec.end, 0, 0, 0)

    seen: set[str] = set()
    for feedback_id, row in iter_run_feedback(run):
        if feedback_id in seen:
            continue
        if not _matches_filters(row, filters):
            continue
        occurred = _row_time(row)
        if occurred is None:
            # 计划 8.7:不能用导入日期当来源发生日期——这条反馈既进不了窗口,
            # 也无法证明它不在窗口内,必须报出来
            untimed += 1
            continue
        if not (start <= occurred < end):
            continue
        seen.add(feedback_id)
        N += 1
        if feedback_id in topic_ids:
            n += 1
    return WindowQuery(spec.start, spec.end, n, N, untimed)


def _window_reasons(before: WindowQuery, after: WindowQuery) -> list[str]:
    """两窗之间的可比性理由;空列表表示窗口这一层没问题。"""
    reasons: list[str] = []
    b_start, b_end = _parse_time(before.start), _parse_time(before.end)
    a_start, a_end = _parse_time(after.start), _parse_time(after.end)
    if None in (b_start, b_end, a_start, a_end):
        reasons.append('窗口时间无法解析')
        return reasons
    if not (b_start < b_end) or not (a_start < a_end):
        reasons.append('窗口起点必须早于终点')
        return reasons
    if (b_end - b_start) != (a_end - a_start):
        reasons.append('前后窗口时长不等')
    if b_start < a_end and a_start < b_end:
        reasons.append('前后窗口重叠')
    return reasons


def compute_review(
    run: Mapping,
    *,
    revision: int,
    topic_version_ids: Sequence[str],
    before: WindowSpec,
    after: WindowSpec,
    filters: Mapping | None = None,
    alignment_confirmed: bool = False,
) -> ReviewComputation:
    """按计划 8.7 推导一份复盘结果。不可比时 metrics 为 None,不输出任何变化结论。"""
    filters = dict(filters or {})
    reasons: list[str] = []

    published_revision = (run.get('result') or {}).get('revision')
    if published_revision is None:
        reasons.append('该分析尚未发布 revision')
    elif int(published_revision) != int(revision):
        reasons.append(f'版本不一致:请求 {revision},当前 {published_revision}')

    evidence_by_topic = (run.get('result') or {}).get('evidence_by_topic') or {}
    unknown = [t for t in topic_version_ids if t not in evidence_by_topic]
    if unknown:
        reasons.append(f'目标主题不属于该 revision: {", ".join(unknown)}')

    before_q = query_window(run, before, filters, set())
    after_q = query_window(run, after, filters, set())
    reasons.extend(_window_reasons(before_q, after_q))

    if not alignment_confirmed:
        # 计划 8.7:目标映射未确认 → insufficient。本版不做跨 run 自动主题对齐,
        # 由人确认当前主题与原任务问题相符。
        reasons.append('目标映射尚未人工确认')

    if reasons:
        return ReviewComputation(INSUFFICIENT, tuple(reasons), before_q, after_q, None)

    topic_ids = _topic_feedback_ids(run, topic_version_ids)
    before_q = query_window(run, before, filters, topic_ids)
    after_q = query_window(run, after, filters, topic_ids)

    if before_q.untimed or after_q.untimed:
        return ReviewComputation(
            INSUFFICIENT, ('存在无法确定发生时间的反馈,不能确认窗口覆盖',),
            before_q, after_q, None,
        )
    if before_q.N == 0 or after_q.N == 0:
        return ReviewComputation(INSUFFICIENT, ('窗口内无可比数据(分母为 0)',), before_q, after_q, None)

    metrics = compare_counts(before_q.n, before_q.N, after_q.n, after_q.N)
    if before_q.N < MIN_WINDOW_SAMPLE or after_q.N < MIN_WINDOW_SAMPLE:
        # 保留原始数量供展示,但不给效果判断
        return ReviewComputation(LOW_SAMPLE, ('样本量不足(<50),不输出变化结论',), before_q, after_q, metrics)
    return ReviewComputation(COMPARABLE, (), before_q, after_q, metrics)
