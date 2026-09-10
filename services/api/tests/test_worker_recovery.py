"""W06 恢复语义:租约过期重排队、超限转 error、outbox 死信重试。"""
import time

from app.main import repository, worker
from app.outbox_relay import OutboxRelay
from app.repository import MAX_PUBLISH_ATTEMPTS
from app.watchdog import RunWatchdog

ANALYSES = repository.analyses


def _seed_crashed_run(aid, attempts, lease_ago=60):
    ANALYSES[aid] = {
        'id': aid, 'project_id': 'p', 'dataset_ids': [], 'datasets': [],
        'status': 'running', 'stage': 'analyzing', 'progress': 0, 'total': 0,
        'attempts': attempts, 'lease_owner': 'dead-worker',
        'lease_expires_at': time.time() - lease_ago,
    }


def test_stale_lease_requeues():
    calls = []
    watchdog = RunWatchdog(ANALYSES, publisher=lambda aid: calls.append(aid))
    _seed_crashed_run('crash-rq', attempts=1)
    try:
        result = watchdog.recover_stale()
        assert result == {'recovered': 1, 'errored': 0}
        assert ANALYSES['crash-rq']['status'] == 'queued'
        assert calls == ['crash-rq']
    finally:
        del ANALYSES['crash-rq']


def test_stale_lease_over_limit_errors():
    watchdog = RunWatchdog(ANALYSES, publisher=lambda aid: None)
    _seed_crashed_run('crash-err', attempts=3)
    try:
        result = watchdog.recover_stale()
        assert result == {'recovered': 0, 'errored': 1}
        assert ANALYSES['crash-err']['status'] == 'error'
        assert 'lease expired' in ANALYSES['crash-err']['error']
    finally:
        del ANALYSES['crash-err']


def test_running_with_fresh_lease_untouched():
    watchdog = RunWatchdog(ANALYSES, publisher=lambda aid: None)
    _seed_crashed_run('crash-fresh', attempts=1, lease_ago=-600)
    try:
        result = watchdog.recover_stale()
        assert result == {'recovered': 0, 'errored': 0}
        assert ANALYSES['crash-fresh']['status'] == 'running'
    finally:
        del ANALYSES['crash-fresh']


def test_worker_clears_lease_on_completion():
    ANALYSES['run-ok'] = {'id': 'run-ok', 'project_id': 'p', 'dataset_ids': [], 'datasets': [], 'status': 'queued', 'stage': 'queued', 'total': 0}
    try:
        out = worker.run('run-ok')
        assert out['status'] == 'done'
        assert out.get('lease_owner') is None
        assert out.get('lease_expires_at') is None
        assert out['attempts'] == 1
    finally:
        del ANALYSES['run-ok']


def test_outbox_failed_retries_then_dead_letters():
    repository.outbox.clear()
    repository.create_outbox_event({'event_key': 'evt-fail-1', 'event_type': 'analysis.created', 'payload': {'analysis_id': 'x', 'project_id': 'p'}})

    def boom(_aid):
        raise RuntimeError('queue down')

    relay = OutboxRelay(repository, publisher=boom)
    first = relay.publish_pending()
    assert first == {'published': 0, 'failed': 1}
    event = next(e for e in repository.outbox if e['event_key'] == 'evt-fail-1')
    assert event['status'] == 'pending' and event['attempts'] == 1

    for _ in range(2):
        relay.publish_pending()
    event = next(e for e in repository.outbox if e['event_key'] == 'evt-fail-1')
    assert event['status'] == 'failed'
    assert event['attempts'] == MAX_PUBLISH_ATTEMPTS
    # 死信不再被重投
    assert relay.publish_pending() == {'published': 0, 'failed': 0}
