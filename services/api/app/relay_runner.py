"""Standalone process for draining the transactional outbox.

The runner deliberately keeps the relay loop small: publishing is delegated to
``OutboxRelay`` while this module owns lifecycle, scheduling, and termination.
"""
from __future__ import annotations

import logging
import os
import signal
import time

from .outbox_relay import OutboxRelay

logger = logging.getLogger(__name__)


def run() -> None:
    interval = max(0.1, float(os.getenv("OUTBOX_RELAY_INTERVAL_SECONDS", "5")))
    stop = False

    def request_stop(signum: int, _frame: object) -> None:
        nonlocal stop
        stop = True
        logger.info("received signal %s; stopping outbox relay", signum)

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    relay = OutboxRelay()
    logger.info("outbox relay started (interval=%ss)", interval)
    while not stop:
        try:
            result = relay.publish_pending(limit=100)
            if result.get("published") or result.get("failed"):
                logger.info("outbox relay pass: %s", result)
        except Exception:
            logger.exception("outbox relay pass failed")
        # A bounded sleep makes SIGTERM responsive without busy looping.
        deadline = time.monotonic() + interval
        while not stop and time.monotonic() < deadline:
            time.sleep(min(0.25, deadline - time.monotonic()))
    logger.info("outbox relay stopped")


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    run()
