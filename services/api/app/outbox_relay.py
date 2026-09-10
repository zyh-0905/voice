"""Publish pending outbox events to the analysis queue with retry-safe semantics."""
from typing import Callable, Any

from .repository import Repository, get_repository


class OutboxRelay:
    def __init__(self, repo: Repository | None = None, publisher: Callable[..., Any] | None = None):
        # 必须经 get_repository() 按 USE_DATABASE 选择仓库:
        # relay 是独立进程,InMemory 单例不会共享 API 进程的 outbox 数据。
        self.repository = repo or get_repository()
        if publisher is None:
            from .tasks import run_analysis_task
            publisher = run_analysis_task
        self.publisher = publisher

    def publish_pending(self, limit: int = 100) -> dict[str, int]:
        published = failed = 0
        for event in self.repository.list_pending_outbox(limit=max(0, min(limit, 1000))):
            try:
                payload = event.get("payload") or {}
                analysis_id = payload.get("analysis_id")
                if event.get("event_type") == "analysis.created" and analysis_id:
                    # Celery tasks expose delay; direct callables are useful in tests.
                    if hasattr(self.publisher, "delay"):
                        self.publisher.delay(analysis_id)
                    else:
                        self.publisher(analysis_id)
                else:
                    raise ValueError(f"unsupported event type: {event.get('event_type')}")
                self.repository.mark_published(event["event_key"])
                published += 1
            except Exception as exc:  # leave pending for a later relay pass
                failed += 1
                if hasattr(self.repository, "mark_publish_failed"):
                    self.repository.mark_publish_failed(event["event_key"], str(exc))
        return {"published": published, "failed": failed}
