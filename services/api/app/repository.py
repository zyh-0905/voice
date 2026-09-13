from collections.abc import MutableMapping
from copy import deepcopy
from typing import Protocol
import os

MAX_PUBLISH_ATTEMPTS = 3


def same_event(prior: dict, value: dict) -> bool:
    """工程计划 4.4:同 event_key 时比较标准化内容、时间与渠道。

    三者一致才算同一条事件(计入 duplicate);任一不同即 SOURCE_ID_CONFLICT,
    不能无提示覆盖历史证据。共享一份实现——内存与 SQL 仓储各写一遍的话,
    「同键异内容」在两个模式下会有两种判定,而差异只在真实部署里暴露。
    """
    return (prior.get('content_hash') == value.get('content_hash')
            and str(prior.get('occurred_at') or '') == str(value.get('occurred_at') or '')
            and str(prior.get('channel') or '') == str(value.get('channel') or ''))


class Repository(Protocol):
    def list_projects(self) -> list[dict]: ...
    def get_project(self, key: str) -> dict | None: ...
    def create_project(self, value: dict) -> dict: ...
    def list_members(self, project_id: str) -> list[dict]: ...
    def list_user_memberships(self, user_id: str) -> list[dict]: ...
    def get_membership(self, project_id: str, user_id: str) -> dict | None: ...
    def get_member_role(self, project_id: str, user_id: str) -> str | None: ...
    def create_membership(self, value: dict) -> dict: ...
    def set_member_role(self, project_id: str, user_id: str, role: str) -> dict: ...
    def delete_memberships(self, project_id: str) -> int: ...
    def get_project_settings(self, project_id: str) -> dict | None: ...
    def update_project_settings(self, project_id: str, changes: dict) -> dict: ...
    datasets: MutableMapping[str, dict]
    analyses: MutableMapping[str, dict]
    outbox: list[dict]

    def create_dataset(self, value: dict) -> dict: ...
    def update_dataset(self, key: str, changes: dict) -> dict: ...
    def delete_dataset(self, key: str) -> None: ...
    def get_analysis(self, key: str) -> dict | None: ...
    def create_analysis(self, value: dict) -> dict: ...
    def update_analysis(self, key: str, changes: dict) -> dict: ...
    def create_outbox_event(self, event: dict) -> dict: ...
    def list_pending_outbox(self, limit: int | None = None) -> list[dict]: ...
    def mark_published(self, event_key: str) -> None: ...
    def mark_publish_failed(self, event_key: str, error: str) -> None: ...
    def get_idempotency(self, key: str) -> dict | None: ...
    def delete_idempotency_for_project(self, project_id: str) -> int: ...
    def count_idempotency(self, project_id: str) -> int: ...
    def create_idempotency(self, key: str, value: dict) -> dict: ...
    # —— §5.2 反馈与分块实体:分析、看板、导出、证据源的共同取数源 ——
    def save_feedback_rows(self, project_id: str, dataset_id: str, rows: list[dict]) -> dict: ...
    def list_feedback(self, project_id: str, dataset_ids: list[str] | None = None,
                      feedback_ids: list[str] | None = None) -> list[dict]: ...
    def get_feedback(self, project_id: str, feedback_id: str) -> dict | None: ...
    def delete_feedback_for_dataset(self, project_id: str, dataset_id: str) -> int: ...
    def delete_feedback_for_project(self, project_id: str) -> int: ...
    def replace_segments(self, project_id: str, feedback_id: str, spans: list, redaction_version: str) -> int: ...
    def list_segments(self, project_id: str, feedback_id: str) -> list[dict]: ...
    def save_run_feedbacks(self, project_id: str, run_id: str, feedback_ids: list[str]) -> int: ...
    def list_run_feedback_ids(self, project_id: str, run_id: str) -> list[str]: ...
    def delete_run_feedbacks_for_run(self, project_id: str, run_id: str) -> int: ...
    def delete_run_feedbacks_for_project(self, project_id: str) -> int: ...
    def count_segments(self, project_id: str) -> int: ...
    def count_segments_for_feedback(self, project_id: str, feedback_ids: list[str]) -> int: ...
    def delete_segments_for_project(self, project_id: str) -> int: ...
    def delete_segments_for_dataset(self, project_id: str, dataset_id: str) -> int: ...
    # —— §5.2 分析修订与主题版本(快照改由实体表现算) ——
    def save_revision(self, project_id: str, run_id: str, plan: dict) -> dict: ...
    def latest_revision(self, project_id: str, run_id: str) -> int | None: ...
    def get_analysis_revision(self, project_id: str, run_id: str, revision: int) -> dict | None: ...
    def get_topic_version(self, project_id: str, version_id: str) -> dict | None: ...
    def list_topic_evidence(self, project_id: str, version_id: str) -> list[dict]: ...
    def save_topic_correction(self, project_id: str, record: dict) -> dict: ...
    def list_topic_corrections(self, project_id: str, run_id: str) -> list[dict]: ...
    def next_versions_for_run(self, project_id: str, run_id: str) -> dict[str, int]: ...
    def count_topics_for_run(self, project_id: str, run_id: str) -> int: ...
    def delete_topics_for_run(self, project_id: str, run_id: str) -> int: ...
    def delete_topics_for_project(self, project_id: str) -> int: ...
    # —— §5.2 分析阶段 / 风险候选 / 模型调用 ——
    def save_stages(self, project_id: str, run_id: str, stages: list[dict]) -> int: ...
    def list_stages(self, project_id: str, run_id: str) -> list[dict]: ...
    def save_risk_findings(self, project_id: str, run_id: str, findings: list[dict]) -> dict: ...
    def list_risk_findings(self, project_id: str) -> list[dict]: ...
    def get_risk_finding(self, project_id: str, finding_id: str) -> dict | None: ...
    def update_risk_finding(self, project_id: str, finding_id: str, changes: dict) -> dict: ...
    def delete_risk_findings_for_project(self, project_id: str) -> int: ...
    def delete_risk_findings_for_feedback(self, project_id: str, feedback_ids: list[str]) -> int: ...
    def save_model_call(self, project_id: str, record: dict) -> dict: ...
    def list_model_calls(self, project_id: str, run_id: str | None = None) -> list[dict]: ...
    # —— §5.2 任务事件与任务证据 ——
    def save_task_transition(self, project_id: str, task_id: str, changes: dict,
                             event: dict) -> dict: ...
    def list_task_events(self, project_id: str, task_id: str) -> list[dict]: ...
    def append_task_event(self, project_id: str, task_id: str, event: dict) -> dict: ...
    def save_task_evidence(self, project_id: str, task_id: str, rows: list[dict]) -> int: ...
    def list_task_evidence(self, project_id: str, task_id: str) -> list[dict]: ...
    def delete_task_evidence_for_feedback(self, project_id: str, feedback_ids: list[str]) -> int: ...
    def delete_task_data_for_project(self, project_id: str) -> int: ...
    def delete_run_data_for_project(self, project_id: str) -> int: ...
    def list_entities(self, kind: str, project_id: str) -> list[dict]: ...
    def create_entity(self, kind: str, value: dict) -> dict: ...
    def update_entity(self, kind: str, key: str, changes: dict) -> dict: ...
    def delete_entity(self, kind: str, key: str) -> None: ...
    def delete_analysis(self, key: str) -> None: ...
    def delete_project(self, key: str) -> None: ...


class InMemoryRepository:
    def __init__(self):
        self.projects = {}
        self.memberships = {}
        self.datasets = {}
        self.analyses = {}
        self.outbox = []
        self.idempotency = {}
        self.risks, self.tasks, self.reviews, self.audits, self.deletions, self.exports = {}, {}, {}, {}, {}, {}
        # §5.2:键均为 (project_id, id),越项目引用在内存侧也拿不到
        self.feedback = {}
        self.segments = {}
        self.run_feedbacks = {}
        # §5.2 主题与修订:键均带 project_id,越项目引用在内存侧也拿不到
        self.topics = {}
        self.topic_versions = {}
        self.topic_evidence = {}
        self.analysis_revisions = {}
        self.topic_corrections = []
        self.analysis_stages = {}
        self.risk_findings = {}
        self.model_calls = []
        self.task_events = []
        self.task_evidence = {}

    def _create(self, collection, value):
        key = value['id']
        if key in collection:
            raise ValueError(f'Entity already exists: {key}')
        collection[key] = deepcopy(value)
        return deepcopy(collection[key])

    def list_projects(self): return [deepcopy(v) for v in self.projects.values()]
    def get_project(self, key): return deepcopy(self.projects.get(key))
    def create_project(self, value): return self._create(self.projects, value)

    # —— W03 成员关系:以 (project_id, user_id) 为键,读取一律 deepcopy ——
    def list_members(self, project_id):
        items = [deepcopy(v) for v in self.memberships.values() if v['project_id'] == project_id]
        items.sort(key=lambda item: item['user_id'])
        return items

    def list_user_memberships(self, user_id):
        items = [deepcopy(v) for v in self.memberships.values() if v['user_id'] == user_id]
        items.sort(key=lambda item: item['project_id'])
        return items

    def get_membership(self, project_id, user_id):
        return deepcopy(self.memberships.get((project_id, user_id)))

    def get_member_role(self, project_id, user_id):
        membership = self.get_membership(project_id, user_id)
        return membership['role'] if membership else None

    def create_membership(self, value):
        key = (value['project_id'], value['user_id'])
        if key in self.memberships:
            raise ValueError(f'Membership already exists: {value["project_id"]}/{value["user_id"]}')
        self.memberships[key] = deepcopy(value)
        return deepcopy(self.memberships[key])

    def set_member_role(self, project_id, user_id, role):
        membership = self.memberships.get((project_id, user_id))
        if membership is None:
            raise KeyError(f'{project_id}/{user_id}')
        membership['role'] = role
        return deepcopy(membership)

    def delete_memberships(self, project_id):
        """项目删除时连同成员关系一起清理(10.4 级联):留下孤儿行等于留了访问权。"""
        keys = [key for key, value in self.memberships.items() if value['project_id'] == project_id]
        for key in keys:
            del self.memberships[key]
        return len(keys)

    # —— W03 项目设置:timezone 与 settings_json 合并为一份存储值 ——
    def get_project_settings(self, project_id):
        project = self.projects.get(project_id)
        if project is None:
            return None
        stored = dict(project.get('settings_json') or {})
        if project.get('timezone') is not None:
            stored['timezone'] = project['timezone']
        return deepcopy(stored)

    def update_project_settings(self, project_id, changes):
        project = self.projects.get(project_id)
        if project is None:
            raise KeyError(project_id)
        if changes.get('timezone') is not None:
            project['timezone'] = changes['timezone']
        stored = dict(project.get('settings_json') or {})
        stored.update({key: deepcopy(value) for key, value in changes.items() if key != 'timezone'})
        project['settings_json'] = stored
        return self.get_project_settings(project_id)

    def _update(self, collection, key, changes):
        collection[key].update(deepcopy(changes))
        return deepcopy(collection[key])

    def create_dataset(self, value): return self._create(self.datasets, value)
    def update_dataset(self, key, changes): return self._update(self.datasets, key, changes)
    def delete_dataset(self, key):
        if key not in self.datasets: raise KeyError(key)
        del self.datasets[key]
    def get_analysis(self, key): return deepcopy(self.analyses.get(key))
    def create_analysis(self, value): return self._create(self.analyses, value)
    def update_analysis(self, key, changes): return self._update(self.analyses, key, changes)
    def list_entities(self, kind, project_id): return [deepcopy(v) for v in getattr(self, kind).values() if v.get('project_id') == project_id]
    def create_entity(self, kind, value): return self._create(getattr(self, kind), value)
    def update_entity(self, kind, key, changes): return self._update(getattr(self, kind), key, changes)
    def delete_entity(self, kind, key):
        collection = getattr(self, kind)
        if key not in collection: raise KeyError(key)
        del collection[key]
    def delete_analysis(self, key):
        if key not in self.analyses: raise KeyError(key)
        del self.analyses[key]
    def delete_project(self, key):
        self.projects.pop(key, None)
    def create_outbox_event(self, event):
        if any(e['event_key'] == event['event_key'] for e in self.outbox): return next(e for e in self.outbox if e['event_key'] == event['event_key'])
        value = deepcopy({**event, 'status': event.get('status', 'pending')}); self.outbox.append(value); return deepcopy(value)
    def list_pending_outbox(self, limit=None):
        events = [e for e in self.outbox if e.get('status') == 'pending']
        return deepcopy(events[:limit] if limit is not None else events)
    def mark_published(self, event_key):
        for e in self.outbox:
            if e['event_key'] == event_key: e['status'] = 'published'; return
    def mark_publish_failed(self, event_key, error):
        # 重投安全:attempts 达上限才转 failed 死信,期间保持 pending 供下轮重试
        for e in self.outbox:
            if e['event_key'] == event_key:
                e['last_error'] = str(error)
                attempts = int(e.get('attempts', 0)) + 1
                e['attempts'] = attempts
                if attempts >= MAX_PUBLISH_ATTEMPTS:
                    e['status'] = 'failed'
                return

    def get_idempotency(self, key):
        return deepcopy(self.idempotency.get(key))

    def create_idempotency(self, key, value):
        if key in self.idempotency:
            raise ValueError(f'Idempotency key already exists: {key}')
        self.idempotency[key] = deepcopy(value)
        return deepcopy(value)

    # —— §5.2 分析修订与主题版本 ——
    # 四张表一次事务写入:半份修订会同时破坏「(run_id, revision) 唯一」和
    # 「旧 revision 永远可读」——会出现一个 manifest 指向不存在版本的空壳 revision。
    def save_revision(self, project_id, run_id, plan):
        for topic in plan['topics']:
            self.topics[(project_id, run_id, topic['id'])] = deepcopy(topic)
        for version in plan['versions']:
            self.topic_versions[(project_id, version['id'])] = deepcopy(version)
        for evidence in plan['evidence']:
            self.topic_evidence.setdefault((project_id, evidence['topic_version_id']), []).append(deepcopy(evidence))
        record = deepcopy(plan['revision'])
        self.analysis_revisions[(project_id, run_id, record['revision'])] = record
        return record

    def latest_revision(self, project_id, run_id):
        revisions = [rev for (pid, rid, rev) in self.analysis_revisions
                     if pid == project_id and rid == run_id]
        return max(revisions) if revisions else None

    def get_analysis_revision(self, project_id, run_id, revision):
        return deepcopy(self.analysis_revisions.get((project_id, run_id, revision)))

    def get_topic_version(self, project_id, version_id):
        return deepcopy(self.topic_versions.get((project_id, version_id)))

    def list_topic_evidence(self, project_id, version_id):
        return deepcopy(self.topic_evidence.get((project_id, version_id), []))

    def save_topic_correction(self, project_id, record):
        value = deepcopy(record)
        self.topic_corrections.append(value)
        return value

    def next_versions_for_run(self, project_id, run_id):
        """每个主题的下一个可用版本号。

        校正要接着往下编号,不能从 1 重来——重来会撞 `(topic_id, version)` 唯一,
        而那个约束正是「不可原地更新」的保证。
        """
        highest: dict[str, int] = {}
        topic_ids = {topic['topic_id'] for (pid, rid, _row) , topic in
                     ((key, value) for key, value in self.topics.items())
                     if pid == project_id and rid == run_id}
        for (pid, _vid), version in self.topic_versions.items():
            if pid != project_id or version['run_id'] != run_id:
                continue
            if version['topic_id'] not in topic_ids:
                continue
            highest[version['topic_id']] = max(highest.get(version['topic_id'], 0), version['version'])
        return {topic_id: highest.get(topic_id, 0) + 1 for topic_id in topic_ids}

    def list_topic_corrections(self, project_id, run_id):
        return [deepcopy(item) for item in self.topic_corrections
                if item['project_id'] == project_id and item['run_id'] == run_id]

    def count_topics_for_run(self, project_id, run_id):
        """删除与隔离核验用:某个 run 自己有多少个主题行。"""
        return sum(1 for (pid, rid, _row) in self.topics if pid == project_id and rid == run_id)

    # —— §5.2 分析阶段:键 (project_id, run_id, stage, config_hash),重试只推进 attempt ——
    def save_stages(self, project_id, run_id, stages):
        for stage in stages:
            key = (project_id, run_id, stage['stage'], stage.get('config_hash') or '')
            current = self.analysis_stages.get(key)
            row = {**(current or {}), **deepcopy(stage), 'project_id': project_id, 'run_id': run_id}
            row.setdefault('attempt', 1)
            row.setdefault('state', 'PENDING')
            self.analysis_stages[key] = row
        return len(stages)

    def list_stages(self, project_id, run_id):
        return [deepcopy(row) for key, row in sorted(self.analysis_stages.items())
                if key[0] == project_id and key[1] == run_id]

    # —— §5.2 风险候选 ——
    def save_risk_findings(self, project_id, run_id, findings):
        """按 `(feedback_id, rule_id, policy_version)` 写入或刷新候选。

        **人工裁决优先**:已确认/已排除的候选只保留,不把 review_state 退回 pending。
        否则每跑一次分析就会把人的判断冲掉(6.4 要求重新审查留下新增复核事件)。
        """
        created = refreshed = human_decided = 0
        for finding in findings:
            value = deepcopy(finding)
            value['project_id'] = project_id
            value['run_id'] = run_id
            key = (project_id, value['id'])
            prior = self.risk_findings.get(key)
            if prior is None:
                value.setdefault('review_state', 'pending')
                value.setdefault('status', 'OPEN')
                value.setdefault('version', 1)
                self.risk_findings[key] = value
                created += 1
                continue
            if str(prior.get('review_state', 'pending')).lower() != 'pending':
                human_decided += 1
                continue
            # 仍待复核:刷新策略可能已变的字段,人的判断字段一律不动
            self.risk_findings[key] = {**prior, **{name: value[name] for name in
                                                   ('severity', 'reason', 'evidence_offsets',
                                                    'source_row', 'run_id') if name in value}}
            refreshed += 1
        return {'created': created, 'refreshed': refreshed, 'human_decided': human_decided}

    def list_risk_findings(self, project_id):
        rows = [deepcopy(row) for (pid, _rid), row in self.risk_findings.items() if pid == project_id]
        rows.sort(key=lambda row: (str(row.get('severity', '')), str(row.get('id', ''))))
        return rows

    def get_risk_finding(self, project_id, finding_id):
        row = self.risk_findings.get((project_id, finding_id))
        return None if row is None else deepcopy(row)

    def update_risk_finding(self, project_id, finding_id, changes):
        row = self.risk_findings.get((project_id, finding_id))
        if row is None:
            raise KeyError(finding_id)
        row.update(deepcopy(changes))
        return deepcopy(row)

    def delete_risk_findings_for_project(self, project_id):
        keys = [key for key in self.risk_findings if key[0] == project_id]
        for key in keys:
            del self.risk_findings[key]
        return len(keys)

    def delete_risk_findings_for_feedback(self, project_id, feedback_ids):
        """候选挂在 feedback 上(复合外键),删反馈前必须先删它们。"""
        wanted = {str(item) for item in feedback_ids}
        keys = [key for key, row in self.risk_findings.items()
                if key[0] == project_id and str(row.get('feedback_id') or '') in wanted]
        for key in keys:
            del self.risk_findings[key]
        return len(keys)

    # —— §5.2 模型调用:预算与成本的凭据(10.5) ——
    def save_model_call(self, project_id, record):
        from datetime import datetime, timezone
        value = deepcopy(record)
        value['project_id'] = project_id
        # 预算按「今日」统计,所以两个仓储都要给出这个字段,否则过滤条件在两个
        # 模式下含义不同——SQL 有、内存没有时,内存模式会把历史调用也算进今天。
        value.setdefault('created_at', datetime.now(timezone.utc).isoformat())
        self.model_calls.append(value)
        return value

    def list_model_calls(self, project_id, run_id=None):
        return [deepcopy(item) for item in self.model_calls
                if item['project_id'] == project_id
                and (run_id is None or item.get('run_id') == run_id)]

    # —— §5.2 任务事件:与任务状态更新同一事务 ——
    def save_task_transition(self, project_id, task_id, changes, event):
        """更新任务并追加事件。

        两个仓储都把它做成**一次调用**:分成「改任务」和「记事件」两步的话,中间
        失败会留下一个状态变了但没有对应事件的任务,而时间线正好是用来回答
        「这个状态是谁改的」的。
        """
        task = self.tasks.get(task_id)
        if task is None or task.get('project_id') != project_id:
            raise KeyError(task_id)
        task.update(deepcopy(changes))
        self.append_task_event(project_id, task_id, event)
        return deepcopy(task)

    def append_task_event(self, project_id, task_id, event):
        value = {**deepcopy(event), 'project_id': project_id, 'task_id': task_id}
        value.setdefault('material_refs_json', [])
        self.task_events.append(value)
        return deepcopy(value)

    def list_task_events(self, project_id, task_id):
        """按写入顺序返回:时间线的顺序就是它被记录的顺序。"""
        return [deepcopy(item) for item in self.task_events
                if item['project_id'] == project_id and item['task_id'] == task_id]

    def save_task_evidence(self, project_id, task_id, rows):
        """整批替换该任务的来源快照;已存在的 (task, feedback, version) 不重复写。"""
        existing = self.task_evidence.setdefault((project_id, task_id), [])
        seen = {(item['feedback_id'], item.get('topic_version_id')) for item in existing}
        added = 0
        for row in rows:
            key = (row['feedback_id'], row.get('topic_version_id'))
            if key in seen:
                continue
            seen.add(key)
            existing.append({**deepcopy(row), 'project_id': project_id, 'task_id': task_id})
            added += 1
        return added

    def list_task_evidence(self, project_id, task_id):
        return deepcopy(self.task_evidence.get((project_id, task_id), []))

    def delete_task_evidence_for_feedback(self, project_id, feedback_ids):
        """10.4:删源数据要连任务证据一起清——它是源数据的快照,留着就是留着内容。"""
        wanted = {str(item) for item in feedback_ids}
        removed = 0
        for key, rows in list(self.task_evidence.items()):
            if key[0] != project_id:
                continue
            keep = [row for row in rows if str(row.get('feedback_id')) not in wanted]
            removed += len(rows) - len(keep)
            if keep:
                self.task_evidence[key] = keep
            else:
                del self.task_evidence[key]
        return removed

    def delete_task_data_for_project(self, project_id):
        removed = sum(1 for item in self.task_events if item['project_id'] == project_id)
        self.task_events = [item for item in self.task_events if item['project_id'] != project_id]
        for key in [k for k in self.task_evidence if k[0] == project_id]:
            del self.task_evidence[key]
        return removed

    def delete_run_data_for_project(self, project_id):
        """项目级:阶段与模型调用一同清理。"""
        removed = 0
        for key in [k for k in self.analysis_stages if k[0] == project_id]:
            del self.analysis_stages[key]
            removed += 1
        self.model_calls = [item for item in self.model_calls if item['project_id'] != project_id]
        return removed

    def delete_topics_for_run(self, project_id, run_id):
        """删 run 的主题与修订:版本与证据随主题走,不留孤儿行。"""
        topic_rows = {row_id for (pid, rid, row_id) in self.topics
                      if pid == project_id and rid == run_id}
        for version_id in [vid for (pid, vid), version in self.topic_versions.items()
                           if pid == project_id and version['topic_row_id'] in topic_rows]:
            self.topic_versions.pop((project_id, version_id), None)
            self.topic_evidence.pop((project_id, version_id), None)
        for key in [k for k in self.topics if k[0] == project_id and k[1] == run_id]:
            del self.topics[key]
        for key in [k for k in self.analysis_revisions if k[0] == project_id and k[1] == run_id]:
            del self.analysis_revisions[key]
        self.topic_corrections = [item for item in self.topic_corrections
                                  if not (item['project_id'] == project_id and item['run_id'] == run_id)]
        return len(topic_rows)

    def delete_topics_for_project(self, project_id):
        topic_keys = [key for key in self.topics if key[0] == project_id]
        for key in topic_keys:
            del self.topics[key]
        for key in [k for k in self.topic_versions if k[0] == project_id]:
            del self.topic_versions[key]
        for key in [k for k in self.topic_evidence if k[0] == project_id]:
            del self.topic_evidence[key]
        for key in [k for k in self.analysis_revisions if k[0] == project_id]:
            del self.analysis_revisions[key]
        self.topic_corrections = [item for item in self.topic_corrections
                                  if item['project_id'] != project_id]
        return len(topic_keys)

    def delete_idempotency_for_project(self, project_id):
        """10.4:删除项目要清理「幂等响应正文」——它记录着被删对象的存在与内容。

        此前没有这一步:项目删干净了,幂等键还原样留着,重放同一个键还会
        命中一条指向已删分析的记录。计划把幂等响应列为必须受删除策略控制的
        数据,所以它和正文、分块一样属于清理范围。
        """
        keys = [key for key, value in self.idempotency.items()
                if value.get('project_id') == project_id]
        for key in keys:
            del self.idempotency[key]
        return len(keys)

    def count_idempotency(self, project_id):
        """删除核验用:幂等记录不在 _domain 映射里,不能走 list_entities。"""
        return sum(1 for value in self.idempotency.values()
                   if value.get('project_id') == project_id)

    # —— §5.2 反馈与分块 ——
    # 以 (project_id, id) 为键:计划 5.1 要求跨表引用不得越过项目边界,
    # 内存仓储也照此隔离,否则 SQL 侧才会暴露的越权在测试里看不见。
    def _feedback_index(self, project_id):
        return {(row['project_id'], row['event_key']): row
                for row in self.feedback.values() if row['project_id'] == project_id}

    def save_feedback_rows(self, project_id, dataset_id, rows):
        """按 4.4 写入反馈行:整批替换本数据集的行,再跨数据集做事件去重。

        两条规则:

        - **跨数据集同 event_key 同内容** → 4.4 的 duplicate,不新增反馈,归属仍是
          首次有效导入的那个数据集,并把它的 dataset_id 报给调用方。
        - **跨数据集同 event_key 异内容** → 4.4 的 SOURCE_ID_CONFLICT,记错误、
          不覆盖历史证据。

        本批次自己的行先删后写,因此重跑校验(比如改了字段映射)不会自己撞自己。
        已知代价:若另一批次的行当初被判为重复而未落库,而本批次重跑后不再产生
        该 event_key,那条反馈就消失了。修它需要让被去重方重新认领,属于
        首版之外的机制;当前按 4.4「归属首次有效导入」的字面语义处理。
        """
        # 先清掉本批次的旧行,且把本批次排除在去重比较之外。
        # `id` 由行在批次内的位置派生,所以重新治理后位置会变:保留旧 id 会和
        # 新行的 id 撞键,而按新位置重算又会与本轮自己的旧行撞 event_key。
        # 整批替换同时解决两者,并且顺带丢掉这一轮不再产生的行。
        removed = self.delete_feedback_for_dataset(project_id, dataset_id)
        existing = self._feedback_index(project_id)
        inserted = duplicate = 0
        conflicts: list[dict] = []
        claimed: set[str] = set()
        stored: list[int] = []
        for index, row in enumerate(rows):
            value = deepcopy(row)
            value['project_id'] = project_id
            value['dataset_id'] = dataset_id
            key = (project_id, value['event_key'])
            prior = existing.get(key)
            if prior is not None:
                if same_event(prior, value):
                    duplicate += 1
                else:
                    conflicts.append({'source_row': value['source_row'],
                                      'code': 'SOURCE_ID_CONFLICT',
                                      'existing_dataset_id': prior['dataset_id']})
                claimed.add(prior['dataset_id'])
                continue
            self.feedback[(project_id, value['id'])] = value
            existing[key] = value
            inserted += 1
            stored.append(index)
        return {'inserted': inserted, 'duplicate': duplicate, 'conflicts': conflicts,
                'existing_dataset_ids': sorted(claimed), 'removed': removed,
                # 落库行在入参列表中的下标:调用方据此把预览对齐到**真正存在**的行
                'stored_indexes': stored}

    @staticmethod
    def _feedback_out(row):
        """读取时把 occurred_at 归一成 ISO 字符串。

        SQL 仓储把它落在 timestamptz 列上,读出来由 `_feedback_dict` 序列化成
        ISO 字符串;内存仓储若原样返回 datetime,同一字段在两个模式下就有两种
        类型。而调用方(summary / reviews 的时间筛选)是按字符串解析的,
        拿到 datetime 会静默判定为「没有时间」——筛选失效却不报错。
        """
        value = deepcopy(row)
        occurred = value.get('occurred_at')
        if hasattr(occurred, 'isoformat'):
            value['occurred_at'] = occurred.isoformat()
        return value

    def list_feedback(self, project_id, dataset_ids=None, feedback_ids=None):
        wanted = set(dataset_ids) if dataset_ids is not None else None
        wanted_ids = set(feedback_ids) if feedback_ids is not None else None
        rows = [self._feedback_out(row) for key, row in self.feedback.items()
                if key[0] == project_id
                and (wanted is None or row['dataset_id'] in wanted)
                and (wanted_ids is None or key[1] in wanted_ids)]
        # 与导入时的枚举顺序一致:source_row 升序、同批内按数据集稳定
        rows.sort(key=lambda row: (row.get('dataset_id', ''), row.get('source_row', 0)))
        return rows

    def get_feedback(self, project_id, feedback_id):
        row = self.feedback.get((project_id, feedback_id))
        return None if row is None else self._feedback_out(row)

    def delete_feedback_for_dataset(self, project_id, dataset_id):
        keys = [key for key, row in self.feedback.items()
                if key[0] == project_id and row['dataset_id'] == dataset_id]
        for key in keys:
            del self.feedback[key]
        return len(keys)

    def delete_feedback_for_project(self, project_id):
        keys = [key for key in self.feedback if key[0] == project_id]
        for key in keys:
            del self.feedback[key]
        return len(keys)

    def replace_segments(self, project_id, feedback_id, spans, redaction_version):
        """整批替换该反馈的分块:重新分块是重算,不是追加。"""
        key = (project_id, feedback_id)
        self.segments[key] = [
            {'id': f'seg_{feedback_id}_{index}', 'project_id': project_id,
             'feedback_id': feedback_id, 'start_offset': span.start, 'end_offset': span.end,
             'segment_index': index, 'redaction_version': redaction_version}
            for index, span in enumerate(spans)
        ]
        return len(self.segments[key])

    def list_segments(self, project_id, feedback_id):
        return deepcopy(self.segments.get((project_id, feedback_id), []))

    def count_segments(self, project_id):
        """删除核验用:按项目统计分块数,而不是逐个反馈去问。"""
        return sum(len(items) for (pid, _fid), items in self.segments.items() if pid == project_id)

    # —— §5.2 run_feedbacks:冻结一次分析的输入集合 ——
    def save_run_feedbacks(self, project_id, run_id, feedback_ids):
        """整批替换该 run 的输入清单。

        与反馈行同一套理由:重建一个 run 的输入是重算,不是追加;
        保留旧行会留下指向已不在输入集合里的反馈的条目。
        """
        live = {row['id'] for key, row in self.feedback.items() if key[0] == project_id}
        self.run_feedbacks[project_id] = [
            {'id': f'rf_{run_id}_{index}', 'project_id': project_id, 'run_id': run_id,
             'feedback_id': feedback_id}
            for index, feedback_id in enumerate(feedback_ids) if feedback_id in live
        ]
        return len(self.run_feedbacks[project_id])

    def list_run_feedback_ids(self, project_id, run_id):
        return [row['feedback_id'] for row in self.run_feedbacks.get(project_id, [])
                if row['run_id'] == run_id]

    def delete_run_feedbacks_for_run(self, project_id, run_id):
        rows = self.run_feedbacks.get(project_id, [])
        keep = [row for row in rows if row['run_id'] != run_id]
        removed = len(rows) - len(keep)
        self.run_feedbacks[project_id] = keep
        return removed

    def delete_run_feedbacks_for_project(self, project_id):
        removed = len(self.run_feedbacks.get(project_id, []))
        self.run_feedbacks.pop(project_id, None)
        return removed

    def count_segments_for_feedback(self, project_id, feedback_ids):
        """数据集级的删除核验:反馈行删掉后无法再按 dataset_id 反查分块,
        所以按删除前捕获的 feedback_id 清单核验,而不是退回到项目总数
        (那会把别的批次的分块算进来,让核验永远不为零)。"""
        wanted = set(feedback_ids)
        return sum(len(items) for (pid, fid), items in self.segments.items()
                   if pid == project_id and fid in wanted)

    def delete_segments_for_project(self, project_id):
        keys = [key for key in self.segments if key[0] == project_id]
        for key in keys:
            del self.segments[key]
        return len(keys)

    def delete_segments_for_dataset(self, project_id, dataset_id):
        """分块随其反馈走:先找出本批次的反馈,再删它们的分块。"""
        ids = {row['id'] for row in self.feedback.values()
               if row['project_id'] == project_id and row['dataset_id'] == dataset_id}
        removed = 0
        for key in [key for key in self.segments if key[0] == project_id and key[1] in ids]:
            removed += len(self.segments[key])
            del self.segments[key]
        return removed


repository = InMemoryRepository()


def get_repository():
    if os.getenv('USE_DATABASE', '').lower() in ('1', 'true', 'yes'):
        from .sql_repository import SQLAlchemyRepository
        return SQLAlchemyRepository()
    return InMemoryRepository()
