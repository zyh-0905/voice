"""异步分析的接线:队列任务必须真的存在、真的被 worker 注册。

这条链路的失效极难被察觉,因为它不影响任何进程内路径:测试全部走
`RUN_WORKER_INLINE` 或直接调 `AnalysisWorker`,从不经过队列。于是当
`run_analysis_task` 整个不存在时,套件仍然全绿,而真实部署里 relay 启动即崩、
worker 注册不到任何任务,分析永远停在 queued。
"""
import importlib

import pytest

from app.celery_app import celery_app
from app.outbox_relay import OutboxRelay

TASK_NAME = 'voicelens.run_analysis'


def test_analysis_task_is_importable():
    """三个调用点(outbox_relay / watchdog / main)都按名字导入它。"""
    from app.celery_tasks import run_analysis_task

    assert callable(run_analysis_task)


def test_relay_default_publisher_resolves():
    """relay 是独立进程且默认构造 publisher:这里导入失败等于 relay 启动即崩。"""
    relay = OutboxRelay(repo=object())

    assert callable(relay.publisher)


def test_watchdog_default_publisher_resolves():
    """看门狗同样在构造时解析 publisher:导入失败等于恢复逻辑一跑就崩。"""
    from app.watchdog import RunWatchdog

    watchdog = RunWatchdog({})

    assert callable(watchdog.publisher)


@pytest.mark.skipif(celery_app is None, reason='未安装 celery')
def test_included_modules_actually_register_a_task():
    """celery_app 的 include 必须指向真正定义了任务模块。

    此前 include 写的是 `services.api.app.tasks`——那其实是 W15 的整改任务领域
    状态机,里面没有任何 celery 任务,于是 worker 的 `[tasks]` 是空的。
    """
    included = list(celery_app.conf.include or [])
    assert included, 'worker 必须 include 队列任务模块,否则 [tasks] 为空'

    for module_name in included:
        importlib.import_module(module_name)

    assert TASK_NAME in celery_app.tasks, (
        f'include 的模块里没有注册 {TASK_NAME};worker 会以空任务表启动'
    )
