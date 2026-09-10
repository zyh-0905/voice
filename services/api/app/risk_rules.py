"""W08 独立风险扫描:全量规则扫描,独立于向量与聚类。

候选 review_state 恒为 PENDING——风险候选不是既成事实,确认需人工裁决;
否定/假设/转述(guards 排除词出现在命中词前 6 字符窗口)不产生候选。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

import yaml

_SEVERITY_ORDER = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
_SENTENCE_END = re.compile(r'[。！？!?；;\n]')
# 转折/列举分隔切断排除词的修饰作用域:「没有破损,但起火」中的「没有」不算否定
_TURN_SEPARATORS = re.compile(r'[，,、;但不过然而]')


@dataclass(frozen=True)
class RiskRule:
    rule_id: str
    severity: str
    patterns: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class RiskPolicy:
    policy_id: str
    rules: tuple[RiskRule, ...]
    guards: tuple[str, ...] = ()


@dataclass(frozen=True)
class RiskCandidate:
    rule_id: str
    severity: str
    start: int
    end: int
    reason: str
    review_state: str = 'PENDING'


def _resolve_path(path: str) -> str:
    # 相对仓库根与 services/api/ 两种布局均可解析
    for candidate in (path, os.path.join('services/api', path)):
        if os.path.exists(candidate):
            return candidate
    raise FileNotFoundError(f'policy file not found: {path}')


def load_policy(path: str) -> RiskPolicy:
    with open(_resolve_path(path), encoding='utf-8') as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict) or not raw.get('policy_id'):
        raise ValueError('policy must declare policy_id')
    rules = tuple(
        RiskRule(
            rule_id=str(item['rule_id']),
            severity=str(item.get('severity', 'medium')).lower(),
            patterns=tuple(str(p) for p in (item.get('patterns') or [])),
            reason=str(item.get('reason', '')),
        )
        for item in (raw.get('rules') or [])
        if isinstance(item, dict) and item.get('rule_id')
    )
    guards = tuple(str(g) for g in (raw.get('guards') or []))
    return RiskPolicy(policy_id=str(raw['policy_id']), rules=rules, guards=guards)


def _sentence_span(text: str, index: int) -> tuple[int, int]:
    """返回包含 index 的句子区间(句末标点归属前句)。"""
    start, end = 0, len(text)
    for match in _SENTENCE_END.finditer(text):
        if match.end() <= index:
            start = match.end()
        else:
            end = match.end()
            break
    return start, end


def _guarded(text: str, pattern_start: int, guards: tuple[str, ...]) -> bool:
    """命中词所在句内、最近语义片段(转折分隔后的尾段)含排除词 → 否定/假设/转述,不产生候选。

    - 「没有起火」→ 尾段含「没有」,排除
    - 「包裹没有破损,但设备起火」→ 转折切断,尾段「设备」不含,照常命中
    - 「听说别人家产品起火」→ 尾段含「听说」,排除
    """
    if not guards:
        return False
    sent_start, _ = _sentence_span(text, pattern_start)
    prefix = text[sent_start:pattern_start]
    nearest = _TURN_SEPARATORS.split(prefix)[-1]
    return any(guard in nearest for guard in guards)


def scan_risks(feedback_id: str, text: str, policy: RiskPolicy) -> list[RiskCandidate]:
    """扫描一条反馈的全部规则命中;同规则去重、critical 置顶、恒 PENDING。

    feedback_id 保留为契约签名(与 W11 发布事务的关联字段一致);
    候选 offset 为 Unicode 字符索引(text[start:end] 即命中文本)。
    """
    candidates: list[RiskCandidate] = []
    seen_rules: set[str] = set()
    for rule in policy.rules:
        if rule.rule_id in seen_rules:
            continue
        for pattern in rule.patterns:
            if not pattern:
                continue
            for match in re.finditer(re.escape(pattern), text):
                if _guarded(text, match.start(), policy.guards):
                    continue
                if rule.rule_id in seen_rules:
                    continue
                seen_rules.add(rule.rule_id)
                candidates.append(RiskCandidate(
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    start=match.start(),
                    end=match.end(),
                    reason=rule.reason,
                ))
    candidates.sort(key=lambda c: (_SEVERITY_ORDER.get(c.severity, 9), c.start))
    return candidates
