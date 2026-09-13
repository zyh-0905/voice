"""W11 流水线串联:治理 → 风险扫描 → 分块 → 向量 → 聚类 → 命名 → 发布。

把 W07-W10 的组件接进 W06 调度骨架;命名使用 mock provider(NAMING_MODE=manual
时为确定性占位),待归类(噪声)保留计数,不伪装成已命名主题。
"""
from __future__ import annotations

import os
from typing import Mapping

from .clustering import cluster_embeddings
from .embedding_provider import encode_texts, resolve_embedding_provider
from .ingestion import run_feedback
from .llm import CallUsage, make_namer
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
    # 向量 provider 由 EMBEDDING_MODE 决定(8.2 的接入点);接缝在这里,
    # 而不是把某个模型编进流水线
    provider = resolve_embedding_provider()
    vectors = encode_texts(provider, [row['text'] for row in rows])
    result = cluster_embeddings(vectors, 'hdbscan', {'min_cluster_size': 2, 'min_samples': 1})
    drafts: list[TopicDraft] = []
    namer = make_namer(sources, spent_today=spent_today(repository, run.get('project_id')))
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
        evidence_for_naming = [{'evidence_id': row['feedback_id'], 'text': row['text']}
                               for row in representative_rows]
        candidate = namer.name_topic(evidence_for_naming)
        # getattr 而不是直接取属性:命名器没有自报用量时,record_model_call 会记一条
        # UNKNOWN——10.5 要求 UNKNOWN 调用也有记录,而不是缺一条。硬取属性则会让
        # 一个不符合契约的命名器把整条流水线炸掉。
        record_model_call(repository, run.get('project_id'), run.get('id'),
                          getattr(namer, 'last_call', None))
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


def spent_today(repository, project_id: str) -> float:
    """本项目今天的模型花费;预算按「调用前预留」判断(10.5)。

    没有可靠价格配置时一律返回 0——那时付费模式本来就是禁用的(见 BudgetGuard),
    这里返回 0 只是让上游的算术成立,不会让任何调用发生。
    """
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date().isoformat()
    total = 0.0
    for call in repository.list_model_calls(project_id):
        if not str(call.get('created_at') or '').startswith(today):
            continue
        cost = call.get('cost_actual')
        if cost is None:
            cost = call.get('cost_estimated')
        if cost is not None:
            total += float(cost)
    return total


def record_model_call(repository, project_id: str, run_id: str | None,
                      usage: CallUsage | None) -> None:
    """记一次命名调用的模型账(5.2 model_calls / 10.5 预算与可观测性)。

    这个表此前不存在、`model_calls` 全仓库零引用,于是「每日预算」「调用前预留、
    收到 usage 后结算」「没有可靠价格配置时禁用付费模式」全都没有落脚点。

    **费用留 NULL 不填 0**:0 会让「免费」和「不知道多少钱」看起来一样,而预算判断
    依赖这个区别(10.5:没有可靠价格配置时禁用付费模式,而不是默认为免费)。
    tokens 同理——mock 与规则降级不产生用量,填 0 会伪装成「调用过一次且没花钱」。
    """
    import hashlib
    from uuid import uuid4
    usage = usage or CallUsage(provider='unknown', state='UNKNOWN')
    repository.save_model_call(project_id, {
        # 只记请求指纹,不记完整请求(5.2:不记录完整敏感请求)
        'id': f'mc_{uuid4().hex[:10]}', 'run_id': run_id, 'purpose': 'naming',
        'request_hash': hashlib.sha256(
            f'{run_id}|{usage.provider}|{usage.state}'.encode('utf-8')).hexdigest(),
        'provider': usage.provider,
        'model': usage.model,
        # 失败也记:只统计成功调用会让预算低估超时与结构失败重试掉的开销(10.5)
        'state': usage.state,
        'tokens_in': usage.tokens_in, 'tokens_out': usage.tokens_out,
        'cost_estimated': usage.cost_estimated, 'cost_actual': usage.cost_actual,
        'provider_request_id': usage.provider_request_id, 'response_file_id': None,
    })


def record_stage(repository, project_id: str, run_id: str, stage: str, *, state: str = 'DONE',
                 started_at=None, output_hash: str | None = None) -> None:
    """记一条阶段行(5.2 analysis_stages)。

    此前「跑到哪一步」只体现为 run 上的一个 stage 字符串:重试了几次、那一步的产物
    哈希是什么,都无从追溯——而 6.2 的恢复策略要靠这两样判断某一步是否成功过。
    """
    from datetime import datetime, timezone
    repository.save_stages(project_id, run_id, [{
        'stage': stage, 'state': state,
        'started_at': started_at,
        'finished_at': datetime.now(timezone.utc),
        'output_hash': output_hash,
    }])


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
    import time
    from datetime import datetime, timezone

    from .risk_service import persist_findings

    project_id = run.get('project_id')

    def _stage(name, started):
        record_stage(repository, project_id, analysis_id, name,
                     started_at=datetime.fromtimestamp(started, tz=timezone.utc))

    started = time.monotonic()
    rows, sources, total = _flatten_rows(run, repository)
    _stage('govern', started)

    started = time.monotonic()
    persist_segments(repository, project_id, rows)
    _stage('segment', started)

    # 8.2 要求模型 revision 可追溯:冻结进阶段的 config_hash,而不是只活在日志里。
    # 换模型不重跑的话不会有人发现,而聚类结果会变——所以它必须落到数据上。
    embedding_revision = resolve_embedding_provider().revision

    started = time.monotonic()
    drafts = build_topics_from_run(run, repository)
    record_stage(repository, project_id, analysis_id, 'embed',
                 started_at=datetime.fromtimestamp(started, tz=timezone.utc),
                 output_hash=embedding_revision)
    _stage('cluster', started)

    unassigned = total - sum(len(d.evidence) for d in drafts)
    started = time.monotonic()
    snapshot = publish_revision(store, analysis_id, drafts, sources, unassigned, repository)
    _stage('publish', started)

    # 扫描独立于聚类(计划 8.1:1 条严重投诉即使不成簇也要进复核队列),
    # 产物直接落 risk_findings 实体——复核队列就是这张表,不再有第二份副本。
    started = time.monotonic()
    findings = scan_run_risks(run, repository)
    persist_findings(repository, project_id, analysis_id, findings)
    _stage('scan', started)
    return snapshot
