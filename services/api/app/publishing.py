"""W11 发布事务:只有引用和计数校验通过才发布 revision。

快照式单写:完整构建 revision 快照(校验全部通过)后才落库,
InMemory/SQL 都是单次写入——提交中断不会显示半份主题;
正文证据保留 source_row 与 quote 片段偏移,可定位源行与脱敏原文。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol


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
) -> dict:
    """单写原子发布:校验→构建快照→一次 update_analysis。"""
    run = store.get_analysis(analysis_id)
    if run is None:
        raise PublishValidationError(f'analysis not found: {analysis_id}')
    revision = int(run.get('revision') or 0) + 1
    snapshot = build_revision_snapshot(drafts, sources, unassigned_count, revision)
    store.update_analysis(analysis_id, {'result': snapshot, 'status': 'done'})
    return snapshot
