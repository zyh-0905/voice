"""W11 流水线串联:治理 → 风险扫描 → 分块 → 向量 → 聚类 → 命名 → 发布。

把 W07-W10 的组件接进 W06 调度骨架;命名使用 mock provider(NAMING_MODE=manual
时为确定性占位),待归类(噪声)保留计数,不伪装成已命名主题。
"""
from __future__ import annotations

import os
from typing import Mapping

from .clustering import cluster_embeddings
from .ingestion import row_text
from .embedding import encode_segments
from .llm import MockTopicProvider, TopicNamer
from .publishing import EvidenceRef, TopicDraft, publish_revision
from .representatives import select_representatives
from .risk_rules import load_policy, scan_risks
from .segments import split_redacted

POLICY_PATH = os.getenv('RISK_POLICY', 'configs/industry/ecommerce.yaml')
# 没有模型 claim 时引文的字符上限;分块器按句切分,超预算的单句退化为有界切片
_QUOTE_FALLBACK_CHARS = 80


def _resolve_quote(text: str, claimed: str | None) -> tuple[str, int, int]:
    """确定证据引文的文本与 offset。

    优先用命名阶段产出的 claim:它引用的是**支持该结论的那一句**,而且
    `validate_candidate` 已经校验过它是本证据正文的精确子串。没有 claim 时才退化为
    首个真实句段(走 W07 分块器)。

    两者都保证 `text[start:end] == quote`——publishing 会据此校验后发布。
    **不返回 `text[:24]` 这类与结论无关的前缀**:那种引文能通过格式校验,却让
    「每条结论可定位源反馈」在语义上落空。
    """
    if claimed:
        start = text.find(claimed)
        if start >= 0:
            return claimed, start, start + len(claimed)
    if not text:
        return '', 0, 0
    try:
        spans = split_redacted(text, max_tokens=_QUOTE_FALLBACK_CHARS, overlap=0)
    except ValueError:
        # 整段没有句读且超预算:退化为有界切片,仍是正文的真实片段
        spans = []
    if spans:
        span = spans[0]
        return span.text, span.start, span.end
    end = min(_QUOTE_FALLBACK_CHARS, len(text))
    return text[:end], 0, end


def _flatten_rows(run: Mapping) -> tuple[list[dict], dict[str, str], int]:
    """把 run 的数据集预览行展开为反馈行;返回 (rows, sources, row_offset)。"""
    rows: list[dict] = []
    sources: dict[str, str] = {}
    for dataset in run.get('datasets') or []:
        preview = dataset.get('preview') or {}
        for index, row in enumerate(preview.get('rows') or []):
            feedback_id = str(row.get('feedback_id') or f"fb_{dataset.get('id', 'ds')}_{index}")
            # 与证据源端点共用同一份正文口径,否则引文 offset 在两处对不上
            text = row_text(row)
            rows.append({'feedback_id': feedback_id, 'text': text, 'source_row': index})
            sources[feedback_id] = text
    return rows, sources, len(rows)


def build_topics_from_run(run: Mapping) -> list[TopicDraft]:
    """簇/候选 → 主题草稿:真实向量+聚类,命名走 mock/规则,引用精确可校验。"""
    rows, sources, _ = _flatten_rows(run)
    if not rows:
        return []
    vectors = encode_segments([row['text'] for row in rows])
    result = cluster_embeddings(vectors, 'hdbscan', {'min_cluster_size': 2, 'min_samples': 1})
    drafts: list[TopicDraft] = []
    namer = TopicNamer(MockTopicProvider(), sources)
    labels = result.labels
    cluster_ids = sorted({int(label) for label in labels if label != -1})
    for cluster_id in cluster_ids:
        members = [i for i, label in enumerate(labels) if int(label) == cluster_id]
        member_rows = [rows[i] for i in members]
        representatives = select_representatives(
            [rows[i]['feedback_id'] for i in members],
            vectors[members],
            limit=3,
        )
        representative_rows = [row for row in member_rows if row['feedback_id'] in representatives]
        candidate = namer.name_topic(
            [{'evidence_id': row['feedback_id'], 'text': row['text']} for row in representative_rows],
        )
        # 命名阶段返回的 claims 是「引用了哪条证据」的权威来源,按证据 id 取用
        claimed = {claim.evidence_id: claim.quote for claim in candidate.claims}
        evidence = []
        for row in member_rows:
            quote, quote_start, quote_end = _resolve_quote(
                sources[row['feedback_id']], claimed.get(row['feedback_id']),
            )
            evidence.append(EvidenceRef(
                feedback_id=row['feedback_id'],
                source_row=row['source_row'],
                quote=quote,
                quote_start=quote_start,
                quote_end=quote_end,
            ))
        drafts.append(TopicDraft(
            topic_id=f'topic-{cluster_id + 1}',
            name=candidate.topic_name,
            summary=candidate.summary,
            severity=candidate.severity,
            evidence=evidence,
        ))
    return drafts


def scan_run_risks(run: Mapping) -> list[dict]:
    """独立风险扫描(W08)接入:治理后全量扫描,独立于向量与聚类。"""
    policy = load_policy(POLICY_PATH)
    rows, sources, _ = _flatten_rows(run)
    findings = []
    for row in rows:
        for candidate in scan_risks(row['feedback_id'], sources[row['feedback_id']], policy):
            findings.append({
                'feedback_id': row['feedback_id'],
                'source_row': row['source_row'],
                'rule_id': candidate.rule_id,
                # 策略版本随产物一起落库:计划 5.2 的唯一性是 (feedback_id, rule_id,
                # policy_version),换策略后同一对允许再有一条候选
                'policy_version': policy.policy_id,
                'severity': candidate.severity,
                'start': candidate.start,
                'end': candidate.end,
                'reason': candidate.reason,
                'review_state': candidate.review_state,
            })
    return findings


def run_analysis_pipeline(store, analysis_id: str, repository=None) -> dict:
    """完整流水线:风险扫描 → 分块/向量/聚类/命名 → 发布 revision。

    `repository` 用于把风险候选写进项目复核队列;不传则只算不写(纯计算场景)。
    """
    run = store.get_analysis(analysis_id)
    if run is None:
        raise ValueError(f'analysis not found: {analysis_id}')
    rows, sources, total = _flatten_rows(run)
    drafts = build_topics_from_run(run)
    unassigned = total - sum(len(d.evidence) for d in drafts)
    snapshot = publish_revision(store, analysis_id, drafts, sources, unassigned)
    findings = scan_run_risks(run)
    store.update_analysis(analysis_id, {'risk_findings': findings})
    # 扫描独立于聚类,所以候选在主题发布之后单独入队(计划 8.1:1 条严重投诉即使
    # 不成簇也要进复核队列)
    if repository is not None:
        from .risk_service import persist_findings
        persist_findings(repository, run.get('project_id'), findings)
    return snapshot
