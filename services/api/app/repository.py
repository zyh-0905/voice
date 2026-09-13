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
