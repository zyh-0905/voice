"""Deterministic worker with explicit persistence at each state transition."""
from typing import MutableMapping
from .analysis import analyze_feedback


class AnalysisWorker:
    def __init__(self, analyses: MutableMapping[str, dict]):
        self.analyses = analyses

    def run(self, analysis_id: str) -> dict:
        run = self.analyses[analysis_id]
        run.update(status="running", stage="analyzing")
        self.analyses[analysis_id] = run
        try:
            rows = []
            for dataset in run.get("datasets", []):
                rows.extend(dataset.get("preview", {}).get("rows", []))
            if rows:
                run["analysis"] = analyze_feedback(rows)
            run.update(status="done", stage="completed", progress=int(run.get("total") or 0))
        except Exception as exc:
            run.update(status="error", stage="error", error=str(exc))
        self.analyses[analysis_id] = run
        return run

    def retry(self, analysis_id: str) -> dict:
        run = self.analyses[analysis_id]
        run.pop("error", None)
        run.update(status="queued", stage="queued", progress=0)
        self.analyses[analysis_id] = run
        return run

    def cancel(self, analysis_id: str) -> dict:
        run = self.analyses[analysis_id]
        if run.get("status") in {"done", "error", "cancelled"}:
            return run
        run.update(status="cancelled", stage="cancelled")
        self.analyses[analysis_id] = run
        return run
