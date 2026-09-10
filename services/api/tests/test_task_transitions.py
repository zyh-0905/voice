"""W15 状态机单元:合法/非法转移矩阵、自验收禁止、事件与状态同提交、幂等。"""
import pytest

from app.tasks import (
    DRAFT, OPEN, IN_PROGRESS, PENDING_REVIEW, CLOSED,
    EFFECT_NOT_EVALUATED,
    FieldValidationError,
    InvalidTransition,
    VersionConflict,
    can_transition,
    confirm_draft,
    transition_task,
)


def _task(state=DRAFT, version=1):
    return {'id': 't', 'project_id': 'p', 'title': '任务', 'state': state, 'version': version,
            'owner_id': None, 'due_at': None, 'acceptance': None, 'events': [], 'effect_status': EFFECT_NOT_EVALUATED}


def test_draft_cannot_approve():
    assert can_transition(DRAFT, 'approve', 'ANALYST', False) is False


def test_assignee_cannot_approve_own_work():
    assert can_transition(PENDING_REVIEW, 'approve', 'ANALYST', True) is False
    assert can_transition(PENDING_REVIEW, 'approve', 'ANALYST', False) is True


def test_viewer_cannot_act():
    for action in ('confirm', 'start', 'submit', 'approve', 'reject'):
        assert can_transition(DRAFT, action, 'VIEWER', False) is False


def test_full_lifecycle_transitions():
    assert can_transition(DRAFT, 'confirm', 'ANALYST', False)
    assert can_transition(OPEN, 'start', 'ANALYST', True)
    assert can_transition(IN_PROGRESS, 'submit', 'ANALYST', True)
    assert can_transition(PENDING_REVIEW, 'reject', 'ANALYST', False)
    assert can_transition(CLOSED, 'start', 'ANALYST', False) is False  # 终态不可再流转


def test_transition_appends_event_and_bumps_version():
    task = _task(DRAFT)
    transition_task(task, 'confirm', 1, 'owner', 'ANALYST', False, '确认')
    assert task['state'] == OPEN
    assert task['version'] == 2
    assert len(task['events']) == 1
    assert task['events'][0]['action'] == 'confirm'


def test_version_conflict_rejected():
    task = _task(DRAFT)
    with pytest.raises(VersionConflict):
        transition_task(task, 'confirm', 99, 'owner', 'ANALYST', False, '')


def test_invalid_transition_rejected():
    task = _task(DRAFT)
    with pytest.raises(InvalidTransition):
        transition_task(task, 'approve', 1, 'owner', 'ANALYST', False, '')


def test_closed_does_not_claim_improvement():
    task = _task(PENDING_REVIEW, version=1)
    transition_task(task, 'approve', 1, 'reviewer', 'ANALYST', False, '验收')
    assert task['state'] == CLOSED
    assert task['effect_status'] == EFFECT_NOT_EVALUATED  # 不自动变成已证明改善


def test_confirm_requires_fields():
    task = _task(DRAFT)
    with pytest.raises(FieldValidationError, match='owner_id'):
        confirm_draft(task, 1, '', '2026-09-20', '验收标准', 'owner')
    with pytest.raises(FieldValidationError, match='due_at'):
        confirm_draft(task, 1, 'owner-1', '', '验收标准', 'owner')
    with pytest.raises(FieldValidationError, match='acceptance'):
        confirm_draft(task, 1, 'owner-1', '2026-09-20', '', 'owner')


def test_confirm_sets_fields_and_transitions():
    task = _task(DRAFT)
    confirm_draft(task, 1, 'owner-1', '2026-09-20T18:00:00+08:00', '退款率下降', 'owner')
    assert task['state'] == OPEN
    assert task['owner_id'] == 'owner-1'
    assert task['due_at'].startswith('2026-09-20')
    assert task['acceptance'] == '退款率下降'
