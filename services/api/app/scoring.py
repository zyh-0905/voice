"""W14 CPI 评分(工程计划 8.6,纯函数)。

CPI = 0.25×V + 0.30×G + 0.30×S + 0.15×B,可配置权重;缺失分项剔除后其余归一化。
CPI 是可解释指数,不是概率;critical 候选独立置顶,CPI 低不压制安全提示。

说明:计划里文件名为 app/topics/scoring.py,本仓库使用扁平 app/ 布局,
故落在 app/scoring.py(与既有模块一致)。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Mapping

# 严重度 → S 分(线性档位:high=75 与黄金样例一致)
SEVERITY_SCORES: Mapping[str, float] = {
    'NONE': 0.0, 'LOW': 25.0, 'MEDIUM': 50.0, 'HIGH': 75.0, 'CRITICAL': 100.0,
}

DEFAULT_WEIGHTS: Mapping[str, float] = {
    'volume': 0.25, 'growth': 0.30, 'severity': 0.30, 'business': 0.15,
}

# 占比参考点:V 在 p1 = 20% 时达到满分
VOLUME_REFERENCE_SHARE = 0.20
# G 的样本与窗口门槛(工程约定,不是统计标准)
GROWTH_MIN_DENOMINATOR = 50
GROWTH_MIN_HITS = 5
# p0 平滑下限:仅用于指数计算,不改变原始数据展示
GROWTH_SMOOTHING = 0.02
DEFAULT_BUSINESS = 50.0
WEIGHT_SUM_TOLERANCE = 1e-6


class ScoringInputError(ValueError):
    """输入不合法(计数越界、非有限数、权重不满足约束)。"""


@dataclass(frozen=True)
class CpiResult:
    value: float | None
    display_value: int | None
    components: Mapping[str, float | None]
    effective_weights: Mapping[str, float]
    coverage: float
    provisional: bool
    assumptions: tuple[str, ...]


def validate_weights(weights: Mapping[str, float]) -> dict[str, float]:
    """四项权重必须齐全、有限非负、总和 1±1e-6 且至少一项为正。"""
    if set(weights) != set(DEFAULT_WEIGHTS):
        raise ScoringInputError(f'weights must define exactly {sorted(DEFAULT_WEIGHTS)}')
    normalized: dict[str, float] = {}
    for key, raw in weights.items():
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise ScoringInputError(f'weight {key} must be a number') from exc
        if not math.isfinite(value) or value < 0:
            raise ScoringInputError(f'weight {key} must be finite and non-negative')
        normalized[key] = value
    total = sum(normalized.values())
    if abs(total - 1.0) > WEIGHT_SUM_TOLERANCE:
        raise ScoringInputError(f'weights must sum to 1, got {total}')
    if total <= 0:
        raise ScoringInputError('at least one weight must be positive')
    return normalized


def round_half_up(value: float) -> int:
    """整数显示用十进制 HALF_UP,避免不同语言的银行家舍入产生不一致。"""
    return int(Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _check_count(name: str, value: object) -> float:
    if value is None:
        raise ScoringInputError(f'{name} is required')
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ScoringInputError(f'{name} must be a number') from exc
    if not math.isfinite(number) or number < 0:
        raise ScoringInputError(f'{name} must be finite and non-negative')
    return number


def compute_cpi(
    *,
    n1: int,
    N1: int,
    n0: int | None,
    N0: int | None,
    severity: str | None,
    business: float | None,
    comparable_windows: bool = True,
    weights: Mapping[str, float] | None = None,
) -> CpiResult:
    """按冻结签名计算 CPI;无法计算时 value/display_value 为 None。"""
    hits = _check_count('n1', n1)
    denominator = _check_count('N1', N1)
    if hits > denominator:
        raise ScoringInputError('n1 must not exceed N1')

    active_weights = validate_weights(weights) if weights is not None else dict(DEFAULT_WEIGHTS)
    assumptions: list[str] = []
    components: dict[str, float | None] = {}

    # V:占比相对 20% 参考点的达标度
    if denominator <= 0:
        # N1=0 时整个 CPI 不可用
        return CpiResult(
            value=None, display_value=None,
            components={'volume': None, 'growth': None, 'severity': None, 'business': None},
            effective_weights={}, coverage=0.0, provisional=True,
            assumptions=('no_denominator',),
        )
    p1 = hits / denominator
    components['volume'] = 100 * min(1.0, p1 / VOLUME_REFERENCE_SHARE)

    # G:相对前期占比的变化;样本或窗口不满足时不计算
    growth: float | None = None
    if n0 is None or N0 is None:
        assumptions.append('growth_missing_history')
    else:
        prev_hits = _check_count('n0', n0)
        prev_denominator = _check_count('N0', N0)
        if prev_hits > prev_denominator:
            raise ScoringInputError('n0 must not exceed N0')
        if not comparable_windows:
            assumptions.append('growth_windows_not_comparable')
        elif prev_denominator < GROWTH_MIN_DENOMINATOR or denominator < GROWTH_MIN_DENOMINATOR:
            assumptions.append('growth_low_sample')
        elif hits < GROWTH_MIN_HITS:
            assumptions.append('growth_too_few_hits')
        else:
            p0 = prev_hits / prev_denominator
            if p0 == 0:
                assumptions.append('growth_newly_appeared')
            growth = 100 * max(0.0, min(1.0, (p1 - p0) / max(p0, GROWTH_SMOOTHING)))
    components['growth'] = growth

    # S:严重度映射;未知严重度按缺失处理
    severity_score = SEVERITY_SCORES.get(str(severity or '').upper())
    if severity is not None and severity_score is None:
        assumptions.append('severity_unknown')
    components['severity'] = severity_score

    # B:企业配置或人员输入;缺失默认 50 并记录假设
    if business is None:
        business_value = DEFAULT_BUSINESS
        assumptions.append('business_assumed')
    else:
        business_value = _check_count('business', business)
        if business_value > 100:
            raise ScoringInputError('business must be within 0-100')
    components['business'] = business_value

    # 缺失分项从权重和中剔除,其余归一化
    available = {key: active_weights[key] for key, value in components.items() if value is not None}
    effective_total = sum(available.values())
    if effective_total <= 0:
        return CpiResult(
            value=None, display_value=None, components=components,
            effective_weights={}, coverage=0.0, provisional=True,
            assumptions=tuple(assumptions + ['no_available_component']),
        )
    effective_weights = {key: weight / effective_total for key, weight in available.items()}
    value = sum(components[key] * weight for key, weight in effective_weights.items())

    # 覆盖率 = 剩余原始权重之和
    coverage = sum(active_weights[key] for key in available)
    provisional = bool(assumptions) or coverage < 1.0 - WEIGHT_SUM_TOLERANCE

    return CpiResult(
        value=value,
        display_value=round_half_up(value),
        components=components,
        effective_weights=effective_weights,
        coverage=coverage,
        provisional=provisional,
        assumptions=tuple(assumptions),
    )
