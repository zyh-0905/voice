"""W13 主题人工校正与不可变版本。

操作锁定 run 当前 revision(expected_revision 不符 → 409,并发校正只有一个成功);
每次校正产生 revision+1 的**新版本行**,不覆写旧行(工程计划 5.2:`(topic_id, version)`
唯一、不可原地更新);新版本摘要未重新验证前标为待确认(summary_revalidated=False),
不能原样保留不适用的断言。

本模块是**纯函数**:吃一份已加载的快照,吐一份新快照。快照现在是从实体表现算的
读模型(见 app.revisions),历史不再靠 `revision_history` 那份 JSON 副本保存——
旧版本留在 topic_versions 里,由 analysis_revisions 的 manifest 指回具体的版本行。
"""
from __future__ import annotations

from typing import Mapping


class CorrectionConflict(ValueError):
    """expected_revision 与当前 revision 不一致。"""


class TopicNotFound(ValueError):
    """校正目标不存在于当前 revision。"""


def _require_reason(reason: str) -> None:
    if not reason or not str(reason).strip():
        raise ValueError('reason is required')


def _find_topic(topics: list[dict], topic_id: str) -> dict:
    for topic in topics:
        if topic['topic_id'] == topic_id:
            return topic
    raise TopicNotFound(f'topic not found: {topic_id}')


def apply_correction(
    snapshot: Mapping,
    operation: str,
    expected_revision: int,
    params: dict,
    reason: str,
    sources: Mapping[str, str] | None = None,
) -> tuple[dict, list[str]]:
    """返回 (new_snapshot, affected_topic_ids)。

    `snapshot` 由调用方用 `revisions.load_revision_snapshot` 加载,本函数不碰仓储:
    读模型与校正逻辑分开,校正才可能在不连数据库的情况下被测试。
    """
    _require_reason(reason)
    snapshot = dict(snapshot or {})
    current_revision = int(snapshot.get('revision') or 0)
    if int(expected_revision) != current_revision:
        raise CorrectionConflict(f'expected revision {expected_revision}, current {current_revision}')

    topics = [dict(t) for t in snapshot.get('topics') or []]
    evidence_by_topic = {key: [dict(e) for e in value] for key, value in (snapshot.get('evidence_by_topic') or {}).items()}
    unassigned = int(snapshot.get('unassigned_count') or 0)
    affected: list[str] = []

    if operation == 'RENAME':
        name = str(params.get('name') or '').strip()
        if not name:
            raise ValueError('name is required for RENAME')
        topic = _find_topic(topics, str(params['topic_id']))
        topic['name'] = name
        topic['summary_revalidated'] = False
        affected = [topic['topic_id']]
    elif operation == 'MERGE':
        source_ids = list(params.get('source_topic_ids') or [])
        if len(set(source_ids)) < 2:
            raise ValueError('MERGE requires at least two distinct source_topic_ids')
        merged = []
        for source_id in source_ids:
            if not any(t['topic_id'] == source_id for t in topics):
                raise ValueError(f'source_topic_ids not in current revision: {source_id}')
            merged.append(_find_topic(topics, source_id))
        name = str(params.get('name') or '').strip() or '/'.join(t['name'] for t in merged)
        merged_evidence: list[dict] = []
        seen: set[str] = set()
        for topic in merged:
            for item in evidence_by_topic.get(topic['topic_id'], []):
                if item['feedback_id'] in seen:
                    continue  # MERGE 对反馈集合去重
                seen.add(item['feedback_id'])
                merged_evidence.append(item)
        new_id = f"topic-merged-{current_revision + 1}-{len(topics) + 1}"
        topics = [t for t in topics if t['topic_id'] not in set(source_ids)]
        for source_id in source_ids:
            evidence_by_topic.pop(source_id, None)
        topics.append({'topic_id': new_id, 'name': name, 'summary': '', 'severity': merged[0]['severity'],
                       'feedback_count': len(merged_evidence), 'summary_revalidated': False,
                       # 合并主题的来源随第一来源走:内容 provenance 不因操作改变,
                       # 操作本身记录在 topic_corrections
                       'origin': merged[0].get('origin'), 'needs_review': merged[0].get('needs_review', True)})
        evidence_by_topic[new_id] = merged_evidence
        affected = list(source_ids) + [new_id]
    elif operation == 'SPLIT':
        feedback_ids = list(params.get('feedback_ids') or [])
        new_name = str(params.get('name') or '').strip()
        if not feedback_ids:
            raise ValueError('feedback_ids are required for SPLIT')
        if not new_name:
            raise ValueError('name is required for SPLIT')
        source = _find_topic(topics, str(params['topic_id']))
        all_evidence = evidence_by_topic.get(source['topic_id'], [])
        wanted = set(feedback_ids)
        moved = [e for e in all_evidence if e['feedback_id'] in wanted]
        if not moved:
            raise ValueError('feedback_ids not found in source topic')
        # 被拆分反馈未被分配的部分保留在原 topic
        kept = [e for e in all_evidence if e['feedback_id'] not in wanted]
        evidence_by_topic[source['topic_id']] = kept
        source['feedback_count'] = len(kept)
        new_id = f"topic-split-{current_revision + 1}-{len(topics) + 1}"
        topics.append({'topic_id': new_id, 'name': new_name, 'summary': '', 'severity': source['severity'],
                       'feedback_count': len(moved), 'summary_revalidated': False,
                       # 拆出来的部分与源主题同源;源主题本体保留原 origin/needs_review(dict 复制)
                       'origin': source.get('origin'), 'needs_review': source.get('needs_review', True)})
        evidence_by_topic[new_id] = moved
        affected = [source['topic_id'], new_id]
    elif operation == 'CREATE':
        feedback_ids = list(params.get('feedback_ids') or [])
        name = str(params.get('name') or '').strip()
        if not feedback_ids:
            raise ValueError('feedback_ids are required for CREATE')
        if not name:
            raise ValueError('name is required for CREATE')
        sources = sources or {}
        assigned = {item['feedback_id'] for evidence in evidence_by_topic.values() for item in evidence}
        rows: list[dict] = []
        for feedback_id in feedback_ids:
            if feedback_id not in sources:
                raise ValueError(f'foreign feedback_id: {feedback_id}')
            if feedback_id in assigned:
                raise ValueError(f'feedback already assigned: {feedback_id}')
            text = sources[feedback_id]
            rows.append({'feedback_id': feedback_id, 'source_row': 0,
                         'quote': text[:min(24, len(text))], 'quote_start': 0, 'quote_end': min(24, len(text))})
        new_id = f"topic-created-{current_revision + 1}-{len(topics) + 1}"
        topics.append({'topic_id': new_id, 'name': name, 'summary': '', 'severity': 'medium',
                       'feedback_count': len(rows), 'summary_revalidated': False,
                       # 人工从待归类反馈建题:来源是人,不是模型也不是规则降级
                       'origin': 'human', 'needs_review': False})
        evidence_by_topic[new_id] = rows
        unassigned = max(0, unassigned - len(feedback_ids))
        affected = [new_id]
    else:
        raise ValueError(f'unsupported operation: {operation}')

    new_snapshot = {
        **snapshot,
        'revision': current_revision + 1,
        'topics': topics,
        'evidence_by_topic': evidence_by_topic,
        'unassigned_count': unassigned,
    }
    # 不返回 revision_history:旧版本现在留在 topic_versions 里,
    # 由 analysis_revisions 的 manifest 指回具体版本行,不再复制 JSON 副本
    return new_snapshot, affected
