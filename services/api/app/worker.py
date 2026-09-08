"""Small, deterministic analysis worker used by the API and tests.

The production deployment can replace this with a Celery task; the state
machine intentionally lives here so API behaviour remains identical.
"""
from __future__ import annotations

from typing import MutableMapping
from .analysis import analyze_feedback


class AnalysisWorker:
    def __init__(self, analyses: MutableMapping[str, dict]):
        self.analyses = analyses

    def run(self, analysis_id: str) -> dict:
        run = self.analyses[analysis_id]
        try:
            run.update(status="running", stage="analyzing")
            total = int(run.get("total") or 0)
            rows = []
            for dataset in run.get("datasets", []):
                rows.extend(dataset.get("preview", {}).get("rows", []))
            if rows:
                run["analysis"] = analyze_feedback(rows)
            run["progress"] = total
            run.update(status="done", stage="completed")
            return run
        except Exception as exc:  # pragma: no cover - defensive boundary
            run.update(status="error", stage="error", error=str(exc))
            return run

    def retry(self, analysis_id: str) -> dict:
        run = self.analyses[analysis_id]
        run.pop("error", None)
        run.update(status="queued", stage="queued", progress=0)
        return run

    def cancel(self, analysis_id: str) -> dict:
        run = self.analyses[analysis_id]
        if run.get("status") in {"done", "error", "cancelled"}:
            return run
        run.update(status="cancelled", stage="cancelled")
        return run
