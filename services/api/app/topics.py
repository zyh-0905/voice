"""W11 主题领域查询:UI 以 run+revision 查询;证据只返回本 run 输入内的记录。"""
from __future__ import annotations

from typing import Mapping


class RevisionNotFound(ValueError):
    pass


class TopicNotFound(ValueError):
    pass


def list_topics_from_run(run: Mapping) -> list[dict]:
    """从已发布 run 快照读取主题;无发布(无 result/revision)返回空列表。"""
    result = run.get('result') or {}
    return list(result.get('topics') or [])


def topic_evidence_from_run(run: Mapping, topic_id: str, topic_version_id: int | None) -> list[dict]:
    """读取主题证据;topic_version_id 必须与已发布 revision 对应,外项目数据不在此集合。"""
    result = run.get('result') or {}
    revision = result.get('revision')
    if not revision:
        raise RevisionNotFound('run has no published revision')
    if topic_version_id is not None and int(topic_version_id) != int(revision):
        raise RevisionNotFound(f'revision mismatch: want {topic_version_id}, have {revision}')
    evidence_by_topic = result.get('evidence_by_topic') or {}
    if topic_id not in evidence_by_topic:
        raise TopicNotFound(f'topic not found: {topic_id}')
    return list(evidence_by_topic[topic_id])
