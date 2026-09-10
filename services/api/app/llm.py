"""W10 LLM 适配:provider 接口、修复一次、超时/预算降级、manual 命名模式。

mock 与 provider 实现同一接口,origin 分别记录(provider/mock/rule_fallback/manual);
命名失败降级为「待确认主题 01」+ 规则摘要,不生成看似真实的引用。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping, Protocol, Sequence

from .evidence_validation import (
    InvalidEvidence,
    InvalidLLMOutput,
    TopicCandidate,
    repair_once,
    validate_candidate,
    validate_schema,
)

FALLBACK_TOPIC_NAME = '待确认主题 01'


class LLMTimeoutError(RuntimeError):
    """供应商超时。"""


class BudgetExceededError(RuntimeError):
    """预算耗尽。"""


class TopicProvider(Protocol):
    """命名阶段 provider:返回待 schema 校验的原始输出。"""

    origin: str

    def name_topic(self, evidence: Sequence[Mapping[str, str]], context: Mapping[str, object]) -> object: ...


@dataclass
class MockTopicProvider:
    """确定性 mock:输出契约合法且引文真实存在于证据原文。"""

    origin: str = 'mock'

    def name_topic(self, evidence: Sequence[Mapping[str, str]], context: Mapping[str, object]) -> dict:
        rows = list(evidence)
        first = rows[0] if rows else {'evidence_id': 'fb_missing', 'text': '占位证据'}
        quote = first['text'][:12]
        return {
            'topic_name': '物流体验',
            'summary': f'证据共 {len(rows)} 条,聚焦物流更新与配送等待。',
            'severity': 'medium',
            'department': '运营',
            'evidence_ids': [row['evidence_id'] for row in rows] or ['fb_missing'],
            'claims': [{'evidence_id': first['evidence_id'], 'quote': quote, 'claim': f'反馈提及:{quote}'}],
            'suggested_action': '核验物流通知机制',
            'needs_review': True,
            'limitations': ['演示输出,需人工核验'],
        }


def _rule_fallback(evidence: Sequence[Mapping[str, str]], reason: str) -> TopicCandidate:
    """规则降级:确定性占位名与摘要,不伪造引用。"""
    rows = list(evidence)
    total_chars = sum(len(row.get('text', '')) for row in rows)
    return TopicCandidate(
        topic_name=FALLBACK_TOPIC_NAME,
        summary=f'共 {len(rows)} 条证据、{total_chars} 字符,等待人工命名。',
        severity='medium',
        department='',
        evidence_ids=[row['evidence_id'] for row in rows] or ['fb_missing'],
        claims=[],
        suggested_action='',
        needs_review=True,
        limitations=[f'降级: {reason};不生成未经核验的引用。'],
        origin='rule_fallback',
    )


@dataclass
class TopicNamer:
    """编排 provider → schema 校验 → 证据校验 → 一次修复 → 降级。"""

    provider: TopicProvider
    allowed_evidence: Mapping[str, str]
    naming_mode: str = field(default_factory=lambda: os.getenv('NAMING_MODE', 'llm'))
    _manual_counter: int = 0

    def name_topic(self, evidence: Sequence[Mapping[str, str]], context: Mapping[str, object] | None = None) -> TopicCandidate:
        context = context or {}
        if self.naming_mode == 'manual':
            # 确定性占位/规则候选,不调用模型;保留真实向量与聚类,等待人工命名
            self._manual_counter += 1
            return _rule_fallback(evidence, 'manual 模式,未调用模型')
        try:
            raw = self.provider.name_topic(evidence, context)
        except (LLMTimeoutError, BudgetExceededError) as exc:
            return _rule_fallback(evidence, type(exc).__name__)
        try:
            candidate = validate_schema(raw)
        except InvalidLLMOutput as exc:
            return _rule_fallback(evidence, f'输出不满足契约: {exc}')
        # origin 是服务层元数据,不在 LLM 输出契约内,由 provider 声明
        candidate.origin = getattr(self.provider, 'origin', 'provider')
        try:
            return validate_candidate(candidate, self.allowed_evidence)
        except InvalidEvidence:
            repaired = repair_once(candidate, self.allowed_evidence)
            try:
                return validate_candidate(repaired, self.allowed_evidence)
            except InvalidEvidence as exc:
                return _rule_fallback(evidence, f'修复后仍失败: {exc}')


def make_mock_namer(allowed_evidence: Mapping[str, str]) -> TopicNamer:
    return TopicNamer(provider=MockTopicProvider(), allowed_evidence=allowed_evidence)
