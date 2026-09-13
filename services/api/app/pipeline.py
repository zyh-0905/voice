"""W11 流水线串联:治理 → 风险扫描 → 分块 → 向量 → 聚类 → 命名 → 发布。

把 W07-W10 的组件接进 W06 调度骨架;命名使用 mock provider(NAMING_MODE=manual
时为确定性占位),待归类(噪声)保留计数,不伪装成已命名主题。
"""
from __future__ import annotations

import os
from typing import Mapping

from .clustering import cluster_embeddings
from .embedding import encode_segments
from .ingestion import run_feedback
from .llm import MockTopicProvider, TopicNamer
from .ingestion import REDACTION_VERSION
from .publishing import EvidenceRef, TopicDraft, publish_revision
from .representatives import select_representatives
from .risk_rules import load_policy, scan_risks
from .segments import split_redacted

POLICY_PATH = os.getenv('RISK_POLICY', 'configs/industry/ecommerce.yaml')
# 没有模型 claim 时引文的字符上限;分块器按句切分,超预算的单句退化为有界切片
_QUOTE_FALLBACK_CHARS = 80
# 工程计划 8.2:每块上限 384 tokens,相邻长块重叠 64 tokens。
# 这里用字符计数近似 token(中文一字一 token),是首版的工程约定,不是精度声明。
SEGMENT_MAX_TOKENS = 384
SEGMENT_OVERLAP = 64


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


def _flatten_rows(run: Mapping, repository) -> tuple[list[dict], dict[str, str], int]:
    """展开 run 的输入反馈;返回 (rows, sources, total)。

    取数走 `feedback` 实体表(工程计划 5.2),不再读 run 里内嵌的 JSON 副本:
    反馈正文此前在 `datasets.governance` 与 `analysis_runs.result` 各存一份,
    两份都可能与另一份不一致,而没有任何东西会发现。

    输入按 run 创建时冻结的 `run_feedback_ids` 取(5.3「输入固定」):之后再导入的
    反馈不会隐式扩展这个 run 的输入。早于 0014 的 run 没有这个字段,回退到按
    dataset_ids 取——那批 run 的输入本来就没有冻结过,迁移无法凭空补出正确的集合。
    """
    rows = run_feedback(run, repository)
    flattened: list[dict] = []
    sources: dict[str, str] = {}
    for row in rows:
        feedback_id = str(row['id'])
        # 正文是库里那一份;它与证据源查询、导出共用同一口径,offset 才对得上
        text = str(row.get('content_redacted') or '')
        flattened.append({'feedback_id': feedback_id, 'text': text,
                          'source_row': int(row.get('source_row') or 0)})
        sources[feedback_id] = text
    return flattened, sources, len(flattened)


def build_topics_from_run(run: Mapping, repository) -> list[TopicDraft]:
    """簇/候选 → 主题草稿:真实向量+聚类,命名走 mock/规则,引用精确可校验。"""
    rows, sources, _ = _flatten_rows(run, repository)
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


def scan_run_risks(run: Mapping, repository) -> list[dict]:
    """独立风险扫描(W08)接入:治理后全量扫描,独立于向量与聚类。"""
    policy = load_policy(POLICY_PATH)
    rows, sources, _ = _flatten_rows(run, repository)
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


def persist_segments(repository, project_id: str, rows: list[dict]) -> int:
    """把一个 run 的输入分块落进 segments 表(工程计划 8.1 的「分块」阶段产物)。

    分块只在这里产生。此前 `split_redacted` 只有证据源查询与引文兜底在调用,
    `segments` 表并不存在,「offset 指向脱敏正文的 Unicode 位置」这条 8.2 的约定
    因此没有持久载体,每次读取都要按**当时**的参数重算。

    单句超过 token 预算时分块器会拒绝而不是硬切:那种行记 0 块(与
    `_resolve_quote` 同一处理),不会被静默截断后声称覆盖全文。
    """
    written = 0
    for row in rows:
        try:
            spans = split_redacted(row['text'], max_tokens=SEGMENT_MAX_TOKENS, overlap=SEGMENT_OVERLAP)
        except ValueError:
            spans = []
        written += repository.replace_segments(project_id, row['feedback_id'], spans, REDACTION_VERSION)
    return written


def run_analysis_pipeline(store, analysis_id: str, repository=None) -> dict:
    """完整流水线:风险扫描 → 分块/向量/聚类/命名 → 发布 revision。

    `repository` 既是反馈正文的取数来源(`feedback` 实体表),也用于把风险候选
    写进项目复核队列。流水线依赖真实仓储,所以不提供「无仓储」的纯计算降级:
    那种降级会走一条与生产不同、且没有任何东西在读的路径。
    """
    if repository is None:
        raise ValueError('run_analysis_pipeline requires a repository')
    run = store.get_analysis(analysis_id)
    if run is None:
        raise ValueError(f'analysis not found: {analysis_id}')
    rows, sources, total = _flatten_rows(run, repository)
    persist_segments(repository, run.get('project_id'), rows)
    drafts = build_topics_from_run(run, repository)
    unassigned = total - sum(len(d.evidence) for d in drafts)
    snapshot = publish_revision(store, analysis_id, drafts, sources, unassigned)
    findings = scan_run_risks(run, repository)
    store.update_analysis(analysis_id, {'risk_findings': findings})
    # 扫描独立于聚类,所以候选在主题发布之后单独入队(计划 8.1:1 条严重投诉即使
    # 不成簇也要进复核队列)
    from .risk_service import persist_findings
    persist_findings(repository, run.get('project_id'), findings)
    return snapshot
