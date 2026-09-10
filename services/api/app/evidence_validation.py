"""W10 证据校验:合法 JSON → schema → evidence_id 白名单 → quote 精确子串 → claim 对应。

没有有效证据的模型输出不能变成已确认主题;降级来源(origin)在界面可见。
"""
from __future__ import annotations

import json
import os
from typing import Literal, Mapping

import jsonschema
from pydantic import BaseModel, ConfigDict, Field

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), '..', 'contracts', 'llm_topic.schema.json')


class InvalidLLMOutput(ValueError):
    """LLM 原始输出不是合法 JSON 或不满足 schema 契约。"""


class InvalidEvidence(ValueError):
    """候选引用了白名单之外的证据,或 quote 不是证据原文的精确子串。"""


class Claim(BaseModel):
    model_config = ConfigDict(extra='forbid')
    evidence_id: str = Field(min_length=1)
    quote: str = Field(min_length=1, max_length=200)
    claim: str = Field(min_length=1, max_length=200)


class TopicCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    topic_name: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=2000)
    severity: Literal['low', 'medium', 'high', 'critical']
    department: str = Field(default='', max_length=80)
    evidence_ids: list[str] = Field(min_length=1)
    claims: list[Claim] = Field(default_factory=list)
    suggested_action: str = Field(default='', max_length=500)
    needs_review: bool = True
    limitations: list[str] = Field(default_factory=list, max_length=20)
    # 服务层元数据(不在 LLM 输出契约内):provider / mock / rule_fallback / manual
    origin: str = 'provider'


def load_schema() -> dict:
    with open(os.path.abspath(_SCHEMA_PATH), encoding='utf-8') as handle:
        return json.load(handle)


def validate_schema(raw: object) -> TopicCandidate:
    """合法 JSON 与 schema 契约校验;违反抛 InvalidLLMOutput。"""
    try:
        jsonschema.validate(raw, load_schema())
    except jsonschema.ValidationError as exc:
        raise InvalidLLMOutput(f'schema violation: {exc.message}') from exc
    except jsonschema.SchemaError as exc:
        raise InvalidLLMOutput(f'invalid schema: {exc}') from exc
    try:
        return TopicCandidate.model_validate(raw)
    except ValueError as exc:
        raise InvalidLLMOutput(f'candidate invalid: {exc}') from exc


def validate_candidate(candidate: TopicCandidate, allowed_evidence: Mapping[str, str]) -> TopicCandidate:
    """evidence_id 白名单 + quote 精确子串 + claim 证据 ID 与 quote ID 对应。

    allowed_evidence: evidence_id → 脱敏正文。quote 使用 Unicode 子串匹配,
    不执行引文中的任何链接、脚本或指令。
    """
    # 防御:model_copy(update=...) 不会重新验证,重建以保证 claims 为模型实例
    candidate = TopicCandidate.model_validate(candidate.model_dump())
    for evidence_id in candidate.evidence_ids:
        if evidence_id not in allowed_evidence:
            raise InvalidEvidence(f'evidence_id not allowed: {evidence_id}')
    for claim in candidate.claims:
        if claim.evidence_id not in allowed_evidence:
            raise InvalidEvidence(f'claim references foreign evidence: {claim.evidence_id}')
        if claim.evidence_id not in candidate.evidence_ids:
            raise InvalidEvidence(f'claim evidence_id not listed: {claim.evidence_id}')
        text = allowed_evidence[claim.evidence_id]
        if claim.quote not in text:
            raise InvalidEvidence(f'quote not found in evidence {claim.evidence_id}: {claim.quote[:40]}...')
    return candidate


def repair_once(candidate: TopicCandidate, allowed_evidence: Mapping[str, str]) -> TopicCandidate:
    """丢弃无法通过证据校验的 claim(一次修复);evidence_ids 本身非法时无法修复。"""
    valid_claims = [
        claim for claim in candidate.claims
        if claim.evidence_id in allowed_evidence
        and claim.evidence_id in candidate.evidence_ids
        and claim.quote in allowed_evidence[claim.evidence_id]
    ]
    return candidate.model_copy(update={'claims': valid_claims})
