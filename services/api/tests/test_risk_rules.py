"""W08 契约:单条严重投诉不成簇也入队;候选不是既成事实;否定/假设/转述不误报。"""
import pytest

from app.risk_rules import load_policy, scan_risks
from app.risk_service import dedupe, scan_rows

POLICY = load_policy('configs/industry/ecommerce.yaml')


def test_single_safety_case_is_not_dropped():
    candidates = scan_risks('fb_safety_1', '插电时突然起火，手部被烫伤。', POLICY)
    assert any(c.severity == 'critical' for c in candidates)
    assert all(c.review_state == 'PENDING' for c in candidates)
    # 两条 critical 规则都应命中(起火 + 烫伤),任何一条都不能被离群过滤
    rule_ids = {c.rule_id for c in candidates}
    assert {'safety_fire', 'safety_injury'} <= rule_ids


def test_negation_is_not_reported():
    candidates = scan_risks('fb_neg', '设备没有起火，只是温度偏高。', POLICY)
    assert all(c.rule_id != 'safety_fire' for c in candidates)


def test_hypothetical_is_not_reported():
    candidates = scan_risks('fb_hypo', '如果起火会怎么样？请说明。', POLICY)
    assert all(c.rule_id != 'safety_fire' for c in candidates)


def test_hearsay_is_not_reported():
    candidates = scan_risks('fb_hear', '听说别人家产品起火了，我想确认一下。', POLICY)
    assert all(c.rule_id != 'safety_fire' for c in candidates)


def test_guard_does_not_swallow_real_hit():
    # 排除词只作用于命中词前 6 字符窗口,不误伤同句中的真实命中
    candidates = scan_risks('fb_real', '包裹没有破损，但设备起火了。', POLICY)
    assert any(c.rule_id == 'safety_fire' for c in candidates)


def test_same_rule_deduplicated_across_patterns():
    candidates = scan_risks('fb_dup', '支付失败，之后付款失败重试也不行。', POLICY)
    payment = [c for c in candidates if c.rule_id == 'payment_failed']
    assert len(payment) == 1


def test_critical_sorted_first():
    candidates = scan_risks('fb_order', '支付失败，另外设备还起火了。', POLICY)
    assert candidates
    assert candidates[0].severity == 'critical'


def test_offsets_are_unicode_accurate():
    text = '使用时😀被烫伤了。'
    candidates = scan_risks('fb_off', text, POLICY)
    injury = next(c for c in candidates if c.rule_id == 'safety_injury')
    assert text[injury.start:injury.end] == '烫伤'


def test_no_hits_returns_empty():
    assert scan_risks('fb_none', '物流速度一般，希望改进。', POLICY) == []


def test_load_policy_requires_policy_id(tmp_path):
    policy_file = tmp_path / 'no-id-policy.yaml'
    policy_file.write_text('rules: []\n', encoding='utf-8')
    with pytest.raises(ValueError):
        load_policy(str(policy_file))


def test_scan_rows_aggregates_and_dedupes():
    rows = [
        {'feedback_id': 'fb-1', 'text': '设备起火了。'},
        {'feedback_id': 'fb-1', 'text': '设备冒烟了。'},
        {'feedback_id': 'fb-2', 'text': '支付失败。'},
    ]
    records = scan_rows(rows, POLICY)
    fire_records = [r for r in records if r.candidate.rule_id == 'safety_fire']
    assert len(fire_records) == 1
    assert fire_records[0].feedback_id == 'fb-1'
    # 幂等去重不再减少
    assert dedupe(records) == records
