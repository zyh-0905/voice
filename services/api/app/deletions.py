"""工程计划 10.4 删除与备份:先预览影响范围,再二次确认执行。

删除顺序与计划文本一致:
  OWNER 确认 → 写 tombstone → 取消作业/禁止新调用 → 清理原文件与导出
  → 清理反馈/主题/证据引用 → 核验依赖清单为零 → DONE(保留不含正文的最小回执)

关键约束:删除后**不能留着旧报告继续当作有效结果**——级联会清除引用被删
批次的分析结果与派生数据,而不是仅隐藏入口。
"""
from __future__ import annotations

from typing import Mapping


class DeletionError(ValueError):
    """删除请求不合法(目标不存在、类型不支持)。"""


class DeletionConflict(DeletionError):
    """确认名称不符,或清理后仍有依赖残留。"""


def _datasets_of(repository, project_id: str) -> list[dict]:
    return [d for d in repository.datasets.values() if d.get('project_id') == project_id]


def _runs_of(repository, project_id: str) -> list[dict]:
    return [a for a in repository.analyses.values() if a.get('project_id') == project_id]


def _topic_count(run: Mapping) -> int:
    return len((run.get('result') or {}).get('topics') or [])


def preview_deletion(repository, project_id: str, target_type: str, target_id: str) -> dict:
    """只预览不写入:返回将被清理的对象计数,供确认前展示。"""
    if target_type == 'project':
        project = repository.get_project(project_id)
        if not project:
            raise DeletionError('project_not_found')
        runs = _runs_of(repository, project_id)
        return {
            'target_type': 'project', 'target_id': project_id,
            'target_name': project.get('name', project_id),
            'datasets': len(_datasets_of(repository, project_id)),
            'runs': len(runs),
            'topics': sum(_topic_count(run) for run in runs),
            'tasks': len(repository.list_entities('tasks', project_id)),
            'reviews': len(repository.list_entities('reviews', project_id)),
            'risks': len(repository.list_entities('risks', project_id)),
        }
    if target_type == 'dataset':
        dataset = repository.datasets.get(target_id)
        if dataset is None or dataset.get('project_id') != project_id:
            raise DeletionError('dataset_not_found')
        affected = [run for run in _runs_of(repository, project_id)
                    if target_id in (run.get('dataset_ids') or [])]
        return {
            'target_type': 'dataset', 'target_id': target_id,
            'target_name': dataset.get('name', target_id),
            'datasets': 1,
            'runs': len(affected),
            'topics': sum(_topic_count(run) for run in affected),
            'tasks': 0, 'reviews': 0, 'risks': 0,
            # 确认前必须说明:删除批次会让引用它的分析、主题结果与证据失效
            'invalidates_reports': len(affected) > 0,
        }
    raise DeletionError('unsupported_target_type')


def _cancel_jobs(repository, runs: list[dict]) -> int:
    """取消未完成作业,禁止继续写入已删除的数据。"""
    cancelled = 0
    for run in runs:
        if str(run.get('status') or '') in ('queued', 'running'):
            repository.update_analysis(run['id'], {
                'status': 'cancelled', 'stage': 'cancelled',
                'lease_owner': None, 'lease_expires_at': None,
            })
            cancelled += 1
    return cancelled


def _safe_delete(repository, delete, key: str) -> None:
    try:
        delete(key)
    except (KeyError, TypeError):
        # 幂等:目标已经不在了也算清理成功
        pass


def execute_deletion(repository, project_id: str, target_type: str, target_id: str,
                     confirm_name: str, job_id: str, actor: str) -> dict:
    """执行删除:级联清理并返回最小回执(不含任何正文)。"""
    preview = preview_deletion(repository, project_id, target_type, target_id)
    if confirm_name.strip() != str(preview['target_name']).strip():
        raise DeletionConflict('confirm_name_mismatch')

    steps: list[dict] = []

    # 1) 先写 tombstone:备份恢复后可据此重放删除
    repository.create_entity('deletions', {
        'id': job_id, 'project_id': project_id, 'target_type': target_type,
        'target_id': target_id, 'target_name': preview['target_name'],
        'state': 'RUNNING', 'actor': actor,
        'steps': [{'name': 'tombstone', 'status': 'done'}],
    })
    steps.append({'name': 'tombstone', 'status': 'done'})

    runs = _runs_of(repository, project_id)
    if target_type == 'dataset':
        runs = [run for run in runs if target_id in (run.get('dataset_ids') or [])]

    # 2) 取消作业
    steps.append({'name': 'cancel_jobs', 'status': 'done', 'cancelled': _cancel_jobs(repository, runs)})

    # 3) 清理分析结果(主题、证据、风险候选都挂在 run 上)
    for run in runs:
        _safe_delete(repository, repository.delete_analysis, run['id'])
    steps.append({'name': 'purge_runs', 'status': 'done', 'runs': len(runs)})

    # 3.5) 未过期的导出一并失效:删除后不留可用下载链接(10.3)
    from .exports import invalidate_project_exports
    steps.append({'name': 'invalidate_exports', 'status': 'done',
                  'invalidated': invalidate_project_exports(repository, project_id)})

    # 4) 清理数据集(原文件与导出)
    dataset_ids = [target_id] if target_type == 'dataset' else [d['id'] for d in _datasets_of(repository, project_id)]
    for dataset_id in dataset_ids:
        _safe_delete(repository, repository.delete_dataset, dataset_id)
    steps.append({'name': 'purge_datasets', 'status': 'done', 'datasets': len(dataset_ids)})

    # 5) 项目级:清理任务、复盘、风险与项目本身
    if target_type == 'project':
        for kind in ('tasks', 'reviews', 'risks'):
            for item in repository.list_entities(kind, project_id):
                _safe_delete(repository, lambda key, _kind=kind: repository.delete_entity(_kind, key), item['id'])
            steps.append({'name': f'purge_{kind}', 'status': 'done'})
        repository.delete_project(project_id)
        steps.append({'name': 'purge_project', 'status': 'done'})

    # 6) 核验依赖清单为零
    if target_type == 'project':
        remaining = {
            'datasets': len(_datasets_of(repository, project_id)),
            'runs': len(_runs_of(repository, project_id)),
            'tasks': len(repository.list_entities('tasks', project_id)),
            'reviews': len(repository.list_entities('reviews', project_id)),
            'risks': len(repository.list_entities('risks', project_id)),
        }
    else:
        remaining = {'datasets': int(target_id in repository.datasets)}
    steps.append({'name': 'verify', 'status': 'done', 'remaining': remaining})
    if any(remaining.values()):
        raise DeletionConflict(f'dependencies_remaining: {remaining}')

    receipt = {
        'job_id': job_id, 'state': 'DONE', 'target_type': target_type,
        'target_id': target_id, 'actor': actor, 'steps': steps,
        # 回执只保留计数,不含任何正文
        'removed': {key: preview[key] for key in ('datasets', 'runs', 'topics', 'tasks', 'reviews', 'risks')},
    }
    try:
        repository.update_entity('deletions', job_id, {'state': 'DONE', 'steps': steps, 'receipt': receipt})
    except (KeyError, AttributeError):
        pass
    return receipt


def get_deletion(repository, project_id: str, job_id: str) -> dict | None:
    """回执查询:项目本体被清理后仍可查(删除登记独立于项目数据)。"""
    for job in repository.list_entities('deletions', project_id):
        if job.get('id') == job_id:
            return job
    return None
