"""W17 同口径计算:黄金样本、零分母不可比、不输出改善结论。"""
import pytest

from app.review_metrics import compare_counts, effect_status


def test_smaller_count_can_have_higher_share():
    result = compare_counts(100, 1000, 80, 500)
    assert result.count_change == -20
    assert result.share_delta_pp == pytest.approx(6.0)
    assert result.relative_share_change == pytest.approx(0.6)


def test_golden_share_example():
    result = compare_counts(168, 1000, 102, 1000)
    assert result.share_before_pp == pytest.approx(16.8)
    assert result.share_after_pp == pytest.approx(10.2)
    assert result.share_delta_pp == pytest.approx(-6.6)
    assert result.relative_share_change == pytest.approx(-0.3929, abs=0.001)


def test_zero_denominator_not_comparable():
    result = compare_counts(0, 0, 5, 10)
    assert result.comparable is False
    assert result.share_delta_pp is None
    assert effect_status(result) == 'INSUFFICIENT_DATA'


def test_comparable_is_descriptive_not_causal():
    result = compare_counts(10, 100, 5, 100)
    assert result.comparable is True
    assert effect_status(result) == 'OBSERVED_CHANGE'


def test_relative_change_none_when_before_share_zero():
    result = compare_counts(0, 100, 5, 100)
    assert result.relative_share_change is None
    assert result.share_delta_pp == pytest.approx(5.0)
