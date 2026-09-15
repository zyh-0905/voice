"""工程计划 5.2:分析修订、主题版本与证据的实体化与读模型。

**快照不再是存下来的 JSON,而是从实体表现算的读模型。**

此前一次发布把整份快照(主题列表 + 每个主题的全部证据)写进
`analysis_runs.result`,人工校正再把旧快照整份复制进 `revision_history`。那份副本
与「当前」副本可以分叉,而且没有任何东西会发现——计划对这种做法有明文禁止
(「不要为了减少表数把整个项目装进一个不可查询的 JSON 字段」)。

现在:

- 发布与校正**写实体表**(topics / topic_versions / topic_evidence / analysis_revisions);
- 读取走 `load_revision_snapshot`,按 manifest 记录的**具体 version id** 取那一版的
  主题与证据。因此旧 revision 永远可读,且不会因为后来改了同名主题而被动改写;
- `plan_revision` 是发布路径与迁移回填**共用**的展开函数——各写一份的话,
  存量行与新行的 topic_version 编号口径会分叉,而「旧版本可复现」正建立在编号上。

`analysis_runs.result` 里剩的是 run 级标量(status 等),不再承载主题与证据。
"""
from __future__ import annotations

from typing import Mapping, Sequence

# 空串表示「关联到反馈级」而非分块级,见 models.TopicEvidence 的说明
FEEDBACK_LEVEL_SEGMENT = ''


def plan_revision(
    project_id: str,
    run_id: str,
    snapshot: Mapping,
    *,
    next_versions: Mapping[str, int] | None = None,
    reason: str | None = None,
    actor: str | None = None,
) -> dict:
    """把一个 revision 快照展开成待落库的行。

    `next_versions` 按**业务 topic_id** 给出下一个可用版本号(默认都从 1 开始)——
    本函数只在单个 run 内工作,topic_id 在该范围内稳定,不存在跨 run 的歧义。
    返回的四组行由调用方在同一事务里写入。
    """
    revision = int(snapshot.get('revision') or 0)
    versions = dict(next_versions or {})
    manifest: dict[str, str] = {}
    topic_rows: list[dict] = []
    version_rows: list[dict] = []
    evidence_rows: list[dict] = []

    for topic in snapshot.get('topics') or []:
        topic_id = str(topic['topic_id'])
        version = int(versions.get(topic_id, 1))
        versions[topic_id] = version + 1
        # **行 id 必须带 run_id**。`topic_id` 只在一次分析内稳定(5.2),而每个 run 都
        # 会把簇命名为 `topic-1`、`topic-2`……:不带 run_id 的话,同一项目的第二个 run
        # 会与第一个 run 撞主键——它的版本行会被静默跳过,表现为「这个 run 的主题
        # 是空的」,而没有任何东西报错。demo 库上两个 run 正是这样互相覆盖的。
        topic_row_id = f'tp_{run_id}_{topic_id}'
        version_id = f'tv_{run_id}_{topic_id}_{version}'
        manifest[topic_id] = version_id

        topic_rows.append({'project_id': project_id, 'run_id': run_id,
                           'id': topic_row_id, 'topic_id': topic_id,
                           'current_version_id': version_id, 'state': 'ACTIVE'})
        version_rows.append({
            'id': version_id, 'project_id': project_id, 'run_id': run_id,
            'topic_id': topic_id, 'topic_row_id': topic_row_id,
            'version': version, 'revision': revision,
            'name': str(topic.get('name') or ''), 'summary': str(topic.get('summary') or ''),
            'severity': str(topic.get('severity') or 'medium'),
            'department': topic.get('department'),
            'claims_json': list(topic.get('claims') or []),
            'suggested_action': topic.get('suggested_action'),
            'needs_review': bool(topic.get('needs_review', True)),
            # 校正过的版本标 false:摘要未重新验证,不能原样保留不适用的断言
            'summary_revalidated': bool(topic.get('summary_revalidated', True)),
            'limitations_json': list(topic.get('limitations') or []),
            'origin': topic.get('origin'),
        })
        for index, item in enumerate((snapshot.get('evidence_by_topic') or {}).get(topic_id) or []):
            evidence_rows.append({
                'id': f'te_{version_id}_{index}', 'project_id': project_id,
                'topic_version_id': version_id, 'feedback_id': str(item['feedback_id']),
                'segment_id': str(item.get('segment_id') or FEEDBACK_LEVEL_SEGMENT),
                'source_row': int(item.get('source_row') or 0),
                'quote': str(item.get('quote') or ''),
                'quote_start': int(item.get('quote_start') or 0),
                'quote_end': int(item.get('quote_end') or 0),
                'similarity': item.get('similarity'),
                'is_representative': bool(item.get('is_representative', False)),
            })

    revision_row = {
        'id': f'rev_{run_id}_{revision}', 'project_id': project_id, 'run_id': run_id,
        'revision': revision, 'topic_manifest_json': manifest,
        'unassigned_count': int(snapshot.get('unassigned_count') or 0),
        'reason': reason, 'actor_id': actor,
    }
    return {'revision': revision_row, 'topics': topic_rows,
            'versions': version_rows, 'evidence': evidence_rows}


def load_revision_snapshot(repository, run: Mapping, revision: int | None = None) -> dict | None:
    """按 manifest 重建某个 revision 的快照;没有该 revision 返回 None。

    返回形状与旧的 `analysis_runs.result` 相同,所以读取方只需换取数来源,
    不必各自改写解析逻辑——六处各改一次就多六次写错的机会。
    """
    project_id = run.get('project_id')
    run_id = run.get('id')
    if not project_id or not run_id:
        return None
    target = repository.latest_revision(project_id, run_id) if revision is None else int(revision)
    if not target:
        return None
    record = repository.get_analysis_revision(project_id, run_id, target)
    if record is None:
        return None

    manifest = record.get('topic_manifest_json') or {}
    topics: list[dict] = []
    evidence_by_topic: dict[str, list[dict]] = {}
    for topic_id, version_id in manifest.items():
        version = repository.get_topic_version(project_id, version_id)
        if version is None:
            # manifest 指向一个不存在的版本:宁可少一个主题,也不能编一个出来
            continue
        evidence = repository.list_topic_evidence(project_id, version_id)
        topics.append({
            'topic_id': topic_id,
            'name': version['name'],
            'summary': version['summary'],
            'severity': version['severity'],
            'feedback_count': len({item['feedback_id'] for item in evidence}),
            'summary_revalidated': version['summary_revalidated'],
            'version_id': version_id,
            'topic_version': version['version'],
            # AI 来源链的读侧:仓储的 _topic_version_dict 本来就带这两个字段,
            # 此前重建快照时被丢掉,校正路径也因此无法继承
            'origin': version.get('origin'),
            'needs_review': bool(version.get('needs_review', True)),
        })
        evidence_by_topic[topic_id] = [
            {'feedback_id': item['feedback_id'], 'source_row': item['source_row'],
             'quote': item['quote'], 'quote_start': item['quote_start'],
             'quote_end': item['quote_end'],
             # 读侧带出 segment_id:证据→分块→offset→脱敏正文的链路要能走通
             'segment_id': item.get('segment_id') or FEEDBACK_LEVEL_SEGMENT}
            for item in evidence
        ]
    return {
        'revision': target,
        'topics': topics,
        'evidence_by_topic': evidence_by_topic,
        'unassigned_count': record.get('unassigned_count') or 0,
        'status': 'done',
    }


def topic_version_ids(repository, project_id: str, version_ids: Sequence[str]) -> dict[str, dict]:
    """按 id 批量取主题版本,供复盘等按 topic_version_ids 工作的调用方使用。"""
    found: dict[str, dict] = {}
    for version_id in version_ids:
        version = repository.get_topic_version(project_id, version_id)
        if version is not None:
            found[version_id] = version
    return found
