"""W06 看门狗:恢复租约过期的 running 作业(worker 崩溃场景)。

租约过期且 attempts 未达上限 → 重置为 queued 并重新派发;
达到上限 → 转 error,不再自动重试(避免无限复活)。
与 outbox relay 同循环运行,见 relay_runner.run。
"""
from __future__ import annotations

from typing import Any, Callable, MutableMapping

from .worker import MAX_RECOVERY_ATTEMPTS, _now


class RunWatchdog:
    def __init__(self, analyses: MutableMapping[str, dict], publisher: Callable[..., Any] | None = None):
        self.analyses = analyses
        if publisher is None:
            from .celery_tasks import run_analysis_task
            publisher = run_analysis_task
        self.publisher = publisher

    def recover_stale(self, now: float | None = None) -> dict[str, int]:
        """扫描 running 且租约过期的作业;返回 {recovered, errored}。"""
        recovered = errored = 0
        timestamp = now if now is not None else _now()
        for analysis_id, run in list(self.analyses.items()):
            if run.get('status') != 'running':
                continue
            lease = run.get('lease_expires_at')
            if lease is None or lease > timestamp:
                continue
            attempts = int(run.get('attempts', 0))
            if attempts >= MAX_RECOVERY_ATTEMPTS:
                run.update(status='error', stage='error',
                           error=f'lease expired after {attempts} attempts',
                           lease_owner=None, lease_expires_at=None)
                self.analyses[analysis_id] = run
                errored += 1
                continue
            run.update(status='queued', stage='queued', progress=0,
                       lease_owner=None, lease_expires_at=None)
            self.analyses[analysis_id] = run
            if hasattr(self.publisher, 'delay'):
                self.publisher.delay(analysis_id)
            else:
                self.publisher(analysis_id)
            recovered += 1
        return {'recovered': recovered, 'errored': errored}
