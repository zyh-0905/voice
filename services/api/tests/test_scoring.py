"""W14 CPI 契约:黄金值、边界、缺失策略、权重校验、整数显示。"""
import pytest

from app.scoring import (
    DEFAULT_WEIGHTS,
    ScoringInputError,
    compute_cpi,
    round_half_up,
    validate_weights,
)


def test_known_cpi_example():
    result = compute_cpi(n1=168, N1=1000, n0=120, N0=1000, severity='high', business=80)
    assert result.value == pytest.approx(67.5)
    assert result.display_value == 68
    assert result.components['growth'] == pytest.approx(40)
    assert result.components['volume'] == pytest.approx(84)
    assert result.components['severity'] == pytest.approx(75)
    assert result.coverage == pytest.approx(1.0)
    assert result.provisional is False


def test_displays_half_up_not_bankers():
    # 67.5 必须显示 68(十进制 HALF_UP)
    result = compute_cpi(n1=168, N1=1000, n0=120, N0=1000, severity='high', business=80)
    assert result.display_value == 68
    # 区分 HALF_UP 与银行家舍入的经典边界:0.5→1、1.5→2、2.5→3(银行家会给 0、2、2)
    assert round_half_up(0.5) == 1
    assert round_half_up(1.5) == 2
    assert round_half_up(2.5) == 3
    assert round_half_up(66.5) == 67


def test_zero_denominator_yields_no_cpi():
    result = compute_cpi(n1=0, N1=0, n0=None, N0=None, severity='high', business=80)
    assert result.value is None
    assert result.display_value is None
    assert 'no_denominator' in result.assumptions


def test_hits_exceeding_denominator_rejected():
    with pytest.raises(ScoringInputError, match='n1 must not exceed N1'):
        compute_cpi(n1=5, N1=3, n0=None, N0=None, severity='high', business=80)
    with pytest.raises(ScoringInputError, match='n0 must not exceed N0'):
        compute_cpi(n1=1, N1=100, n0=5, N0=3, severity='high', business=80)


def test_non_finite_inputs_rejected():
    with pytest.raises(ScoringInputError):
        compute_cpi(n1=1, N1=float('nan'), n0=None, N0=None, severity='high', business=80)
    with pytest.raises(ScoringInputError):
        compute_cpi(n1=1, N1=100, n0=None, N0=None, severity='high', business=float('inf'))
    with pytest.raises(ScoringInputError, match='within 0-100'):
        compute_cpi(n1=1, N1=100, n0=None, N0=None, severity='high', business=150)


def test_missing_history_drops_growth_and_renormalizes():
    result = compute_cpi(n1=168, N1=1000, n0=None, N0=None, severity='high', business=80)
    assert result.components['growth'] is None
    assert 'growth_missing_history' in result.assumptions
    # 覆盖率 = 剩余原始权重(去掉 growth 的 0.30)
    assert result.coverage == pytest.approx(0.70)
    assert result.provisional is True
    # 其余分项按剩余权重归一化:V/S/B 权重和为 0.70
    assert result.effective_weights['volume'] == pytest.approx(0.25 / 0.70)
    # 手工核对:84*0.25/0.7 + 75*0.3/0.7 + 80*0.15/0.7 = 30 + 32.142857 + 17.142857
    assert result.value == pytest.approx(79.2857, abs=1e-3)


def test_low_sample_suppresses_growth():
    # N0 < 50 → 不可用
    result = compute_cpi(n1=10, N1=100, n0=5, N0=49, severity='high', business=80)
    assert result.components['growth'] is None
    assert 'growth_low_sample' in result.assumptions
    # N1 < 50 → 不可用
    assert compute_cpi(n1=5, N1=49, n0=5, N0=100, severity='high', business=80).components['growth'] is None
    # n1 < 5 → 不可用
    result2 = compute_cpi(n1=4, N1=100, n0=2, N0=100, severity='high', business=80)
    assert result2.components['growth'] is None
    assert 'growth_too_few_hits' in result2.assumptions


def test_incomparable_windows_suppress_growth():
    result = compute_cpi(n1=168, N1=1000, n0=120, N0=1000, severity='high', business=80,
                         comparable_windows=False)
    assert result.components['growth'] is None
    assert 'growth_windows_not_comparable' in result.assumptions


def test_zero_previous_share_is_newly_appeared_not_infinite():
    result = compute_cpi(n1=168, N1=1000, n0=0, N0=1000, severity='high', business=80)
    assert result.components['growth'] == pytest.approx(100)
    assert 'growth_newly_appeared' in result.assumptions
    # 0.02 平滑只用于指数,不改变原始数据展示
    assert result.components['growth'] != float('inf')


def test_business_defaults_to_50_with_assumption():
    result = compute_cpi(n1=168, N1=1000, n0=120, N0=1000, severity='high', business=None)
    assert result.components['business'] == pytest.approx(50)
    assert 'business_assumed' in result.assumptions
    assert result.provisional is True
    assert result.coverage == pytest.approx(1.0)  # 默认值仍计入,不降低覆盖率


def test_unknown_severity_is_treated_as_missing():
    result = compute_cpi(n1=168, N1=1000, n0=120, N0=1000, severity='extreme', business=80)
    assert result.components['severity'] is None
    assert 'severity_unknown' in result.assumptions
    assert result.coverage == pytest.approx(0.70)


def test_critical_scores_highest():
    critical = compute_cpi(n1=168, N1=1000, n0=120, N0=1000, severity='CRITICAL', business=80)
    low = compute_cpi(n1=168, N1=1000, n0=120, N0=1000, severity='LOW', business=80)
    assert critical.components['severity'] == 100
    assert low.components['severity'] == 25
    assert critical.value > low.value


def test_custom_weights_change_result():
    result = compute_cpi(n1=168, N1=1000, n0=120, N0=1000, severity='high', business=80,
                         weights={'volume': 0.5, 'growth': 0.2, 'severity': 0.2, 'business': 0.1})
    assert result.value == pytest.approx(0.5 * 84 + 0.2 * 40 + 0.2 * 75 + 0.1 * 80)


def test_weight_validation():
    assert validate_weights(dict(DEFAULT_WEIGHTS))['volume'] == pytest.approx(0.25)
    with pytest.raises(ScoringInputError, match='exactly'):
        validate_weights({'volume': 1.0})
    with pytest.raises(ScoringInputError, match='sum to 1'):
        validate_weights({'volume': 0.5, 'growth': 0.5, 'severity': 0.5, 'business': 0.5})
    with pytest.raises(ScoringInputError, match='non-negative'):
        validate_weights({'volume': -0.25, 'growth': 0.5, 'severity': 0.5, 'business': 0.25})
    with pytest.raises(ScoringInputError, match='finite'):
        validate_weights({'volume': float('nan'), 'growth': 0.5, 'severity': 0.4, 'business': 0.1})


def test_weight_sum_tolerance_accepts_floating_point_noise():
    noisy = {'volume': 0.25 + 1e-9, 'growth': 0.30, 'severity': 0.30, 'business': 0.15}
    assert validate_weights(noisy)['volume'] == pytest.approx(0.25)
