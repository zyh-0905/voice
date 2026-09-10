"""W17 复盘同口径计算。

compare_counts 返回 WindowMetrics(count_change、share_delta_pp、relative_share_change、comparable);
零分母/不可比时不输出改善结论——不是简单相减两个看板数字。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WindowMetrics:
    count_change: int | None
    share_before_pp: float | None
    share_after_pp: float | None
    share_delta_pp: float | None
    relative_share_change: float | None
    comparable: bool


def compare_counts(n_before: int, N_before: int, n_after: int, N_after: int) -> WindowMetrics:
    """同口径比较:占比为百分点,变化为百分点差值,相对变化为 share_delta/before_share。

    任一分母为 0 → comparable=False,不输出任何变化结论。
    """
    if N_before <= 0 or N_after <= 0:
        return WindowMetrics(
            count_change=n_after - n_before,
            share_before_pp=None, share_after_pp=None,
            share_delta_pp=None, relative_share_change=None,
            comparable=False,
        )
    share_before = n_before / N_before * 100
    share_after = n_after / N_after * 100
    delta_pp = share_after - share_before
    relative = (delta_pp / share_before) if share_before > 0 else None
    return WindowMetrics(
        count_change=n_after - n_before,
        share_before_pp=round(share_before, 2),
        share_after_pp=round(share_after, 2),
        share_delta_pp=round(delta_pp, 2),
        relative_share_change=round(relative, 4) if relative is not None else None,
        comparable=True,
    )


def effect_status(metrics: WindowMetrics) -> str:
    """复盘状态:不可比 → INSUFFICIENT_DATA;可比 → OBSERVED_CHANGE(描述性,非因果证明)。"""
    return 'OBSERVED_CHANGE' if metrics.comparable else 'INSUFFICIENT_DATA'
