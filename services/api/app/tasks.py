"""W15 整改任务状态机与事务。

状态: DRAFT → OPEN → IN_PROGRESS → PENDING_REVIEW → CLOSED(可 CANCELLED);
约束:草稿不能跳过执行直接验收;负责人不得自验收(approve 需要非 assignee);
所有状态变化与事件在同一次更新内提交;幂等键防重复确认;
CLOSED 不会自动把 effect_status 变成「已证明改善」。
"""
from __future__ import annotations

from typing import Mapping

DRAFT, OPEN, IN_PROGRESS, PENDING_REVIEW, CLOSED, CANCELLED = 'DRAFT', 'OPEN', 'IN_PROGRESS', 'PENDING_REVIEW', 'CLOSED', 'CANCELLED'
EFFECT_NOT_EVALUATED = 'NOT_EVALUATED'

# state -> action -> 允许(role 条件在调用处校验)
_TRANSITIONS: dict[str, dict[str, str]] = {
    DRAFT: {'confirm': OPEN, 'cancel': CANCELLED},
    OPEN: {'start': IN_PROGRESS, 'cancel': CANCELLED},
    IN_PROGRESS: {'submit': PENDING_REVIEW, 'cancel': CANCELLED},
    PENDING_REVIEW: {'approve': CLOSED, 'reject': IN_PROGRESS, 'cancel': CANCELLED},
    CLOSED: {},
    CANCELLED: {},
}


class InvalidTransition(ValueError):
    pass


class VersionConflict(ValueError):
    pass


class FieldValidationError(ValueError):
    pass


def state_of(task: Mapping) -> str:
    """读取任务状态:规范字段是 state;兼容旧行的 status。"""
    value = task.get('state') or task.get('status') or DRAFT
    normalized = str(value).upper()
    return normalized if normalized in _TRANSITIONS else DRAFT


def can_transition(state: str, action: str, actor_role: str, is_assignee: bool) -> bool:
    """状态机判定:VIEWER 只读;approve(验收)不允许 assignee 自验收。"""
    if str(actor_role).upper() == 'VIEWER':
        return False
    if action not in _TRANSITIONS.get(state, {}):
        return False
    if action == 'approve' and is_assignee:
        return False
    return True


def transition_task(task: dict, action: str, expected_version: int, actor_id: str, actor_role: str,
                    is_assignee: bool, comment: str) -> dict:
    """执行状态变化,并把事件与状态一起写回 task(同一次更新)。"""
    if int(task.get('version') or 0) != int(expected_version):
        raise VersionConflict(f"expected version {expected_version}, current {task.get('version')}")
    state = state_of(task)
    if not can_transition(state, action, actor_role, is_assignee):
        raise InvalidTransition(f'{action} not allowed from {state}')
    task['state'] = _TRANSITIONS[state][action]
    task['version'] = int(task.get('version') or 0) + 1
    task.setdefault('events', []).append({
        'action': action, 'actor': actor_id, 'comment': comment or '', 'state': task['state'],
    })
    # 关闭任务不自动宣称经营效果改善
    if task['state'] == CLOSED:
        task.setdefault('effect_status', EFFECT_NOT_EVALUATED)
    return task


def confirm_draft(task: dict, expected_version: int, owner_id: str, due_at: str, acceptance: str,
                  actor_id: str) -> dict:
    """草稿确认:owner_id/due_at/acceptance 必填;缺字段抛 FieldValidationError。"""
    if state_of(task) != DRAFT:
        raise InvalidTransition('confirm only allowed from DRAFT')
    if int(task.get('version') or 0) != int(expected_version):
        raise VersionConflict(f"expected version {expected_version}, current {task.get('version')}")
    if not owner_id or not owner_id.strip():
        raise FieldValidationError('owner_id is required')
    if not due_at or not due_at.strip():
        raise FieldValidationError('due_at is required')
    if not acceptance or not acceptance.strip():
        raise FieldValidationError('acceptance is required')
    task.update({'owner_id': owner_id, 'due_at': due_at, 'acceptance': acceptance})
    return transition_task(task, 'confirm', expected_version, actor_id, 'ANALYST', False, 'confirm draft')
