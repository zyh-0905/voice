"""W11 主题领域查询:UI 以 run+revision 查询;证据只返回本 run 输入内的记录。"""
from __future__ import annotations

from typing import Mapping


class RevisionNotFound(ValueError):
    pass


class TopicNotFound(ValueError):
    pass


def list_topics_from_run(snapshot: Mapping) -> list[dict]:
    """从 revision 读模型读取主题;无发布(无 revision)返回空列表。

    参数是 `revisions.load_revision_snapshot` 的产物,不是 run——快照现在是
    按 manifest 现算的,不再存在 run 的某个 JSON 字段里。
    """
    return list(snapshot.get('topics') or [])


def topic_evidence_from_run(snapshot: Mapping, topic_id: str, topic_version_id: int | None) -> list[dict]:
    """读取主题证据;topic_version_id 必须与已发布 revision 对应,外项目数据不在此集合。"""
    revision = snapshot.get('revision')
    if not revision:
        raise RevisionNotFound('run has no published revision')
    if topic_version_id is not None and int(topic_version_id) != int(revision):
        raise RevisionNotFound(f'revision mismatch: want {topic_version_id}, have {revision}')
    evidence_by_topic = snapshot.get('evidence_by_topic') or {}
    if topic_id not in evidence_by_topic:
        raise TopicNotFound(f'topic not found: {topic_id}')
    return list(evidence_by_topic[topic_id])
