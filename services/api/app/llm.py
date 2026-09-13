"""W10 LLM 适配:provider 接口、修复一次、超时/预算降级、manual 命名模式。

mock 与 provider 实现同一接口,origin 分别记录(provider/mock/rule_fallback/manual);
命名失败降级为「待确认主题 01」+ 规则摘要,不生成看似真实的引用。
"""
from __future__ import annotations

import os
import re
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
# 异常定义在 provider 侧(它要抛),这里再导出一次:`from .llm import LLMTimeoutError`
# 的既有调用方不必改,而两边也不会各定义一份导致 except 漏接。
from .topic_provider import (  # noqa: F401  (re-exported)
    BudgetExceededError,
    BudgetGuard,
    CallUsage,
    HTTPTopicProvider,
    LLMTimeoutError,
)

FALLBACK_TOPIC_NAME = '待确认主题 01'
NAMING_MODES = ('mock', 'provider', 'manual')


class TopicProvider(Protocol):
    """命名阶段 provider:返回待 schema 校验的原始输出。"""

    origin: str

    def name_topic(self, evidence: Sequence[Mapping[str, str]], context: Mapping[str, object]) -> object: ...


@dataclass
class MockTopicProvider:
    """确定性 mock:输出契约合法且引文真实存在于证据原文;主题名由证据高频词生成。"""

    origin: str = 'mock'

    def name_topic(self, evidence: Sequence[Mapping[str, str]], context: Mapping[str, object]) -> dict:
        rows = list(evidence)
        first = rows[0] if rows else {'evidence_id': 'fb_missing', 'text': '占位证据'}
        text = ' '.join(row.get('text', '') for row in rows)
        quote = first['text'][:12]
        return {
            'topic_name': _deterministic_name(text),
            'summary': f'证据共 {len(rows)} 条,聚焦 {_deterministic_name(text)} 相关反馈。',
            'severity': 'medium',
            'department': '运营',
            'evidence_ids': [row['evidence_id'] for row in rows] or ['fb_missing'],
            'claims': [{'evidence_id': first['evidence_id'], 'quote': quote, 'claim': f'反馈提及:{quote}'}],
            'suggested_action': '核验相关流程机制',
            'needs_review': True,
            'limitations': ['演示输出,需人工核验'],
        }


def _deterministic_name(text: str) -> str:
    """确定性命名:去掉标点/空白后取前 4 个字符;空文本用占位名。

    演示 mock 的稳定命名策略——不同证据簇得到不同且可读的名字;
    真实命名由 TopicProvider 实现(见 contracts/llm_topic.schema.json)。
    """
    cleaned = re.sub(r'[\s，。！？、；：""''（）【】,;:!?.]+', '', text)
    if not cleaned:
        return FALLBACK_TOPIC_NAME
    return cleaned[:4]


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


def resolve_naming_mode() -> str:
    """14.1:mock / provider / manual。未知值按 mock 处理并保持可观测。

    定义在 `TopicNamer` 之前:字段的 `default_factory` 在类定义时求值,
    放到后面会 NameError——而那只在导入时炸,看起来像别的模块出了问题。
    """
    value = (os.getenv('NAMING_MODE') or 'mock').strip().lower()
    return value if value in NAMING_MODES else 'mock'


@dataclass
class TopicNamer:
    """编排 provider → schema 校验 → 证据校验 → 一次修复 → 降级。

    `last_call` 记录**每一次**命名尝试的记账信息,包括超时、结构失败与降级:
    10.5 要求 UNKNOWN 调用也有记录,只统计成功调用会让预算低估超时与重试的开销。
    没有发起调用的路径(mock/manual/预算禁用)也留一条,state 说明为什么。
    """

    provider: TopicProvider
    allowed_evidence: Mapping[str, str]
    naming_mode: str = field(default_factory=resolve_naming_mode)
    spent_today: float | None = None
    _manual_counter: int = 0
    last_call: CallUsage | None = None

    def _usage(self, state: str) -> CallUsage:
        """优先取 provider 自报的用量(它知道 tokens 与请求 id)。"""
        reported = getattr(self.provider, 'last_usage', None)
        usage = reported if reported is not None else CallUsage(provider=self.naming_mode)
        usage.state = state
        return usage

    def name_topic(self, evidence: Sequence[Mapping[str, str]], context: Mapping[str, object] | None = None) -> TopicCandidate:
        context = dict(context or {})
        if self.spent_today is not None:
            context.setdefault('spent_today', self.spent_today)
        if self.naming_mode == 'manual':
            # 确定性占位/规则候选,不调用模型;保留真实向量与聚类,等待人工命名
            self._manual_counter += 1
            self.last_call = CallUsage(provider='manual', state='SKIPPED_MANUAL')
            return _rule_fallback(evidence, 'manual 模式,未调用模型')
        if self.naming_mode == 'mock':
            self.last_call = CallUsage(provider='mock', state='SKIPPED_MOCK')
        try:
            raw = self.provider.name_topic(evidence, context)
        except LLMTimeoutError as exc:
            self.last_call = self._usage('TIMEOUT')
            return _rule_fallback(evidence, type(exc).__name__)
        except BudgetExceededError as exc:
            self.last_call = self._usage('BUDGET_EXCEEDED')
            return _rule_fallback(evidence, f'{type(exc).__name__}: {exc}')
        except Exception as exc:  # 供应商侧的任何失败都不能让整个 run 崩掉
            self.last_call = self._usage('ERROR')
            return _rule_fallback(evidence, f'{type(exc).__name__}: {exc}')
        # mock 产出不是模型调用:记成 SUCCESS 会让 model_calls 里混进一批
        # 从未发生的「成功调用」,而预算与成本口径都建立在这张表上。
        self.last_call = self._usage('MOCK' if self.naming_mode == 'mock' else 'SUCCESS')
        try:
            candidate = validate_schema(raw)
        except InvalidLLMOutput as exc:
            # 结构失败仍是一次**真实发生**的调用:用量要记账(8.5 要求修复重试一次)
            self.last_call.state = 'SCHEMA_INVALID'
            return _rule_fallback(evidence, f'输出不满足契约: {exc}')
        # origin 是服务层元数据,不在 LLM 输出契约内,由 provider 声明
        candidate.origin = getattr(self.provider, 'origin', 'provider')
        try:
            return validate_candidate(candidate, self.allowed_evidence)
        except InvalidEvidence as exc:
            repaired = repair_once(candidate, self.allowed_evidence)
            try:
                return validate_candidate(repaired, self.allowed_evidence)
            except InvalidEvidence as inner:
                self.last_call.state = 'EVIDENCE_INVALID'
                return _rule_fallback(evidence, f'修复后仍失败: {inner}')


def make_namer(allowed_evidence: Mapping[str, str], *, spent_today: float | None = None) -> TopicNamer:
    """按 NAMING_MODE 造命名器。生产环境禁止 mock(14.1),由 settings 在启动时拦截。"""
    mode = resolve_naming_mode()
    if mode == 'provider':
        provider = HTTPTopicProvider.from_env()
        if provider is None:
            # 说了用 provider 却没有配 MODEL_ENDPOINT / MODEL_ID:降级到人工命名并
            # 在每次尝试里记明原因,而不是悄悄用 mock 冒充「已接入模型」。
            return TopicNamer(provider=MockTopicProvider(), allowed_evidence=allowed_evidence,
                              naming_mode='manual', spent_today=spent_today)
        return TopicNamer(provider=provider, allowed_evidence=allowed_evidence,
                          naming_mode='provider', spent_today=spent_today)
    if mode == 'manual':
        return TopicNamer(provider=MockTopicProvider(), allowed_evidence=allowed_evidence,
                          naming_mode='manual', spent_today=spent_today)
    return TopicNamer(provider=MockTopicProvider(), allowed_evidence=allowed_evidence,
                      naming_mode='mock', spent_today=spent_today)


def make_mock_namer(allowed_evidence: Mapping[str, str]) -> TopicNamer:
    return TopicNamer(provider=MockTopicProvider(), allowed_evidence=allowed_evidence,
                      naming_mode='mock')
