"""Deterministic worker with explicit persistence at each state transition.

W06:阶段租约——进入 running 时写入 lease_owner/lease_expires_at,完成或失败时清除;
看门狗(见 watchdog.py)负责把租约过期的 running 作业重新排队,超限转 error。
"""
import os
import time
import uuid
from typing import MutableMapping

LEASE_TIMEOUT_SECONDS = float(os.getenv('ANALYSIS_LEASE_TIMEOUT_SECONDS', '300'))
MAX_RECOVERY_ATTEMPTS = int(os.getenv('ANALYSIS_MAX_ATTEMPTS', '3'))


def _now() -> float:
    return time.time()


class _AnalysisStoreAdapter:
    """把 analyses 映射适配为 publishing.AnalysisStore;共享主进程仓储实例。"""

    def __init__(self, analyses: MutableMapping[str, dict]):
        self._analyses = analyses

    def get_analysis(self, analysis_id: str) -> dict | None:
        return self._analyses.get(analysis_id)

    def update_analysis(self, analysis_id: str, changes: dict) -> dict:
        current = dict(self._analyses.get(analysis_id) or {})
        current.update(changes)
        self._analyses[analysis_id] = current
        return current


class AnalysisWorker:
    def __init__(self, analyses: MutableMapping[str, dict], repository=None):
        self.analyses = analyses
        # 传仓储时,风险候选会写进项目复核队列;不传则只算不写
        self.repository = repository
        self.store = _AnalysisStoreAdapter(analyses)
        self.lease_owner = f"worker-{os.getpid()}-{uuid.uuid4().hex[:8]}"

    def run(self, analysis_id: str) -> dict:
        run = self.analyses[analysis_id]
        attempts = int(run.get('attempts', 0)) + 1
        run.update(status="running", stage="analyzing", attempts=attempts,
                   lease_owner=self.lease_owner,
                   lease_expires_at=_now() + LEASE_TIMEOUT_SECONDS)
        self.analyses[analysis_id] = run
        try:
            # W11:分析阶段执行完整流水线(风险扫描 → 分块/向量/聚类/命名 → 发布 revision)
            from .pipeline import run_analysis_pipeline
            run_analysis_pipeline(self.store, analysis_id, self.repository)
            run = self.analyses[analysis_id]
            run.update(status="done", stage="completed", progress=int(run.get("total") or 0),
                       lease_owner=None, lease_expires_at=None)
        except Exception as exc:
            run.update(status="error", stage="error", error=str(exc),
                       lease_owner=None, lease_expires_at=None)
        self.analyses[analysis_id] = run
        return run

    def retry(self, analysis_id: str) -> dict:
        run = self.analyses[analysis_id]
        run.pop("error", None)
        run.update(status="queued", stage="queued", progress=0,
                   lease_owner=None, lease_expires_at=None)
        self.analyses[analysis_id] = run
        return run

    def cancel(self, analysis_id: str) -> dict:
        run = self.analyses[analysis_id]
        if run.get("status") in {"done", "error", "cancelled"}:
            return run
        run.update(status="cancelled", stage="cancelled",
                   lease_owner=None, lease_expires_at=None)
        self.analyses[analysis_id] = run
        return run
