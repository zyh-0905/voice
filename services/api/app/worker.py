"""Deterministic worker with explicit persistence at each state transition.

W06:阶段租约——进入 running 时写入 lease_owner/lease_expires_at,完成或失败时清除;
看门狗(见 watchdog.py)负责把租约过期的 running 作业重新排队,超限转 error。
"""
import os
import time
import uuid
from typing import MutableMapping
from .analysis import analyze_feedback

LEASE_TIMEOUT_SECONDS = float(os.getenv('ANALYSIS_LEASE_TIMEOUT_SECONDS', '300'))
MAX_RECOVERY_ATTEMPTS = int(os.getenv('ANALYSIS_MAX_ATTEMPTS', '3'))


def _now() -> float:
    return time.time()


class AnalysisWorker:
    def __init__(self, analyses: MutableMapping[str, dict]):
        self.analyses = analyses
        self.lease_owner = f"worker-{os.getpid()}-{uuid.uuid4().hex[:8]}"

    def run(self, analysis_id: str) -> dict:
        run = self.analyses[analysis_id]
        attempts = int(run.get('attempts', 0)) + 1
        run.update(status="running", stage="analyzing", attempts=attempts,
                   lease_owner=self.lease_owner,
                   lease_expires_at=_now() + LEASE_TIMEOUT_SECONDS)
        self.analyses[analysis_id] = run
        try:
            rows = []
            for dataset in run.get("datasets", []):
                rows.extend(dataset.get("preview", {}).get("rows", []))
            if rows:
                run["analysis"] = analyze_feedback(rows)
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
