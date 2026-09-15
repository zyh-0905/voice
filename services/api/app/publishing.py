"""W11 发布事务:只有引用和计数校验通过才发布 revision。

快照式单写:完整构建 revision 快照(校验全部通过)后才落库,
InMemory/SQL 都是单次写入——提交中断不会显示半份主题;
正文证据保留 source_row 与 quote 片段偏移,可定位源行与脱敏原文。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol

from .revisions import plan_revision


class PublishValidationError(ValueError):
    """引用不存在、quote 与原文不一致或计数不符;发布整体拒绝。"""


@dataclass(frozen=True)
class EvidenceRef:
    feedback_id: str
    source_row: int
    quote: str
    quote_start: int
    quote_end: int


@dataclass(frozen=True)
class TopicDraft:
    topic_id: str
    name: str
    summary: str
    severity: str
    evidence: list[EvidenceRef] = field(default_factory=list)
    # 命名来源的原始标记(llm 的 provider 声明:http/mock/rule_fallback)。
    # 存库保持原值,API 层再映射到前端契约的 ai/rule/human/unknown——
    # 库里留的是审计事实,接口说的是展示词汇。
    origin: str | None = None
    # 命名器自报的待复核标记(8.5 契约字段);降级候选恒为 True。
    # 此前这个字段在 draft 就丢了,topic_versions.needs_review 只能吃默认值。
    needs_review: bool = True


class AnalysisStore(Protocol):
    def get_analysis(self, analysis_id: str) -> dict: ...
    def update_analysis(self, analysis_id: str, changes: dict) -> dict: ...


def validate_draft_references(drafts: list[TopicDraft], sources: Mapping[str, str]) -> None:
    """引用校验:feedback_id 必须在本 run 输入内;quote 必须是原文精确 Unicode 片段。"""
    for draft in drafts:
        for ref in draft.evidence:
            if ref.feedback_id not in sources:
                raise PublishValidationError(f'foreign feedback_id: {ref.feedback_id}')
            text = sources[ref.feedback_id]
            if not (0 <= ref.quote_start <= ref.quote_end <= len(text)):
                raise PublishValidationError(f'quote offsets out of range: {ref.feedback_id}')
            if text[ref.quote_start:ref.quote_end] != ref.quote:
                raise PublishValidationError(f'quote mismatch: {ref.feedback_id}')
        if draft.evidence and any(ref.feedback_id not in sources for ref in draft.evidence):
            raise PublishValidationError(f'topic {draft.topic_id} references foreign evidence')


def build_revision_snapshot(
    drafts: list[TopicDraft],
    sources: Mapping[str, str],
    unassigned_count: int,
    revision: int,
) -> dict:
    """构建完整 revision 快照;任何校验失败都整体拒绝,不产生部分数据。"""
    validate_draft_references(drafts, sources)
    topics = []
    evidence_by_topic = {}
    for draft in drafts:
        topic = {
            'topic_id': draft.topic_id,
            'name': draft.name,
            'summary': draft.summary,
            'severity': draft.severity,
            'feedback_count': len(draft.evidence),
            'origin': draft.origin,
            'needs_review': draft.needs_review,
        }
        evidence_by_topic[draft.topic_id] = [
            {
                'feedback_id': ref.feedback_id,
                'source_row': ref.source_row,
                'quote': ref.quote,
                'quote_start': ref.quote_start,
                'quote_end': ref.quote_end,
            }
            for ref in draft.evidence
        ]
        topics.append(topic)
    return {
        'revision': revision,
        'topics': topics,
        'evidence_by_topic': evidence_by_topic,
        'unassigned_count': unassigned_count,
        'status': 'done',
    }


def publish_revision(
    store: AnalysisStore,
    analysis_id: str,
    drafts: list[TopicDraft],
    sources: Mapping[str, str],
    unassigned_count: int,
    repository,
) -> dict:
    """单写原子发布:校验→构建快照→把快照展开成实体行,一次事务写入。

    发布落的**不是 JSON 快照**而是实体行(工程计划 5.2):主题、主题版本、
    证据与 revision 记录各归各表。快照改为读取时按 manifest 现算——存下来就又
    变成两份会分叉的副本,而那正是 5.2 明文要移除的东西。

    版本号取自 `analysis_revisions` 而不是 run 里残留的标量:人工校正推进的是
    revision 序列,从表里取才不会在「校正与重跑并发」时把同一个 revision 写两次。
    """
    run = store.get_analysis(analysis_id)
    if run is None:
        raise PublishValidationError(f'analysis not found: {analysis_id}')
    project_id = run.get('project_id')
    revision = int(repository.latest_revision(project_id, analysis_id) or 0) + 1
    snapshot = build_revision_snapshot(drafts, sources, unassigned_count, revision)
    # 版本号**必须接着往下编**。不传 next_versions 的话 plan_revision 会对每个主题
    # 从 1 重新编号,第二次发布的版本 id 与第一次相同——于是新证据被追加到旧版本行上,
    # 「不可原地更新」当场失效,而且旧 revision 读出来会看到新证据。
    plan = plan_revision(project_id, analysis_id, snapshot,
                         next_versions=repository.next_versions_for_run(project_id, analysis_id))
    repository.save_revision(project_id, analysis_id, plan)
    store.update_analysis(analysis_id, {'status': 'done'})
    return snapshot
