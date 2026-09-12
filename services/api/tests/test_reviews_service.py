"""W17 复盘同口径(计划 8.7)。

这些用例针对的是「口径从哪来」:调用方给数字时,窗口是否等长、是否重叠、主题是否
属于该 revision、样本够不够,全都无从校验——算术再对也不构成同口径比较。

黄金值本身(168/1000→102/1000、100/1000→80/500)由 test_review_metrics.py 覆盖,
这里只验证推导与可比性闸门。
"""
from datetime import date, timedelta

from app.reviews import (
    COMPARABLE,
    INSUFFICIENT,
    LOW_SAMPLE,
    WindowSpec,
    compute_review,
)

# 两窗必须等长,所以不能按自然月取(8 月 31 天、9 月 30 天)——各取 30 天
BEFORE = WindowSpec('2026-08-01T00:00:00+00:00', '2026-08-31T00:00:00+00:00')
AFTER = WindowSpec('2026-09-01T00:00:00+00:00', '2026-10-01T00:00:00+00:00')


def _rows(start: date, count: int, prefix: str) -> list[dict]:
    return [
        {'feedback_id': f'{prefix}_{i}', 'text': '物流信息一直没有更新',
         'occurred_at': (start + timedelta(days=i % 28)).isoformat()}
        for i in range(count)
    ]


def _evidence(before_hits: int, after_hits: int = 0, topic: str = 't1') -> dict:
    """主题 t1 的证据:前窗前 before_hits 条 + 后窗前 after_hits 条。"""
    ids = [{'feedback_id': f'before_{i}'} for i in range(before_hits)]
    ids += [{'feedback_id': f'after_{i}'} for i in range(after_hits)]
    return {topic: ids}


def _run(rows, evidence, revision: int = 1) -> dict:
    return {
        'id': 'run_1', 'project_id': 'p',
        'datasets': [{'id': 'ds', 'preview': {'rows': rows}}],
        'result': {'revision': revision, 'evidence_by_topic': evidence},
    }


def _computation(rows, evidence, *, before=BEFORE, after=AFTER, topics=('t1',),
                 run_revision=1, request_revision=None, **kwargs):
    """run_revision 是已发布的版本,request_revision 是请求里写的版本——两者分开,
    才能构造出「版本不一致」。"""
    published = run_revision if request_revision is None else request_revision
    return compute_review(
        _run(rows, evidence, run_revision),
        revision=published, topic_version_ids=list(topics),
        before=before, after=after, alignment_confirmed=True, **kwargs,
    )


def test_denominator_and_numerator_come_from_the_run():
    """n/N 必须由窗口与主题证据推导,而不是外部给的数字。"""
    rows = _rows(date(2026, 8, 1), 100, 'before') + _rows(date(2026, 9, 1), 100, 'after')
    result = _computation(rows, _evidence(17, 10))

    assert result.before.N == 100 and result.before.n == 17
    assert result.after.N == 100 and result.after.n == 10
    assert result.comparability == COMPARABLE
    assert result.metrics is not None
    assert result.metrics.share_delta_pp == -7.0


def test_window_filters_out_of_range_rows():
    """窗口外的反馈不进分母——半开区间,且不能拿导入日期冒充发生时间。"""
    rows = _rows(date(2026, 8, 1), 100, 'before') + _rows(date(2026, 9, 1), 100, 'after')
    narrow = WindowSpec('2026-08-01T00:00:00+00:00', '2026-08-11T00:00:00+00:00')
    result = _computation(rows, _evidence(17, 10), before=narrow)

    assert result.before.N < 100, '窗口收窄后分母必须变小'
    assert result.comparability == INSUFFICIENT, '两窗不等长 → 不可比'


def test_unequal_windows_are_insufficient():
    rows = _rows(date(2026, 8, 1), 100, 'before') + _rows(date(2026, 9, 1), 100, 'after')
    short = WindowSpec('2026-09-01T00:00:00+00:00', '2026-09-21T00:00:00+00:00')
    result = _computation(rows, _evidence(17, 10), after=short)

    assert result.comparability == INSUFFICIENT
    assert any('时长不等' in reason for reason in result.reasons)
    assert result.metrics is None, '不可比时不得输出任何变化结论'


def test_overlapping_windows_are_insufficient():
    rows = _rows(date(2026, 8, 1), 100, 'before') + _rows(date(2026, 9, 1), 100, 'after')
    overlapping = WindowSpec('2026-08-20T00:00:00+00:00', '2026-09-19T00:00:00+00:00')
    result = _computation(rows, _evidence(17, 10), after=overlapping)

    assert result.comparability == INSUFFICIENT
    assert any('重叠' in reason for reason in result.reasons)


def test_untimed_rows_block_comparability():
    """无时间数据无法确认覆盖 → insufficient,不能用导入日期顶替。"""
    rows = _rows(date(2026, 8, 1), 100, 'before')
    rows += [{'feedback_id': f'after_{i}', 'text': '没有时间字段'} for i in range(100)]
    result = _computation(rows, _evidence(17, 10))

    assert result.comparability == INSUFFICIENT
    assert any('无法确定发生时间' in reason for reason in result.reasons)


def test_unconfirmed_alignment_is_insufficient():
    """本版不做跨 run 自动主题对齐,目标映射必须人工确认(计划 8.7)。"""
    rows = _rows(date(2026, 8, 1), 100, 'before') + _rows(date(2026, 9, 1), 100, 'after')
    result = compute_review(
        _run(rows, _evidence(17, 10)), revision=1, topic_version_ids=['t1'],
        before=BEFORE, after=AFTER, alignment_confirmed=False,
    )

    assert result.comparability == INSUFFICIENT
    assert any('人工确认' in reason for reason in result.reasons)


def test_foreign_topic_is_insufficient():
    rows = _rows(date(2026, 8, 1), 100, 'before') + _rows(date(2026, 9, 1), 100, 'after')
    result = _computation(rows, _evidence(17, 10), topics=('t_missing',))

    assert result.comparability == INSUFFICIENT
    assert any('不属于该 revision' in reason for reason in result.reasons)


def test_revision_mismatch_is_insufficient():
    rows = _rows(date(2026, 8, 1), 100, 'before') + _rows(date(2026, 9, 1), 100, 'after')
    result = _computation(rows, _evidence(17, 10), request_revision=2)

    assert result.comparability == INSUFFICIENT
    assert any('版本不一致' in reason for reason in result.reasons)


def test_small_windows_keep_counts_but_give_no_verdict():
    """每窗 N<50:保留原始数量,但不给效果判断(计划 8.7)。"""
    rows = _rows(date(2026, 8, 1), 20, 'before') + _rows(date(2026, 9, 1), 20, 'after')
    result = _computation(rows, _evidence(17, 10))

    assert result.comparability == LOW_SAMPLE
    assert result.before.N == 20 and result.after.N == 20, '数量仍要保留'
    assert result.metrics is not None, '数量可展示'
    assert not result.comparable, '但不能据此宣称变化'


def test_zero_denominator_is_insufficient():
    rows = _rows(date(2026, 8, 1), 100, 'before') + _rows(date(2026, 9, 1), 100, 'after')
    empty = WindowSpec('2026-12-01T00:00:00+00:00', '2026-12-31T00:00:00+00:00')
    result = _computation(rows, _evidence(17, 10), after=empty)

    assert result.comparability == INSUFFICIENT
    assert result.metrics is None


def test_multi_topic_numerator_is_a_deduped_union():
    """多主题取反馈并集:同一条反馈属于两个主题也只算一次(计划 8.7)。"""
    rows = [
        {'feedback_id': 'shared', 'text': '被两个主题引用', 'occurred_at': '2026-08-05T00:00:00+00:00'},
        {'feedback_id': 'only_t1', 'text': '只有 t1 引用', 'occurred_at': '2026-08-06T00:00:00+00:00'},
        {'feedback_id': 'after_0', 'text': '后窗', 'occurred_at': '2026-09-05T00:00:00+00:00'},
    ]
    run = {
        'id': 'run_1', 'project_id': 'p',
        'datasets': [{'id': 'ds', 'preview': {'rows': rows}}],
        'result': {'revision': 1, 'evidence_by_topic': {
            't1': [{'feedback_id': 'shared'}, {'feedback_id': 'only_t1'}],
            't2': [{'feedback_id': 'shared'}],
        }},
    }
    result = compute_review(
        run, revision=1, topic_version_ids=['t1', 't2'],
        before=BEFORE, after=AFTER, alignment_confirmed=True,
    )

    # 并集 {shared, only_t1};若按主题相加会得到 3
    assert result.before.n == 2, '同一条反馈被两个主题引用,只能算一次'
