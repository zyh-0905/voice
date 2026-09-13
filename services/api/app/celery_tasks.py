"""队列任务入口:把分析作业交给 Celery worker。

**与 `app/tasks.py` 不是一回事。** `app/tasks.py` 是 W15 的整改任务领域状态机
(DRAFT/OPEN/…),与队列无关。两个模块都叫「任务」,此前 `celery_app` 的 include 与
三个调用点都指向了 `app.tasks`,结果是:

- worker 启动时注册不到任何任务(`[tasks]` 为空);
- relay / watchdog 直接 `ImportError: cannot import name 'run_analysis_task'`,
  relay 崩溃重启,outbox 事件永不投递。

于是真实部署里「上传 → 分析」永远停在 queued,而测试因为走进程内 worker 完全无感。
队列任务单独成模块,不再和领域模块争名字。
"""
from __future__ import annotations

import logging

from .celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_analysis(analysis_id: str) -> dict:
    """在 worker 进程内跑完整流水线。

    仓储必须在这里按 `USE_DATABASE` **重新解析**:worker 是独立进程,不共享 API
    进程的内存仓储;沿用调用方的仓储实例会在真实部署下读写到一个空库。
    """
    from .repository import get_repository
    from .worker import AnalysisWorker

    repository = get_repository()
    worker = AnalysisWorker(repository.analyses, repository)
    logger.info('analysis task started: %s', analysis_id)
    result = worker.run(analysis_id)
    logger.info('analysis task finished: %s (%s)', analysis_id, result.get('status'))
    return result


if celery_app is not None:
    # 有 Celery:注册为队列任务,调用方通过 .delay() 投递
    run_analysis_task = celery_app.task(name='voicelens.run_analysis')(_run_analysis)
else:
    # 未安装 Celery:退化为可直接调用的函数,调用方据 getattr(..., 'delay') 判定
    run_analysis_task = _run_analysis
