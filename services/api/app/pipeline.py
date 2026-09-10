"""W11 流水线串联:治理 → 风险扫描 → 分块 → 向量 → 聚类 → 命名 → 发布。

把 W07-W10 的组件接进 W06 调度骨架;命名使用 mock provider(NAMING_MODE=manual
时为确定性占位),待归类(噪声)保留计数,不伪装成已命名主题。
"""
from __future__ import annotations

import os
from typing import Mapping

from .clustering import cluster_embeddings
from .embedding import encode_segments
from .llm import MockTopicProvider, TopicNamer
from .publishing import EvidenceRef, TopicDraft, publish_revision
from .representatives import select_representatives
from .risk_rules import load_policy, scan_risks

POLICY_PATH = os.getenv('RISK_POLICY', 'configs/industry/ecommerce.yaml')


def _flatten_rows(run: Mapping) -> tuple[list[dict], dict[str, str], int]:
    """把 run 的数据集预览行展开为反馈行;返回 (rows, sources, row_offset)。"""
    rows: list[dict] = []
    sources: dict[str, str] = {}
    for dataset in run.get('datasets') or []:
        preview = dataset.get('preview') or {}
        for index, row in enumerate(preview.get('rows') or []):
            feedback_id = str(row.get('feedback_id') or f"fb_{dataset.get('id', 'ds')}_{index}")
            text = ' '.join(str(value) for value in row.values() if value is not None)
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
        evidence = []
        for row in member_rows:
            text = sources[row['feedback_id']]
            quote = text[:min(24, len(text))]
            evidence.append(EvidenceRef(
                feedback_id=row['feedback_id'],
                source_row=row['source_row'],
                quote=quote,
                quote_start=0,
                quote_end=len(quote),
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
                'rule_id': candidate.rule_id,
                'severity': candidate.severity,
                'start': candidate.start,
                'end': candidate.end,
                'reason': candidate.reason,
                'review_state': candidate.review_state,
            })
    return findings


def run_analysis_pipeline(store, analysis_id: str) -> dict:
    """完整流水线:风险扫描 → 分块/向量/聚类/命名 → 发布 revision。"""
    run = store.get_analysis(analysis_id)
    if run is None:
        raise ValueError(f'analysis not found: {analysis_id}')
    rows, sources, total = _flatten_rows(run)
    drafts = build_topics_from_run(run)
    unassigned = total - sum(len(d.evidence) for d in drafts)
    snapshot = publish_revision(store, analysis_id, drafts, sources, unassigned)
    findings = scan_run_risks(run)
    store.update_analysis(analysis_id, {'risk_findings': findings})
    return snapshot
